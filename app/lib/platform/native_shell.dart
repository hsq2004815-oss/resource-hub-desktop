/// Native shell features that have no pub package: file dialogs, drag & drop and
/// the Windows Startup shortcut.
///
/// All of it lives in `windows/runner` behind the existing `resource_hub/window`
/// method channel (see ADR-002), so the release build stays plugin-free and the
/// UI keeps working in widget tests where the channel is absent.
library;

import 'dart:async';

import 'package:flutter/services.dart';

abstract final class NativeShell {
  static const MethodChannel _channel = MethodChannel('resource_hub/window');
  static final StreamController<List<String>> _drops =
      StreamController<List<String>>.broadcast();
  static final StreamController<void> _quickDismissals =
      StreamController<void>.broadcast();
  static final StreamController<String> _addFolderRequests =
      StreamController<String>.broadcast();
  static bool _handlerInstalled = false;

  /// Paths dropped onto the window (files and directories, already absolute).
  static Stream<List<String>> get drops {
    _installHandler();
    return _drops.stream;
  }

  /// Phase 16: the runner asks for the quick panel to close — the window lost
  /// focus, the tray icon was clicked, a second instance woke the app, or Alt+F4
  /// was pressed. [WindowControl] only sends commands; this is the matching
  /// incoming side and keeps the channel's single message handler here.
  static Stream<void> get quickDismissals {
    _installHandler();
    return _quickDismissals.stream;
  }

  /// Phase 19: an Explorer context-menu entry (or a CLI launch) asks to add
  /// [path] as a folder resource. The runner buffers it until [shellAddReady].
  static Stream<String> get addFolderRequests {
    _installHandler();
    return _addFolderRequests.stream;
  }

  /// Tells the runner that the add-folder listener is attached, so it can flush
  /// a path that arrived before the Flutter UI was ready.
  static Future<void> shellAddReady() => _invoke<void>('shellAddReady');

  static Future<bool> setShellContextMenuEnabled(bool enabled) async =>
      await _invoke<bool>('setShellContextMenuEnabled', enabled) ?? false;

  static Future<bool> isShellContextMenuEnabled() async =>
      await _invoke<bool>('isShellContextMenuEnabled') ?? false;

  static Future<String?> pickFolder() => _invoke<String>('pickFolder');

  /// Any file, for the form's "browse file" button.
  static Future<String?> pickFile() => _invoke<String>('pickFile');

  /// JSON only, for the import dialog.
  static Future<String?> pickJsonFile() => _invoke<String>('pickJsonFile');

  static Future<String?> saveJsonFile({required String suggestedName}) =>
      _invoke<String>('saveFile', <String, String>{
        'suggestedName': suggestedName,
      });

  static Future<bool> setLaunchAtStartup(bool enabled) async =>
      await _invoke<bool>('setLaunchAtStartup', enabled) ?? false;

  static Future<bool> isLaunchAtStartup() async =>
      await _invoke<bool>('isLaunchAtStartup') ?? false;

  /// Opens a URL / file / folder with the default shell handler.
  ///
  /// Returns false when the runner is unavailable (widget tests, non-Windows)
  /// or the shell rejected the target, so callers can fall back to the Python
  /// backend. Doing this in the runner keeps the foreground hand-off correct:
  /// Explorer and browsers then open in front of the app instead of behind it.
  static Future<bool> openTarget(String target) async =>
      await _invoke<bool>('openTarget', target) ?? false;

  /// Opens the containing folder and selects [path] in Explorer.
  static Future<bool> revealPath(String path) async =>
      await _invoke<bool>('revealPath', path) ?? false;

  static void _installHandler() {
    if (_handlerInstalled) {
      return;
    }
    _handlerInstalled = true;
    _channel.setMethodCallHandler((MethodCall call) async {
      if (call.method == 'quickDismissed') {
        _quickDismissals.add(null);
        return null;
      }
      if (call.method == 'addFolderPath') {
        final Object? path = call.arguments;
        if (path is String && path.isNotEmpty) {
          _addFolderRequests.add(path);
        }
        return null;
      }
      if (call.method != 'dropPaths') {
        return null;
      }
      final Object? arguments = call.arguments;
      final List<String> paths = arguments is List
          ? arguments.whereType<String>().toList(growable: false)
          : <String>[];
      if (paths.isNotEmpty) {
        _drops.add(paths);
      }
      return null;
    });
  }

  static Future<T?> _invoke<T>(String method, [Object? arguments]) async {
    try {
      return await _channel.invokeMethod<T>(method, arguments);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      // Shell actions are optional; a broken dialog must not break the UI.
      return null;
    }
  }
}
