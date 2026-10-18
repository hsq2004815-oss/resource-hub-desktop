/// Resource Hub — Flutter desktop client.
///
/// Boot order: start the Python backend -> `app.hello` -> load settings ->
/// register the global hotkey -> render the shell. Failures land on a retry
/// screen instead of a white window.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'data/backend_bootstrap.dart';
import 'data/backend_repository.dart';
import 'design/app_theme.dart';
import 'design/app_tokens.dart';
import 'features/home/home_page.dart';
import 'l10n/app_strings_ext.dart';
import 'l10n/strings_scope.dart';
import 'platform/native_shell.dart';
import 'platform/window_control.dart';
import 'widgets/app_button.dart';

void main() {
  runApp(const ResourceHubApp());
}

/// Screenshot / QA hook.
///
/// `RH_THEME=light|dark|system` and `RH_LANG=zh|en` set the initial state so a
/// single release build can produce reference screenshots for every variant
/// without driving the UI with synthetic input. Unset means the defaults below.
abstract final class InitialUiState {
  static ThemeMode get themeMode {
    return switch (Platform.environment['RH_THEME']?.trim().toLowerCase()) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => ThemeMode.system,
    };
  }

  static AppLanguage? get languageOverride {
    final String? code = Platform.environment['RH_LANG']?.trim();
    if (code == null || code.isEmpty) {
      return null;
    }
    return AppLanguage.fromCode(code);
  }
}

class ResourceHubApp extends StatefulWidget {
  const ResourceHubApp({super.key});

  @override
  State<ResourceHubApp> createState() => _ResourceHubAppState();
}

class _ResourceHubAppState extends State<ResourceHubApp> {
  late AppLanguage _language = InitialUiState.languageOverride ?? AppLanguage.zh;
  late ThemeMode _themeMode = InitialUiState.themeMode;

  Future<BackendConnection>? _pending;
  BackendConnection? _connection;
  AppSettings _settings = const AppSettings();
  HotkeyStatus? _hotkey;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  void _boot() {
    setState(() => _pending = _startBackend());
  }

  /// Keeps the native window title and tray menu in the active language.
  void _syncWindowStrings(AppLanguage language) {
    final AppStrings strings = AppStrings(language);
    WindowControl.setTitle(strings.tx('window_title'));
    WindowControl.setTrayLabels(
      toggle: strings.t('tray_toggle'),
      exit: strings.t('tray_exit'),
    );
  }

  Future<BackendConnection> _startBackend() async {
    final BackendConnection connection = await BackendBootstrap.connect();
    final AppSettings settings = await connection.repository.loadSettings();
    _settings = settings;
    if (mounted) {
      final AppLanguage language = InitialUiState.languageOverride ??
          AppLanguage.fromCode(settings.language);
      _connection = connection;
      if (language != _language) {
        setState(() => _language = language);
      }
    }
    // Registering the hotkey is best-effort: a taken combination must not block
    // startup, the status bar reports it instead.
    try {
      final HotkeyStatus status = await connection.repository.startHotkey();
      if (mounted) {
        setState(() => _hotkey = status);
      }
    } catch (_) {
      // Ignored on purpose; see above.
    }
    // Repair a missing Startup shortcut, but never delete one on boot: the
    // packaged app may legitimately be started from a different build.
    if (settings.launchAtStartup) {
      unawaited(NativeShell.setLaunchAtStartup(true));
    }
    // Phase 19: the Explorer context-menu entry is owned by the runner (HKCU).
    unawaited(NativeShell.setShellContextMenuEnabled(
      settings.shellContextMenuEnabled,
    ));
    return connection;
  }

  void _setThemeMode(ThemeMode mode) {
    if (mode == _themeMode) {
      return;
    }
    setState(() => _themeMode = mode);
  }

  Future<void> _applySettings(AppSettings next) async {
    final BackendConnection? connection = _connection;
    if (connection == null) {
      return;
    }
    final AppSettings saved = await connection.repository.saveSettings(next);
    if (!mounted) {
      return;
    }
    setState(() {
      _settings = saved;
      _language =
          InitialUiState.languageOverride ?? AppLanguage.fromCode(saved.language);
    });
    _syncWindowStrings(_language);
    // Settings are the source of truth for the Startup shortcut.
    unawaited(NativeShell.setLaunchAtStartup(saved.launchAtStartup));
    unawaited(NativeShell.setShellContextMenuEnabled(
      saved.shellContextMenuEnabled,
    ));
    try {
      final HotkeyStatus status = await connection.repository.startHotkey();
      if (mounted) {
        setState(() => _hotkey = status);
      }
    } catch (_) {
      // Best effort, as above.
    }
  }

  void _setLanguage(AppLanguage language) {
    if (language == _language) {
      return;
    }
    setState(() => _language = language);
    _syncWindowStrings(language);
    _applySettings(_settings.copyWith(language: language.code));
  }

  @override
  void dispose() {
    _connection?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AppStrings strings = AppStrings(_language);
    return AppStringsScope(
      strings: strings,
      onLanguageChanged: _setLanguage,
      child: MaterialApp(
        title: strings.tx('window_title'),
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: _themeMode,
        home: FutureBuilder<BackendConnection>(
          future: _pending,
          builder: (
            BuildContext context,
            AsyncSnapshot<BackendConnection> snapshot,
          ) {
            if (snapshot.connectionState != ConnectionState.done) {
              return _BootSplash(message: strings.tx('backend_connecting'));
            }
            if (snapshot.hasError || !snapshot.hasData) {
              return _BootFailure(
                title: strings.tx('backend_failed_title'),
                detail: '${snapshot.error ?? 'unknown error'}',
                hint: strings.tx('backend_failed_hint'),
                retryLabel: strings.tx('retry'),
                onRetry: _boot,
              );
            }
            return HomePage(
              api: snapshot.data!.repository,
              dataCorrupt: snapshot.data!.hello.isCorrupt,
              settings: _settings,
              hotkey: _hotkey,
              themeMode: _themeMode,
              onThemeModeChanged: _setThemeMode,
              onSettingsChanged: _applySettings,
            );
          },
        ),
      ),
    );
  }
}

class _BootSplash extends StatelessWidget {
  const _BootSplash({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: scheme.primary,
                borderRadius: AppRadius.mdAll,
              ),
              child: const Icon(
                Icons.dashboard_customize_outlined,
                color: Colors.white,
                size: 26,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            SizedBox(
              width: 180,
              child: LinearProgressIndicator(
                borderRadius: BorderRadius.circular(AppRadius.pill),
                minHeight: 4,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              message,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

class _BootFailure extends StatelessWidget {
  const _BootFailure({
    required this.title,
    required this.detail,
    required this.hint,
    required this.retryLabel,
    required this.onRetry,
  });

  final String title;
  final String detail;
  final String hint;
  final String retryLabel;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xxxl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(Icons.error_outline, size: 32, color: scheme.error),
                const SizedBox(height: AppSpacing.md),
                Text(title, style: text.titleLarge),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  hint,
                  style:
                      text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                ),
                const SizedBox(height: AppSpacing.md),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(AppSpacing.md),
                  decoration: BoxDecoration(
                    color: scheme.surfaceContainer,
                    borderRadius: AppRadius.smAll,
                    border: Border.all(color: scheme.outlineVariant),
                  ),
                  child: SelectableText(
                    detail,
                    style: text.bodySmall?.copyWith(
                      fontFamily: 'Consolas',
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.lg),
                AppButton(
                  label: retryLabel,
                  icon: Icons.refresh,
                  onPressed: onRetry,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
