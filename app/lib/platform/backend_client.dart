/// Client for the Python backend's JSON Lines protocol.
///
/// One JSON object per line over the child process's stdin/stdout:
///
///   request  `{"id": 1, "method": "resources.list", "params": {...}}`
///   response `{"id": 1, "ok": true, "result": {...}}`
///   error    `{"id": 1, "ok": false, "error": {"code": ..., "key": ..., ...}}`
///   event    `{"event": "hotkey", "payload": {...}}`
///
/// stdout is protocol-only; the backend writes diagnostics to stderr.
///
/// Encoding is handled explicitly with UTF-8 on both directions. Relying on
/// [Process.start]'s default would use the system encoding (cp936 on Chinese
/// Windows) and mangle every non-ASCII path.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// A structured failure returned by the backend.
///
/// [code] is one of `bad_request`, `validation`, `duplicate`, `not_found`,
/// `corrupt_data`, `unknown_method`, `internal`. When [key] is present it is a
/// key from the legacy string table and can be translated directly.
class BackendException implements Exception {
  const BackendException(this.code, this.detail, {this.key});

  final String code;
  final String detail;
  final String? key;

  bool get isCorruptData => code == 'corrupt_data';

  @override
  String toString() =>
      'BackendException($code${key == null ? '' : ', key: $key'}): $detail';
}

/// An unsolicited message from the backend (hotkey press, tray toggle, …).
class BackendEvent {
  const BackendEvent(this.name, this.payload);

  final String name;
  final Map<String, dynamic> payload;

  @override
  String toString() => 'BackendEvent($name, $payload)';
}

/// Owns the backend child process and correlates requests with responses.
class BackendClient {
  BackendClient._(this._process, this._timeout) {
    _subscription = _process.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(_onLine, onDone: _onDone, onError: _onStreamError);
    _errorSubscription = _process.stderr
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(_onStderrLine);
  }

  /// Launches the backend.
  ///
  /// [scriptPath] is the Python entry script in source mode, or null when
  /// [executable] is a self-contained backend binary. [baseDir] is where the
  /// JSON data files live.
  static Future<BackendClient> start({
    required String executable,
    String? scriptPath,
    required String baseDir,
    List<String> extraArgs = const <String>[],
    Duration timeout = const Duration(seconds: 20),
  }) async {
    final Process process = await Process.start(
      executable,
      <String>[
        ?scriptPath,
        baseDir,
        ...extraArgs,
      ],
      workingDirectory: Directory.current.path,
    );
    return BackendClient._(process, timeout);
  }

  final Process _process;
  final Duration _timeout;
  final StreamController<BackendEvent> _events =
      StreamController<BackendEvent>.broadcast();
  final Map<int, Completer<Map<String, dynamic>>> _pending =
      <int, Completer<Map<String, dynamic>>>{};

  late final StreamSubscription<String> _subscription;
  late final StreamSubscription<String> _errorSubscription;
  int _nextId = 1;
  bool _closed = false;

  /// Diagnostics forwarded from the backend's stderr (never protocol frames).
  final StreamController<String> _logs = StreamController<String>.broadcast();

  Stream<BackendEvent> get events => _events.stream;
  Stream<String> get logs => _logs.stream;
  bool get isRunning => !_closed && _process.exitCode != Future<void>.value();

  /// Sends a request and waits for its response.
  ///
  /// Throws [BackendException] for structured failures, [TimeoutException] when
  /// the backend does not answer, and [StateError] after [close].
  Future<Map<String, dynamic>> call(
    String method, [
    Map<String, dynamic> params = const <String, dynamic>{},
  ]) {
    if (_closed) {
      throw StateError('BackendClient is closed');
    }
    final int id = _nextId++;
    final Completer<Map<String, dynamic>> completer =
        Completer<Map<String, dynamic>>();
    _pending[id] = completer;
    _write(<String, dynamic>{'id': id, 'method': method, 'params': params});

    return completer.future.timeout(
      _timeout,
      onTimeout: () {
        _pending.remove(id);
        throw TimeoutException('backend did not answer $method within $_timeout');
      },
    );
  }

  /// Shuts the backend down and releases the process.
  Future<void> close({Duration grace = const Duration(seconds: 2)}) async {
    if (_closed) {
      return;
    }
    try {
      await call('app.shutdown').timeout(grace);
    } catch (_) {
      // Best effort: fall through to a hard kill.
    }
    _closed = true;
    await _subscription.cancel();
    await _errorSubscription.cancel();
    await _process.stdin.close().catchError((Object _) {});
    try {
      await _process.exitCode.timeout(grace);
    } on TimeoutException {
      _process.kill();
    }
    _failPending(const BackendException('internal', 'backend closed'));
    await _events.close();
    await _logs.close();
  }

  void _write(Map<String, dynamic> frame) {
    final String line = jsonEncode(frame);
    _process.stdin.add(utf8.encode('$line\n'));
  }

  void _onLine(String line) {
    if (line.trim().isEmpty) {
      return;
    }
    final Map<String, dynamic> frame;
    try {
      frame = jsonDecode(line) as Map<String, dynamic>;
    } on FormatException {
      // A non-JSON line on stdout is a backend bug; surface it instead of
      // silently dropping it.
      _logs.add('malformed frame: $line');
      return;
    }

    if (!frame.containsKey('id')) {
      final Object? name = frame['event'];
      final Object? payload = frame['payload'];
      if (name is String) {
        _events.add(
          BackendEvent(
            name,
            payload is Map<String, dynamic>
                ? payload
                : <String, dynamic>{},
          ),
        );
      }
      return;
    }

    final Object? rawId = frame['id'];
    if (rawId is! int) {
      return;
    }
    final Completer<Map<String, dynamic>>? completer = _pending.remove(rawId);
    if (completer == null || completer.isCompleted) {
      return;
    }
    if (frame['ok'] == true) {
      final Object? result = frame['result'];
      completer.complete(
        result is Map<String, dynamic> ? result : <String, dynamic>{},
      );
      return;
    }
    final Object? error = frame['error'];
    final Map<String, dynamic> errorMap =
        error is Map<String, dynamic> ? error : <String, dynamic>{};
    completer.completeError(
      BackendException(
        errorMap['code'] as String? ?? 'internal',
        errorMap['detail'] as String? ?? '',
        key: errorMap['key'] as String?,
      ),
    );
  }

  void _onStderrLine(String line) {
    if (line.trim().isEmpty) {
      return;
    }
    _logs.add(line);
  }

  void _onDone() {
    _closed = true;
    _failPending(const BackendException('internal', 'backend exited'));
  }

  void _onStreamError(Object error) {
    _logs.add('stdout error: $error');
    _onDone();
  }

  void _failPending(BackendException error) {
    for (final Completer<Map<String, dynamic>> completer in _pending.values) {
      if (!completer.isCompleted) {
        completer.completeError(error);
      }
    }
    _pending.clear();
  }
}
