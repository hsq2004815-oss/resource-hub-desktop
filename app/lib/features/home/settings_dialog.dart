/// Settings dialog.
///
/// Language and theme are live. The global-hotkey switch, the hotkey recorder
/// and launch-at-startup persist through [onSettingsChanged]; recording stops
/// the backend hotkey first so pressing the current combination cannot toggle
/// the window mid-recording (legacy recorded while the hotkey stayed active).
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../data/backend_repository.dart';
import '../../design/app_tokens.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../util/hotkeys.dart';
import '../../widgets/app_button.dart';
import '../../widgets/app_fields.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({
    super.key,
    required this.language,
    required this.themeMode,
    required this.settings,
    required this.onLanguageChanged,
    required this.onThemeModeChanged,
    required this.onSettingsChanged,
    required this.onProbeHotkey,
    required this.onHotkeyRecordingChanged,
  });

  final AppLanguage language;
  final ThemeMode themeMode;
  final AppSettings settings;
  final ValueChanged<AppLanguage> onLanguageChanged;
  final ValueChanged<ThemeMode> onThemeModeChanged;
  final Future<void> Function(AppSettings settings) onSettingsChanged;

  /// Asks the backend whether the recorded combination can be registered.
  final Future<bool> Function(String hotkeyId) onProbeHotkey;

  /// Stops (`true`) / restarts (`false`) the backend hotkey around recording.
  final Future<void> Function(bool recording) onHotkeyRecordingChanged;

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late AppSettings _settings = widget.settings;
  final FocusNode _hotkeyFocus = FocusNode(debugLabel: 'hotkey-recorder');
  bool _recording = false;
  String? _hotkeyError;

  // The dialog route is not rebuilt by HomePage when the app-level theme/language
  // change, so the *selection* must not come from the constructor snapshot:
  // SegmentedButton ignores taps on the already-selected segment, which made
  // "switch to English, then back to Chinese" a one-way trip.
  late ThemeMode _themeMode = widget.themeMode;

  @override
  void dispose() {
    if (_recording) {
      unawaited(widget.onHotkeyRecordingChanged(false));
    }
    _hotkeyFocus.dispose();
    super.dispose();
  }

  void _changeLanguage(AppLanguage language) {
    // Compare against the *current* ambient language, not `widget.language`:
    // that constructor prop is the value captured when the dialog was opened and
    // goes stale as soon as the language changes once.
    if (language == context.l10n.language) {
      return;
    }
    // The ambient AppStringsScope rebuilds this dialog with the new table.
    widget.onLanguageChanged(language);
  }

  void _changeThemeMode(ThemeMode mode) {
    if (mode == _themeMode) {
      return;
    }
    setState(() => _themeMode = mode);
    widget.onThemeModeChanged(mode);
  }

  Future<void> _apply(AppSettings next) async {
    setState(() => _settings = next);
    await widget.onSettingsChanged(next);
  }

  Future<void> _startRecording() async {
    if (_recording || !_settings.globalHotkeyEnabled) {
      return;
    }
    setState(() {
      _recording = true;
      _hotkeyError = null;
    });
    await widget.onHotkeyRecordingChanged(true);
    _hotkeyFocus.requestFocus();
  }

  Future<void> _cancelRecording() async {
    if (!_recording) {
      return;
    }
    setState(() => _recording = false);
    await widget.onHotkeyRecordingChanged(false);
  }

  /// Handles one key press while recording. Runs asynchronously because probing
  /// availability is a backend round-trip; the Focus callback below swallows the
  /// key event itself so no shortcut fires.
  Future<void> _captureKey(KeyEvent event) async {
    final AppStrings t = context.l10n;
    final LogicalKeyboardKey key = event.logicalKey;
    if (key == LogicalKeyboardKey.escape) {
      await _cancelRecording();
      return;
    }
    final String? keyName = hotkeyKeyName(key);
    if (keyName == null) {
      // A bare modifier press is not a combination; wait for the real key.
      return;
    }
    final List<String> modifiers = hotkeyModifiers();
    if (modifiers.isEmpty) {
      setState(() => _hotkeyError = t.t('hotkey_invalid'));
      return;
    }
    final String label = formatHotkey(modifiers, keyName);
    bool available;
    try {
      available = await widget.onProbeHotkey(label);
    } catch (_) {
      available = false;
    }
    if (!mounted) {
      return;
    }
    if (!available) {
      setState(() => _hotkeyError = t.t('hotkey_in_use', <Object?>[label]));
      return;
    }
    setState(() {
      _recording = false;
      _hotkeyError = null;
      _settings = _settings.copyWith(globalHotkeyId: label);
    });
    // The parent saves the settings and re-registers the hotkey.
    await widget.onSettingsChanged(_settings);
  }

  KeyEventResult _onKeyEvent(FocusNode node, KeyEvent event) {
    if (!_recording) {
      return KeyEventResult.ignored;
    }
    if (event is KeyDownEvent) {
      unawaited(_captureKey(event));
    }
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;

    return Focus(
      focusNode: _hotkeyFocus,
      onKeyEvent: _onKeyEvent,
      child: Dialog(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.xxl,
                  AppSpacing.xl,
                  AppSpacing.md,
                  AppSpacing.md,
                ),
                child: Row(
                  children: <Widget>[
                    Icon(Icons.settings_outlined,
                        size: 20, color: scheme.primary),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(t.t('settings_title'), style: text.titleLarge),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, size: 18),
                      splashRadius: 18,
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
              ),
              Divider(height: 1, color: scheme.outlineVariant),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(AppSpacing.xxl),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      _FieldLabel(text: t.t('settings_language')),
                      SegmentedButton<AppLanguage>(
                        segments: const <ButtonSegment<AppLanguage>>[
                          ButtonSegment<AppLanguage>(
                            value: AppLanguage.zh,
                            label: Text('简体中文'),
                          ),
                          ButtonSegment<AppLanguage>(
                            value: AppLanguage.en,
                            label: Text('English'),
                          ),
                        ],
                        selected: <AppLanguage>{t.language},
                        showSelectedIcon: false,
                        onSelectionChanged: (Set<AppLanguage> value) =>
                            _changeLanguage(value.first),
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      _FieldLabel(text: t.tx('settings_theme')),
                      SegmentedButton<ThemeMode>(
                        segments: <ButtonSegment<ThemeMode>>[
                          ButtonSegment<ThemeMode>(
                            value: ThemeMode.light,
                            icon: const Icon(Icons.light_mode_outlined,
                                size: 15),
                            label: Text(t.tx('theme_light')),
                          ),
                          ButtonSegment<ThemeMode>(
                            value: ThemeMode.system,
                            icon: const Icon(Icons.brightness_auto_outlined,
                                size: 15),
                            label: Text(t.tx('theme_system')),
                          ),
                          ButtonSegment<ThemeMode>(
                            value: ThemeMode.dark,
                            icon:
                                const Icon(Icons.dark_mode_outlined, size: 15),
                            label: Text(t.tx('theme_dark')),
                          ),
                        ],
                        selected: <ThemeMode>{_themeMode},
                        showSelectedIcon: false,
                        onSelectionChanged: (Set<ThemeMode> value) =>
                            _changeThemeMode(value.first),
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(t.t('settings_hotkey'),
                                    style: text.bodyMedium),
                                const SizedBox(height: 2),
                                Text(
                                  t.t('settings_hotkey_hint'),
                                  style: text.bodySmall?.copyWith(
                                    color: scheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: _settings.globalHotkeyEnabled,
                            onChanged: (bool value) {
                              if (_recording) {
                                unawaited(_cancelRecording());
                              }
                              unawaited(
                                _apply(
                                  _settings.copyWith(
                                    globalHotkeyEnabled: value,
                                  ),
                                ),
                              );
                            },
                          ),
                        ],
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: AppReadonlyValue(
                              label: t.t('settings_hotkey_enabled'),
                              value: _settings.globalHotkeyEnabled
                                  ? _settings.globalHotkeyId
                                  : '—',
                              icon: Icons.keyboard_outlined,
                            ),
                          ),
                          const SizedBox(width: AppSpacing.sm),
                          AppButton(
                            label: _recording
                                ? t.t('settings_hotkey_recording')
                                : t.t('settings_hotkey_record'),
                            icon: _recording
                                ? Icons.fiber_manual_record
                                : Icons.keyboard_alt_outlined,
                            variant: _recording
                                ? AppButtonVariant.danger
                                : AppButtonVariant.secondary,
                            compact: true,
                            onPressed: _settings.globalHotkeyEnabled
                                ? (_recording
                                    ? () => unawaited(_cancelRecording())
                                    : () => unawaited(_startRecording()))
                                : null,
                          ),
                        ],
                      ),
                      if (_hotkeyError != null) ...<Widget>[
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          _hotkeyError!,
                          style: text.bodySmall?.copyWith(color: scheme.error),
                        ),
                      ] else if (_recording) ...<Widget>[
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          t.t('settings_hotkey_recording'),
                          style: text.bodySmall?.copyWith(color: scheme.primary),
                        ),
                      ],
                      const SizedBox(height: AppSpacing.xl),
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(t.t('settings_startup'),
                                    style: text.bodyMedium),
                                const SizedBox(height: 2),
                                Text(
                                  t.t('settings_startup_note'),
                                  style: text.bodySmall?.copyWith(
                                    color: scheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: _settings.launchAtStartup,
                            onChanged: (bool value) => unawaited(
                              _apply(
                                _settings.copyWith(launchAtStartup: value),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs),
      child: Text(
        text,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      ),
    );
  }
}
