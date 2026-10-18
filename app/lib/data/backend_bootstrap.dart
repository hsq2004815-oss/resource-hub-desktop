/// Locates and starts the Python backend, then exposes a ready repository.
///
/// Resolution order is deliberately boring so both `flutter run` (from `app/`)
/// and the packaged release build work:
///
/// | what | order |
/// |---|---|
/// | backend executable | `RH_BACKEND_EXE`, then `backend/resource_hub_backend.exe` next to the app |
/// | backend script | `RH_BACKEND_SCRIPT`, `backend/main.py`, `../backend/main.py` |
/// | python | `RH_PYTHON`, `python`, `py` |
/// | data dir | `RH_DATA_DIR`, else the directory containing `backend/` |
///
/// Any failure becomes a [BackendStartupException] with a human-readable reason
/// instead of an unhandled crash — the UI shows a retry screen.
library;

import 'dart:io';

import '../platform/backend_client.dart';
import 'backend_repository.dart';

/// A started backend plus the metadata from `app.hello`.
class BackendConnection {
  const BackendConnection({
    required this.repository,
    required this.hello,
    required this.executable,
  });

  final BackendRepository repository;
  final BackendHello hello;

  /// What was launched, for the error screen / diagnostics.
  final String executable;

  Future<void> close() => repository.client.close();
}

class BackendStartupException implements Exception {
  const BackendStartupException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Where the backend lives on this machine.
class BackendLocation {
  const BackendLocation({
    required this.executable,
    required this.scriptPath,
    required this.baseDir,
  });

  final String executable;

  /// Null when [executable] is a self-contained backend binary.
  final String? scriptPath;
  final String baseDir;
}

abstract final class BackendBootstrap {
  static BackendLocation locate() {
    final Map<String, String> env = Platform.environment;

    final String? backendExe = _nonEmpty(env['RH_BACKEND_EXE']);
    if (backendExe != null && File(backendExe).existsSync()) {
      final String baseDir =
          _nonEmpty(env['RH_DATA_DIR']) ?? File(backendExe).parent.path;
      return BackendLocation(
        executable: backendExe,
        scriptPath: null,
        baseDir: baseDir,
      );
    }

    // Packaged layout (Phase 6): the frozen backend sits in `backend\` next to
    // the app executable, and the JSON data files live next to the app.
    final File? packaged = _findPackagedBackend();
    if (packaged != null) {
      final String baseDir = _nonEmpty(env['RH_DATA_DIR']) ??
          File(Platform.resolvedExecutable).parent.path;
      return BackendLocation(
        executable: packaged.path,
        scriptPath: null,
        baseDir: baseDir,
      );
    }

    final File? script = _findScript(env);
    if (script == null) {
      throw const BackendStartupException(
        '找不到后端脚本 backend/main.py。\n'
        '开发模式下请从仓库根目录或 app/ 目录启动，'
        '或设置环境变量 RH_BACKEND_SCRIPT。',
      );
    }
    final String baseDir =
        _nonEmpty(env['RH_DATA_DIR']) ?? script.parent.parent.path;

    final String? python = _findPython(env);
    if (python == null) {
      throw const BackendStartupException(
        '找不到可用的 Python 解释器（需要 3.11 及以上）。\n'
        '请安装 Python，或设置环境变量 RH_PYTHON 指向解释器路径。',
      );
    }
    return BackendLocation(
      executable: python,
      scriptPath: script.path,
      baseDir: baseDir,
    );
  }

  /// Starts the backend and completes `app.hello`.
  static Future<BackendConnection> connect({
    Duration timeout = const Duration(seconds: 20),
  }) async {
    final BackendLocation location = locate();
    final BackendClient client;
    try {
      client = await BackendClient.start(
        executable: location.executable,
        scriptPath: location.scriptPath,
        baseDir: location.baseDir,
        timeout: timeout,
      );
    } on ProcessException catch (error) {
      throw BackendStartupException(
        '无法启动后端进程：${error.message}\n${location.executable}',
      );
    }

    final BackendRepository repository = BackendRepository(client);
    try {
      final BackendHello hello = await repository.hello();
      if (hello.protocolVersion != 1) {
        throw BackendStartupException(
          '后端协议版本不匹配：期望 1，实际 ${hello.protocolVersion}。',
        );
      }
      return BackendConnection(
        repository: repository,
        hello: hello,
        executable: location.executable,
      );
    } on BackendStartupException {
      await client.close();
      rethrow;
    } catch (error) {
      await client.close();
      throw BackendStartupException('后端未响应 app.hello：$error');
    }
  }

  static String? _nonEmpty(String? value) {
    final String? trimmed = value?.trim();
    return (trimmed == null || trimmed.isEmpty) ? null : trimmed;
  }

  static File? _findScript(Map<String, String> env) {
    final String? explicit = _nonEmpty(env['RH_BACKEND_SCRIPT']);
    if (explicit != null && File(explicit).existsSync()) {
      return File(explicit);
    }
    final List<String> candidates = <String>[
      'backend/main.py',
      '../backend/main.py',
    ];
    for (final String candidate in candidates) {
      final File file = File(candidate);
      if (file.existsSync()) {
        return file.absolute;
      }
    }
    // Packaged builds sit next to the executable rather than the sources.
    final String exeDir = File(Platform.resolvedExecutable).parent.path;
    for (final String candidate in <String>['backend/main.py', '../backend/main.py']) {
      final File file = File('$exeDir${Platform.pathSeparator}$candidate');
      if (file.existsSync()) {
        return file;
      }
    }
    return null;
  }

  static String? _findPython(Map<String, String> env) {
    final String? explicit = _nonEmpty(env['RH_PYTHON']);
    if (explicit != null) {
      return explicit;
    }
    for (final String candidate in <String>['python', 'py', 'python3']) {
      try {
        final ProcessResult result =
            Process.runSync(candidate, <String>['--version']);
        if (result.exitCode == 0) {
          return candidate;
        }
      } on ProcessException {
        continue;
      }
    }
    return null;
  }

  /// Frozen backend shipped inside the release folder (`backend\` sub-directory
  /// or directly next to the executable).
  static File? _findPackagedBackend() {
    final String exeDir = File(Platform.resolvedExecutable).parent.path;
    final String separator = Platform.pathSeparator;
    const String name = 'resource_hub_backend.exe';
    for (final String candidate in <String>[
      '$exeDir${separator}backend$separator$name',
      '$exeDir$separator$name',
    ]) {
      final File file = File(candidate);
      if (file.existsSync()) {
        return file;
      }
    }
    return null;
  }
}
