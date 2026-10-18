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

import '../../data/backend_models.dart';
import '../../data/backend_repository.dart';
import '../../design/app_tokens.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../util/hotkeys.dart';
import '../../widgets/app_button.dart';
import '../../widgets/app_fields.dart';

/// Which recorder row is currently capturing a key combination.
enum _HotkeyField { toggle, quickLinks, quickFolders }

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
    this.onLoadBookmarkStatus,
    this.onSyncBookmarks,
    this.onPickBookmarkDir,
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

  /// Phase 17: watched browser profiles / last bookmark sync state.
  final Future<BookmarkStatus?> Function()? onLoadBookmarkStatus;

  /// Phase 17: manual bookmark sync; null when the feature is unavailable.
  final Future<BookmarkSyncResult?> Function()? onSyncBookmarks;

  /// Phase 17: choose a custom browser data directory.
  final Future<String?> Function()? onPickBookmarkDir;

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late AppSettings _settings = widget.settings;
  final FocusNode _hotkeyFocus = FocusNode(debugLabel: 'hotkey-recorder');
  _HotkeyField? _recordingField;
  _HotkeyField? _errorField;
  String? _hotkeyError;

  BookmarkStatus? _bookmarkStatus;
  bool _bookmarkStatusLoading = false;
  bool _bookmarkSyncing = false;
  String? _bookmarkResult;

  // The dialog route is not rebuilt by HomePage when the app-level theme/language
  // change, so the *selection* must not come from the constructor snapshot:
  // SegmentedButton ignores taps on the already-selected segment, which made
  // "switch to English, then back to Chinese" a one-way trip.
  late ThemeMode _themeMode = widget.themeMode;

  @override
  void initState() {
    super.initState();
    unawaited(_loadBookmarkStatus());
  }

  Future<void> _loadBookmarkStatus() async {
    final Future<BookmarkStatus?> Function()? loader =
        widget.onLoadBookmarkStatus;
    if (loader == null) {
      return;
    }
    setState(() => _bookmarkStatusLoading = true);
    final BookmarkStatus? status = await loader();
    if (!mounted) {
      return;
    }
    setState(() {
      _bookmarkStatus = status;
      _bookmarkStatusLoading = false;
    });
  }

  Future<void> _syncBookmarksNow() async {
    final Future<BookmarkSyncResult?> Function()? sync =
        widget.onSyncBookmarks;
    if (sync == null || _bookmarkSyncing) {
      return;
    }
    final AppStrings t = context.l10n;
    setState(() {
      _bookmarkSyncing = true;
      _bookmarkResult = null;
    });
    final BookmarkSyncResult? result = await sync();
    if (!mounted) {
      return;
    }
    setState(() {
      _bookmarkSyncing = false;
      _bookmarkResult = result == null
          ? null
          : t.tx('settings_bookmarks_result', <Object?>[
              result.added,
              result.skipped,
            ]);
    });
    await _loadBookmarkStatus();
  }

  Future<void> _pickBookmarkDir() async {
    final Future<String?> Function()? pick = widget.onPickBookmarkDir;
    if (pick == null) {
      return;
    }
    final String? path = await pick();
    if (path == null || path.isEmpty || !mounted) {
      return;
    }
    await _apply(_settings.copyWith(bookmarkCustomDir: path));
    await _loadBookmarkStatus();
  }

  Future<void> _clearBookmarkDir() async {
    await _apply(_settings.copyWith(bookmarkCustomDir: ''));
    await _loadBookmarkStatus();
  }

  @override
  void dispose() {
    if (_recordingField != null) {
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

  Future<void> _startRecording(_HotkeyField field) async {
    if (_recordingField != null || !_settings.globalHotkeyEnabled) {
      return;
    }
    setState(() {
      _recordingField = field;
      _errorField = null;
      _hotkeyError = null;
    });
    await widget.onHotkeyRecordingChanged(true);
    _hotkeyFocus.requestFocus();
  }

  Future<void> _cancelRecording() async {
    if (_recordingField == null) {
      return;
    }
    setState(() => _recordingField = null);
    await widget.onHotkeyRecordingChanged(false);
  }

  List<String> _otherHotkeyIds(_HotkeyField field) => <String>[
        if (field != _HotkeyField.toggle) _settings.globalHotkeyId,
        if (field != _HotkeyField.quickLinks) _settings.quickLinksHotkeyId,
        if (field != _HotkeyField.quickFolders) _settings.quickFoldersHotkeyId,
      ];

  /// Handles one key press while recording. Runs asynchronously because probing
  /// availability is a backend round-trip; the Focus callback below swallows the
  /// key event itself so no shortcut fires.
  Future<void> _captureKey(KeyEvent event) async {
    final _HotkeyField? field = _recordingField;
    if (field == null) {
      return;
    }
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
      setState(() {
        _errorField = field;
        _hotkeyError = t.t('hotkey_invalid');
      });
      return;
    }
    final String label = formatHotkey(modifiers, keyName);
    // The three actions are registered independently; using one combination for
    // two of them would make the second registration fail silently.
    if (_otherHotkeyIds(field).contains(label)) {
      setState(() {
        _errorField = field;
        _hotkeyError = t.tx('hotkey_duplicate');
      });
      return;
    }
    bool available;
    try {
      available = await widget.onProbeHotkey(label);
    } catch (_) {
      available = false;
    }
    if (!mounted || _recordingField != field) {
      return;
    }
    if (!available) {
      setState(() {
        _errorField = field;
        _hotkeyError = t.t('hotkey_in_use', <Object?>[label]);
      });
      return;
    }
    final AppSettings next = switch (field) {
      _HotkeyField.toggle => _settings.copyWith(globalHotkeyId: label),
      _HotkeyField.quickLinks => _settings.copyWith(quickLinksHotkeyId: label),
      _HotkeyField.quickFolders =>
        _settings.copyWith(quickFoldersHotkeyId: label),
    };
    setState(() {
      _recordingField = null;
      _errorField = null;
      _hotkeyError = null;
      _settings = next;
    });
    // The parent saves the settings and re-registers the hotkeys.
    await widget.onSettingsChanged(next);
  }

  KeyEventResult _onKeyEvent(FocusNode node, KeyEvent event) {
    if (_recordingField == null) {
      return KeyEventResult.ignored;
    }
    if (event is KeyDownEvent) {
      unawaited(_captureKey(event));
    }
    return KeyEventResult.handled;
  }

  /// One recorder row: current combination + record/cancel button. Shared by the
  /// full-window hotkey and the two quick-panel hotkeys (Phase 16).
  Widget _hotkeyRow(
    BuildContext context, {
    required _HotkeyField field,
    required String label,
    required String value,
  }) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final bool recording = _recordingField == field;
    final bool showError = _errorField == field && _hotkeyError != null;
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: AppReadonlyValue(
                  label: label,
                  value: _settings.globalHotkeyEnabled ? value : '—',
                  icon: Icons.keyboard_outlined,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              AppButton(
                label: recording
                    ? t.t('settings_hotkey_recording')
                    : t.t('settings_hotkey_record'),
                icon: recording
                    ? Icons.fiber_manual_record
                    : Icons.keyboard_alt_outlined,
                variant: recording
                    ? AppButtonVariant.danger
                    : AppButtonVariant.secondary,
                compact: true,
                onPressed: _settings.globalHotkeyEnabled
                    ? (recording
                        ? () => unawaited(_cancelRecording())
                        : () => unawaited(_startRecording(field)))
                    : null,
              ),
            ],
          ),
          if (showError) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              _hotkeyError!,
              style: text.bodySmall?.copyWith(color: scheme.error),
            ),
          ] else if (recording) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              t.t('settings_hotkey_recording'),
              style: text.bodySmall?.copyWith(color: scheme.primary),
            ),
          ],
        ],
      ),
    );
  }

  /// Phase 17: browser-bookmark bridge block (switch, optional custom dir and a
  /// manual sync button with inline result).
  Widget _buildBookmarkSection(
    BuildContext context,
    AppStrings t,
    ColorScheme scheme,
    TextTheme text,
  ) {
    final BookmarkStatus? status = _bookmarkStatus;
    final String statusText;
    if (_bookmarkStatusLoading && status == null) {
      statusText = t.tx('settings_bookmarks_loading');
    } else if (status == null || status.profiles.isEmpty) {
      statusText = t.tx('settings_bookmarks_none');
    } else {
      final String last = status.lastSyncAt ?? t.tx('settings_bookmarks_never');
      statusText = '${t.tx('settings_bookmarks_detected', <Object?>[
        status.profiles.length,
        status.totalBookmarks,
      ])} · ${t.tx('settings_bookmarks_last_sync', <Object?>[last])}';
    }
    final bool hasCustomDir = _settings.bookmarkCustomDir.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(t.tx('settings_bookmarks_title'),
                      style: text.bodyMedium),
                  const SizedBox(height: 2),
                  Text(
                    t.tx('settings_bookmarks_hint'),
                    style: text.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Switch(
              key: const ValueKey<String>('bookmark-sync-switch'),
              value: _settings.bookmarkSyncEnabled,
              onChanged: (bool value) => unawaited(
                _apply(_settings.copyWith(bookmarkSyncEnabled: value)),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: <Widget>[
            Expanded(
              child: AppReadonlyValue(
                label: t.tx('settings_bookmarks_dir'),
                value: hasCustomDir
                    ? _settings.bookmarkCustomDir
                    : t.tx('settings_bookmarks_dir_auto'),
                icon: Icons.bookmarks_outlined,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            AppButton(
              label: t.tx('settings_bookmarks_pick'),
              icon: Icons.folder_open_outlined,
              variant: AppButtonVariant.secondary,
              compact: true,
              onPressed: widget.onPickBookmarkDir == null
                  ? null
                  : () => unawaited(_pickBookmarkDir()),
            ),
            if (hasCustomDir) ...<Widget>[
              const SizedBox(width: AppSpacing.xs),
              IconButton(
                tooltip: t.tx('settings_bookmarks_clear'),
                icon: const Icon(Icons.clear, size: 16),
                visualDensity: VisualDensity.compact,
                onPressed: () => unawaited(_clearBookmarkDir()),
              ),
            ],
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                statusText,
                style: text.bodySmall?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            AppButton(
              label: _bookmarkSyncing
                  ? t.tx('settings_bookmarks_syncing')
                  : t.tx('settings_bookmarks_sync_now'),
              icon: Icons.sync,
              variant: AppButtonVariant.secondary,
              compact: true,
              onPressed: _bookmarkSyncing || widget.onSyncBookmarks == null
                  ? null
                  : () => unawaited(_syncBookmarksNow()),
            ),
          ],
        ),
        if (_bookmarkResult != null) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          Text(
            _bookmarkResult!,
            style: text.bodySmall?.copyWith(color: scheme.primary),
          ),
        ],
      ],
    );
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
                              if (_recordingField != null) {
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
                      _hotkeyRow(
                        context,
                        field: _HotkeyField.toggle,
                        label: t.t('settings_hotkey_enabled'),
                        value: _settings.globalHotkeyId,
                      ),
                      const SizedBox(height: AppSpacing.lg),
                      Text(
                        t.tx('settings_quick_title'),
                        style: text.labelMedium?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        t.tx('settings_quick_hint'),
                        style: text.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                      _hotkeyRow(
                        context,
                        field: _HotkeyField.quickLinks,
                        label: t.tx('settings_quick_links'),
                        value: _settings.quickLinksHotkeyId,
                      ),
                      _hotkeyRow(
                        context,
                        field: _HotkeyField.quickFolders,
                        label: t.tx('settings_quick_folders'),
                        value: _settings.quickFoldersHotkeyId,
                      ),
                      const SizedBox(height: AppSpacing.xl),
                      _buildBookmarkSection(context, t, scheme, text),
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
