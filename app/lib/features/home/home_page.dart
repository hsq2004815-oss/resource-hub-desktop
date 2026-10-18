/// Application shell, wired to the Python backend.
///
/// All persistence goes through [BackendRepository]; this widget owns view state
/// only (selection, filters, edit mode, status line). Filtering stays client-side
/// because the dataset is small and the list must feel instant — the backend's
/// `visible()` remains the reference implementation, covered by
/// `test_service.VisibleTests`.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../data/backend_models.dart';
import '../../data/resource_api.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../models/resource_item.dart';
import '../../platform/backend_client.dart';
import '../../platform/native_shell.dart';
import '../../platform/window_control.dart';
import '../../util/json_backup.dart';
import '../../widgets/app_button.dart';
import '../../widgets/resource_grid.dart';
import '../../widgets/resource_table.dart';
import '../../widgets/status_bar.dart';
import 'resource_detail_panel.dart';
import 'resource_form.dart';
import 'resource_list_panel.dart';
import 'settings_dialog.dart';

/// A status line message: either an i18n key with args, or literal text.
class _Status {
  const _Status({
    this.key,
    this.text,
    this.args = const <Object?>[],
    this.tone = StatusTone.info,
  });

  final String? key;
  final String? text;
  final List<Object?> args;
  final StatusTone tone;

  factory _Status.fromError(BackendException error) {
    final String? errorKey = error.key;
    if (errorKey != null) {
      return _Status(key: errorKey, tone: StatusTone.error);
    }
    return _Status(
      text: error.detail.isEmpty ? error.code : error.detail,
      tone: StatusTone.error,
    );
  }

  String resolve(AppStrings strings) {
    if (text != null) {
      return text!;
    }
    final String? messageKey = key;
    if (messageKey == null) {
      return '';
    }
    return strings.tx(messageKey, args);
  }
}

/// A manual ordering change that can be reverted from the status bar for a few
/// seconds. Kept as the previous id order so undo is just another reorder.
class _UndoAction {
  const _UndoAction({required this.mode, required this.ids});

  final ViewMode mode;
  final List<String> ids;
}

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.api,
    required this.dataCorrupt,
    required this.settings,
    required this.hotkey,
    required this.themeMode,
    required this.onThemeModeChanged,
    required this.onSettingsChanged,
  });

  final ResourceApi api;

  /// True when the backend could not parse the data files; the shell then runs
  /// read-only and says so.
  final bool dataCorrupt;
  final AppSettings settings;
  final HotkeyStatus? hotkey;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onThemeModeChanged;
  final Future<void> Function(AppSettings settings) onSettingsChanged;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final GlobalKey<ResourceFormState> _formKey = GlobalKey<ResourceFormState>();
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  final ScrollController _listScroll = ScrollController();
  StreamSubscription<BackendEvent>? _eventSubscription;
  StreamSubscription<List<String>>? _dropSubscription;
  HotkeyStatus? _hotkey;

  List<ResourceItem> _links = <ResourceItem>[];
  List<ResourceItem> _folders = <ResourceItem>[];
  final Map<String, PathState> _pathStates = <String, PathState>{};

  ViewMode _mode = ViewMode.folders;
  String? _selectedId;
  String _query = '';
  String _categoryFilter = kAllCategories;
  bool _favoritesOnly = false;
  ResourceLayout _layout = ResourceLayout.list;

  /// Right-hand details panel (Phase 9): opened by a completed row click,
  /// non-modal, width is remembered for the session.
  bool _detailOpen = false;
  double _detailWidth = 560;

  _Status? _status;
  _UndoAction? _undo;
  Timer? _undoTimer;
  bool _reorderSaving = false;
  bool _loading = true;
  String? _loadFailure;

  ResourceApi get _repo => widget.api;
  bool get _dataCorrupt => widget.dataCorrupt;

  /// Reordering (drag handles and Alt+Up/Down) needs a complete, unfiltered list:
  /// a sparse search result has no meaningful global positions.
  bool get _canReorder =>
      !_dataCorrupt &&
      !_loading &&
      !_reorderSaving &&
      _query.trim().isEmpty;

  @override
  void initState() {
    super.initState();
    _hotkey = widget.hotkey;
    // The backend owns the global hotkey; a press arrives as an event and the
    // window toggle happens here so the search box can take focus afterwards.
    _eventSubscription = widget.api.events.listen(_onBackendEvent);
    // Shell file drops arrive from the runner (WM_DROPFILES -> method channel).
    _dropSubscription = NativeShell.drops.listen(_handleDropPaths);
    _reloadAll();
  }

  @override
  void didUpdateWidget(HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.hotkey != widget.hotkey) {
      _hotkey = widget.hotkey;
    }
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
    _dropSubscription?.cancel();
    _search.dispose();
    _searchFocus.dispose();
    _listScroll.dispose();
    _undoTimer?.cancel();
    super.dispose();
  }

  Future<void> _onBackendEvent(BackendEvent event) async {
    if (event.name != 'hotkey') {
      return;
    }
    final bool visible = await WindowControl.toggle();
    if (visible && mounted) {
      _searchFocus.requestFocus();
    }
  }

  // -- shell integration (drag & drop, dialogs, import/export) -------------
  Future<void> _handleDropPaths(List<String> paths) async {
    if (paths.isEmpty) {
      return;
    }
    if (_dataCorrupt) {
      _setStatus(_Status(key: 'data_corrupt'));
      return;
    }
    try {
      final DropOutcome outcome = await _repo.drop(paths);
      if (!mounted) {
        return;
      }
      // A drop always writes to the folders collection, so following the
      // legacy app the shell switches from links to folders.
      final bool switched = _mode.isLinks &&
          (outcome.added > 0 || outcome.skipped > 0);
      if (switched) {
        setState(() {
          _mode = ViewMode.folders;
          _selectedId = null;
          _detailOpen = false;
          _categoryFilter = kAllCategories;
          _query = '';
          _search.clear();
        });
      }
      if (outcome.added > 0) {
        await _reload(ViewMode.folders);
        if (!mounted) {
          return;
        }
        if (outcome.skipped > 0) {
          _setStatus(
            _Status(
              key: 'drop_added_skipped',
              args: <Object?>[outcome.added, outcome.skipped],
              tone: StatusTone.success,
            ),
          );
        } else if (switched) {
          _setStatus(
            _Status(key: 'drop_switched', tone: StatusTone.success),
          );
        } else {
          _setStatus(
            _Status(
              key: 'drop_added',
              args: <Object?>[outcome.added],
              tone: StatusTone.success,
            ),
          );
        }
        return;
      }
      if (outcome.skipped > 0) {
        _setStatus(
          _Status(
            key: 'drop_added_skipped',
            args: <Object?>[0, outcome.skipped],
            tone: StatusTone.warning,
          ),
        );
        return;
      }
      _setStatus(_Status(key: 'drop_invalid', tone: StatusTone.warning));
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<void> _browseFolder() async {
    final String? path = await NativeShell.pickFolder();
    if (path == null || path.isEmpty) {
      return;
    }
    _formKey.currentState?.setPath(path);
  }

  Future<void> _browseFile() async {
    final String? path = await NativeShell.pickFile();
    if (path == null || path.isEmpty) {
      return;
    }
    _formKey.currentState?.setPath(path);
  }

  Future<void> _exportCollection() async {
    if (_dataCorrupt) {
      _setStatus(_Status(key: 'data_corrupt'));
      return;
    }
    final bool isLinks = _mode.isLinks;
    final String? path = await NativeShell.saveJsonFile(
      suggestedName: isLinks ? 'sites-backup.json' : 'folders-backup.json',
    );
    if (path == null || path.isEmpty) {
      return;
    }
    try {
      await JsonBackup.write(path, await _repo.export(_mode));
      _setStatus(_Status(key: 'backup_exported', tone: StatusTone.success));
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    } catch (error) {
      _setStatus(_Status(text: '$error', tone: StatusTone.error));
    }
  }

  Future<void> _importCollection() async {
    if (_dataCorrupt) {
      _setStatus(_Status(key: 'data_corrupt'));
      return;
    }
    final String? path = await NativeShell.pickJsonFile();
    if (path == null || path.isEmpty) {
      return;
    }

    final List<Map<String, dynamic>> items;
    try {
      items = await JsonBackup.read(path);
    } catch (_) {
      _setStatus(_Status(key: 'import_failed', tone: StatusTone.error));
      return;
    }

    try {
      final ImportOutcome outcome = await _repo.import(_mode, items);
      await _reload(_mode);
      if (!mounted) {
        return;
      }
      setState(() {
        _selectedId = null;
        _detailOpen = false;
      });
      _setStatus(
        outcome.skipped > 0
            ? _Status(
                key: 'backup_imported_skipped',
                args: <Object?>[outcome.imported, outcome.skipped],
                tone: StatusTone.success,
              )
            : _Status(key: 'backup_imported', tone: StatusTone.success),
      );
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<bool> _probeHotkey(String hotkeyId) => widget.api.probeHotkey(hotkeyId);

  /// Stops the backend hotkey while the settings dialog records a new one, so
  /// pressing the current combination cannot toggle the window mid-recording.
  /// The restart happens through `onSettingsChanged` -> `startHotkey`.
  Future<void> _setHotkeyRecording(bool recording) async {
    try {
      if (recording) {
        await widget.api.stopHotkey();
        return;
      }
      final HotkeyStatus status = await widget.api.startHotkey();
      if (mounted) {
        setState(() => _hotkey = status);
      }
    } catch (_) {
      // Best effort: a failed hotkey operation must not break settings.
    }
  }

  // -- data ---------------------------------------------------------------
  Future<void> _reloadAll() async {
    if (_dataCorrupt) {
      setState(() => _loading = false);
      return;
    }
    await Future.wait<void>(<Future<void>>[
      _reload(ViewMode.links),
      _reload(ViewMode.folders),
    ]);
    if (mounted) {
      setState(() => _loading = false);
    }
  }

  Future<void> _reload(ViewMode mode) async {
    try {
      final ResourceListPage page = await _repo.list(mode);
      if (!mounted) {
        return;
      }
      setState(() {
        if (mode.isLinks) {
          _links = page.items;
        } else {
          _folders = page.items;
        }
      });
    } on BackendException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _status = _Status.fromError(error);
        _loadFailure = error.detail;
      });
    }
  }

  List<ResourceItem> get _current => _mode.isLinks ? _links : _folders;

  List<ResourceItem> get _visible {
    final String query = _query.trim().toLowerCase();
    final List<ResourceItem> filtered = _current
        .where((ResourceItem item) {
          if (_favoritesOnly && !item.favorite) {
            return false;
          }
          if (_categoryFilter != kAllCategories &&
              item.category != _categoryFilter) {
            return false;
          }
          if (query.isEmpty) {
            return true;
          }
          final String haystack = <String>[
            item.name,
            item.path,
            item.category,
            item.note,
            item.kind.name,
          ].join(' ').toLowerCase();
          return haystack.contains(query);
        })
        .map((ResourceItem item) {
          final PathState state = _pathStates[item.id] ?? PathState.unknown;
          return state == item.pathState
              ? item
              : item.copyWith(pathState: state);
        })
        .toList();
    // Phase 8: the stored order is the display order. Favourites are no longer
    // pinned, because the user can drag rows into any position.
    return filtered;
  }

  List<String> get _categories {
    final Set<String> found = <String>{
      for (final ResourceItem item in _current)
        if (item.category != kUncategorized) item.category,
    };
    return found.toList()..sort();
  }

  ResourceItem? get _selected {
    final String? id = _selectedId;
    if (id == null) {
      return null;
    }
    for (final ResourceItem item in _current) {
      if (item.id == id) {
        return item;
      }
    }
    return null;
  }

  void _setStatus(_Status status, {_UndoAction? undo}) {
    if (!mounted) {
      return;
    }
    _undoTimer?.cancel();
    _undoTimer = null;
    if (undo != null) {
      // Status-bar undo lives for five seconds; the next status replaces it.
      _undoTimer = Timer(const Duration(seconds: 5), () {
        if (mounted) {
          setState(() => _undo = null);
        }
      });
    }
    setState(() {
      _status = status;
      _undo = undo;
    });
  }

  // -- manual ordering -----------------------------------------------------
  static bool _sameOrder(List<String> a, List<String> b) {
    if (a.length != b.length) {
      return false;
    }
    for (int i = 0; i < a.length; i++) {
      if (a[i] != b[i]) {
        return false;
      }
    }
    return true;
  }

  /// Optimistically applies a new full-collection order and persists it.
  ///
  /// [ids] must be a permutation of the current collection ids; the backend
  /// rejects anything else, in which case the previous order is restored. The
  /// optimistic update keeps the dragged row under the pointer instead of
  /// waiting for a JSON round-trip.
  Future<bool> _applyOrder(
    ViewMode mode,
    List<String> ids, {
    required String successKey,
    bool allowUndo = true,
  }) async {
    if (_reorderSaving) {
      return false;
    }
    final List<ResourceItem> bucket = mode.isLinks ? _links : _folders;
    if (ids.length != bucket.length) {
      return false;
    }
    final List<String> before = <String>[for (final item in bucket) item.id];
    if (_sameOrder(before, ids)) {
      _setStatus(_Status(key: successKey, tone: StatusTone.success));
      return true;
    }
    final Map<String, ResourceItem> byId = <String, ResourceItem>{
      for (final ResourceItem item in bucket) item.id: item,
    };
    final List<ResourceItem> next = <ResourceItem>[
      for (final String id in ids)
        if (byId[id] != null) byId[id]!,
    ];
    if (next.length != bucket.length) {
      return false;
    }

    setState(() {
      _reorderSaving = true;
      if (mode.isLinks) {
        _links = next;
      } else {
        _folders = next;
      }
    });
    try {
      await _repo.reorder(mode, ids);
      if (!mounted) {
        return false;
      }
      setState(() => _reorderSaving = false);
      _setStatus(
        _Status(key: successKey, tone: StatusTone.success),
        undo: allowUndo ? _UndoAction(mode: mode, ids: before) : null,
      );
      return true;
    } on BackendException catch (error) {
      _restoreOrder(mode, bucket);
      _setStatus(_Status.fromError(error));
      return false;
    } catch (error) {
      _restoreOrder(mode, bucket);
      _setStatus(_Status(text: '$error', tone: StatusTone.error));
      return false;
    }
  }

  void _restoreOrder(ViewMode mode, List<ResourceItem> bucket) {
    if (!mounted) {
      return;
    }
    setState(() {
      _reorderSaving = false;
      if (mode.isLinks) {
        _links = bucket;
      } else {
        _folders = bucket;
      }
    });
  }

  /// Moves [item] to [targetIndex] of the visible list (index *after* removal)
  /// and translates that into a full-collection order.
  Future<void> _handleMoveItem(ResourceItem item, int targetIndex) async {
    if (!_canReorder) {
      return;
    }
    final List<ResourceItem> visible = _visible;
    final List<ResourceItem> remaining = <ResourceItem>[
      for (final ResourceItem entry in visible)
        if (entry.id != item.id) entry,
    ];
    final int clamped = targetIndex.clamp(0, remaining.length);
    final List<ResourceItem> full = <ResourceItem>[
      for (final ResourceItem entry in _current)
        if (entry.id != item.id) entry,
    ];
    if (remaining.isEmpty) {
      full.add(item);
    } else if (clamped >= remaining.length) {
      final int anchor = full.indexWhere(
        (ResourceItem entry) => entry.id == remaining.last.id,
      );
      full.insert(anchor + 1, item);
    } else {
      final int anchor = full.indexWhere(
        (ResourceItem entry) => entry.id == remaining[clamped].id,
      );
      full.insert(anchor, item);
    }
    final bool applied = await _applyOrder(
      _mode,
      <String>[for (final ResourceItem entry in full) entry.id],
      successKey: 'reorder_saved',
    );
    if (applied && mounted) {
      setState(() => _selectedId = item.id);
    }
  }

  /// Keyboard alternative to dragging: Alt+Up/Down moves the selected row one
  /// position at a time.
  Future<void> _moveSelected(int delta) async {
    if (!_canReorder) {
      return;
    }
    final ResourceItem? item = _selected;
    if (item == null) {
      return;
    }
    final int index = _visible.indexWhere(
      (ResourceItem entry) => entry.id == item.id,
    );
    if (index < 0) {
      return;
    }
    final int target = index + delta;
    if (target < 0 || target >= _visible.length) {
      return;
    }
    await _handleMoveItem(item, target);
  }

  /// One-shot "newest first" order from the overflow menu. Ties keep their
  /// current relative order so the result is deterministic.
  Future<void> _sortByAdded() async {
    if (_dataCorrupt || _reorderSaving) {
      return;
    }
    final List<ResourceItem> bucket = _current;
    final List<int> order = List<int>.generate(bucket.length, (int i) => i);
    order.sort((int a, int b) {
      final DateTime? left = bucket[a].createdAt;
      final DateTime? right = bucket[b].createdAt;
      if (left == null && right == null) {
        return a.compareTo(b);
      }
      if (left == null) {
        return 1;
      }
      if (right == null) {
        return -1;
      }
      final int byDate = right.compareTo(left);
      return byDate != 0 ? byDate : a.compareTo(b);
    });
    await _applyOrder(
      _mode,
      <String>[for (final int index in order) bucket[index].id],
      successKey: 'sort_by_added_done',
    );
  }

  Future<void> _undoOrder() async {
    final _UndoAction? undo = _undo;
    if (undo == null || _reorderSaving) {
      return;
    }
    _undoTimer?.cancel();
    _undoTimer = null;
    setState(() => _undo = null);
    await _applyOrder(
      undo.mode,
      undo.ids,
      successKey: 'reorder_undone',
      allowUndo: false,
    );
  }

  // -- mutations ----------------------------------------------------------
  /// Opens the add/edit form in a dialog.
  ///
  /// The form is the same [ResourceForm] the legacy layout kept permanently
  /// visible; only its presentation changed. All CRUD still goes through
  /// [_persistDraft] -> [ResourceApi], so the business layer is untouched.
  Future<void> _openEditor({ResourceItem? item}) async {
    if (_dataCorrupt) {
      _setStatus(_Status(key: 'data_corrupt'));
      return;
    }
    final List<String> categories = _categories;
    if (item != null) {
      setState(() => _selectedId = item.id);
      _setStatus(
        _Status(key: _mode.isLinks ? 'editing_link' : 'editing_folder'),
      );
    }

    final ResourceItem? saved = await showDialog<ResourceItem>(
      context: context,
      builder: (BuildContext dialogContext) {
        return Dialog(
          clipBehavior: Clip.antiAlias,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460, maxHeight: 680),
            child: ResourceForm(
              key: _formKey,
              mode: _mode,
              categories: categories,
              editing: item,
              onClose: () => Navigator.of(dialogContext).pop(),
              onBrowseFolder: _browseFolder,
              onBrowseFile: _browseFile,
              onClear: () {},
              onSubmit: (ResourceItem draft) {
                unawaited(
                  _saveDraft(dialogContext, draft, editing: item),
                );
              },
            ),
          ),
        );
      },
    );

    if (!mounted) {
      return;
    }
    if (saved != null) {
      setState(() => _selectedId = saved.id);
    }
  }

  /// Saves [draft], closes the dialog on success and keeps it open on failure
  /// (validation / duplicate errors stay visible for correction).
  Future<void> _saveDraft(
    BuildContext dialogContext,
    ResourceItem draft, {
    ResourceItem? editing,
  }) async {
    final ResourceItem? saved = await _persistDraft(draft, editing: editing);
    if (saved != null && dialogContext.mounted) {
      Navigator.of(dialogContext).pop(saved);
    }
  }

  Future<ResourceItem?> _persistDraft(
    ResourceItem draft, {
    ResourceItem? editing,
  }) async {
    final bool isLinks = _mode.isLinks;
    try {
      final ResourceItem saved;
      if (editing == null) {
        saved = await _repo.add(
          _mode,
          name: draft.name,
          target: draft.path,
          category: draft.category,
          note: draft.note,
        );
      } else {
        saved = await _repo.update(
          _mode,
          id: editing.id,
          name: draft.name,
          target: draft.path,
          category: draft.category,
          note: draft.note,
        );
      }
      await _reload(_mode);
      if (!mounted) {
        return null;
      }
      setState(() => _selectedId = saved.id);
      _setStatus(
        _Status(
          key: editing == null
              ? (isLinks ? 'link_saved' : 'folder_saved')
              : (isLinks ? 'link_updated' : 'folder_updated'),
          tone: StatusTone.success,
        ),
      );
      return saved;
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
      return null;
    } catch (error) {
      _setStatus(_Status(text: '$error'));
      return null;
    }
  }

  Future<void> _handleDelete() async {
    final ResourceItem? item = _selected;
    if (item == null) {
      _setStatus(
        _Status(
          key: _mode.isLinks ? 'select_first_link' : 'select_first_folder',
          tone: StatusTone.warning,
        ),
      );
      return;
    }
    final AppStrings strings = context.l10n;
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) => AlertDialog(
        title: Text(strings.t('confirm_delete_title')),
        content: Text(strings.t('confirm_delete_body', <Object?>[item.name])),
        actions: <Widget>[
          AppButton(
            label: strings.t('settings_cancel'),
            variant: AppButtonVariant.ghost,
            onPressed: () => Navigator.of(context).pop(false),
          ),
          AppButton(
            label: strings.t('delete'),
            variant: AppButtonVariant.danger,
            onPressed: () => Navigator.of(context).pop(true),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    try {
      await _repo.delete(_mode, item.id);
      await _reload(_mode);
      if (!mounted) {
        return;
      }
      setState(() {
        _selectedId = null;
        _detailOpen = false;
      });
      _setStatus(
        _Status(
          key: _mode.isLinks ? 'link_deleted' : 'folder_deleted',
          tone: StatusTone.success,
        ),
      );
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<void> _toggleFavorite(ResourceItem item) async {
    try {
      final ResourceItem updated =
          await _repo.setFavorite(_mode, item.id, value: !item.favorite);
      await _reload(_mode);
      if (!mounted) {
        return;
      }
      setState(() => _selectedId = updated.id);
      _setStatus(
        _Status(
          key: updated.favorite ? 'favorited' : 'unfavorited',
          tone: StatusTone.success,
        ),
      );
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<void> _open(ResourceItem item) async {
    final AppStrings strings = context.l10n;
    try {
      // The runner owns the foreground window, so it can hand foreground
      // rights to Explorer / the browser; without that they can open behind
      // this window. Fall back to the backend when the native method is absent
      // (widget tests, non-Windows, or a rejected target).
      final bool handled = await NativeShell.openTarget(item.path);
      if (!handled) {
        await _repo.open(_mode, item.id);
      }
      _setStatus(_Status(text: '${strings.t('open')}: ${item.name}'));
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<void> _reveal(ResourceItem item) async {
    final AppStrings strings = context.l10n;
    try {
      final bool handled = await NativeShell.revealPath(item.path);
      if (!handled) {
        await _repo.reveal(_mode, item.id);
      }
      _setStatus(_Status(text: '${strings.t('open_location')}: ${item.name}'));
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  void _copyPath(ResourceItem item) {
    Clipboard.setData(ClipboardData(text: item.path));
    _setStatus(
      _Status(
        key: _mode.isLinks ? 'copied_url' : 'copied_path',
        tone: StatusTone.success,
      ),
    );
  }

  // -- details panel (Phase 9) --------------------------------------------
  void _previewItem(ResourceItem item) {
    setState(() {
      _selectedId = item.id;
      _detailOpen = true;
    });
  }

  void _closeDetail() {
    if (!mounted) {
      return;
    }
    setState(() => _detailOpen = false);
  }

  Future<void> _openDetailPath(String path) async {
    final AppStrings strings = context.l10n;
    try {
      final bool handled = await NativeShell.openTarget(path);
      if (!handled) {
        await _repo.openPath(path);
      }
      _setStatus(_Status(text: '${strings.t('open')}: $path'));
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<void> _revealDetailPath(String path) async {
    final AppStrings strings = context.l10n;
    try {
      final bool handled = await NativeShell.revealPath(path);
      if (!handled) {
        await _repo.revealPath(path);
      }
      _setStatus(_Status(text: '${strings.t('open_location')}: $path'));
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  void _copyText(String value) {
    Clipboard.setData(ClipboardData(text: value));
    _setStatus(_Status(key: 'copied_path', tone: StatusTone.success));
  }

  /// Adds a folder/file discovered inside the preview map as a stored resource.
  Future<void> _addResourceFromPreview(FsEntry entry) async {
    if (_dataCorrupt) {
      _setStatus(_Status(key: 'data_corrupt'));
      return;
    }
    try {
      if (_mode.isLinks) {
        _handleModeChanged(ViewMode.folders);
      }
      final ResourceItem saved = await _repo.add(
        ViewMode.folders,
        name: entry.name,
        target: entry.path,
      );
      await _reload(ViewMode.folders);
      if (!mounted) {
        return;
      }
      setState(() {
        _selectedId = saved.id;
        _detailOpen = true;
      });
      _setStatus(
        _Status(
          key: 'added_as_resource',
          args: <Object?>[saved.name],
          tone: StatusTone.success,
        ),
      );
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  Future<void> _checkPaths() async {
    try {
      final PathCheckOutcome outcome = await _repo.checkPaths(_mode);
      if (!mounted) {
        return;
      }
      setState(() {
        for (final ResourceItem item in _current) {
          _pathStates[item.id] = outcome.missingIds.contains(item.id)
              ? PathState.missing
              : PathState.ok;
        }
      });
      if (!outcome.supported) {
        _setStatus(_Status(key: 'path_check_links_disabled'));
        return;
      }
      _setStatus(
        outcome.missingCount == 0
            ? _Status(key: 'paths_checked_all_ok', tone: StatusTone.success)
            : _Status(
                key: 'paths_checked_missing',
                args: <Object?>[outcome.missingCount],
                tone: StatusTone.warning,
              ),
      );
    } on BackendException catch (error) {
      _setStatus(_Status.fromError(error));
    }
  }

  void _handleModeChanged(ViewMode mode) {
    if (mode == _mode) {
      return;
    }
    setState(() {
      _mode = mode;
      _selectedId = null;
      _detailOpen = false;
      _categoryFilter = kAllCategories;
      _query = '';
      _search.clear();
    });
  }

  Future<void> _openSettings() async {
    final AppStrings strings = context.l10n;
    await showDialog<void>(
      context: context,
      builder: (BuildContext dialogContext) => SettingsDialog(
        language: strings.language,
        themeMode: widget.themeMode,
        settings: widget.settings,
        onLanguageChanged: AppStringsScope.languageSetterOf(dialogContext),
        onThemeModeChanged: widget.onThemeModeChanged,
        onSettingsChanged: widget.onSettingsChanged,
        onProbeHotkey: _probeHotkey,
        onHotkeyRecordingChanged: _setHotkeyRecording,
      ),
    );
  }

  String _defaultStatus(AppStrings strings) {
    if (_dataCorrupt) {
      return strings.tx('data_corrupt_body');
    }
    final HotkeyStatus? hotkey = _hotkey;
    if (hotkey != null && !hotkey.registered && hotkey.reason == 'unavailable') {
      return strings.tx('hotkey_unavailable_reason', <Object?>[hotkey.label]);
    }
    return strings.t('summary_all', <Object?>[_visible.length, _current.length]);
  }

  @override
  Widget build(BuildContext context) {
    final AppStrings strings = context.l10n;
    final List<ResourceItem> visible = _visible;
    final ResourceItem? selected = _selected;
    final ListSummary summary = ListSummary(
      visible: visible.length,
      total: _current.length,
      category: _categoryFilter == kAllCategories
          ? kAllCategories
          : (_categoryFilter == kUncategorized
              ? strings.t('uncategorized')
              : _categoryFilter),
      query: _query,
    );

    final _Status? status = _status;
    final StatusTone tone = _dataCorrupt
        ? StatusTone.error
        : (status?.tone ?? StatusTone.info);

    final Widget shell = Scaffold(
      body: Column(
        children: <Widget>[
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : LayoutBuilder(
                    builder: (BuildContext context, BoxConstraints constraints) {
                      final double maxDetailWidth = math.max(
                        420.0,
                        math.min(760.0, constraints.maxWidth - 320),
                      );
                      final double detailWidth =
                          _detailWidth.clamp(420.0, maxDetailWidth);
                      final ResourceItem? detailItem =
                          _detailOpen ? _selected : null;
                      return ResourceListPanel(
                        detailsPanel: detailItem == null
                            ? null
                            : SizedBox(
                                width: detailWidth,
                                child: ResourceDetailPanel(
                                  key: ValueKey<String>(
                                    '${detailItem.id}-${_mode.name}',
                                  ),
                                  item: detailItem,
                                  loadChildren: _repo.listChildren,
                                  onClose: _closeDetail,
                                  onResize: (double dx) => setState(() {
                                    _detailWidth = (_detailWidth - dx)
                                        .clamp(420.0, maxDetailWidth);
                                  }),
                                  onOpenItem: _open,
                                  onRevealItem: _reveal,
                                  onEditItem: (ResourceItem item) =>
                                      _openEditor(item: item),
                                  onToggleFavoriteItem: _toggleFavorite,
                                  onOpenPath: _openDetailPath,
                                  onRevealPath: _revealDetailPath,
                                  onAddResource: _addResourceFromPreview,
                                  onCopyText: _copyText,
                                ),
                              ),
                        mode: _mode,
                    items: visible,
                    allItems: _current,
                    categories: _categories,
                    summary: summary,
                    selectedId: _selectedId,
                    searchController: _search,
                    searchFocusNode: _searchFocus,
                    categoryFilter: _categoryFilter,
                    favoritesOnly: _favoritesOnly,
                    scrollController: _listScroll,
                    layout: _layout,
                    onLayoutChanged: (ResourceLayout value) =>
                        setState(() => _layout = value),
                    onModeChanged: _handleModeChanged,
                    onAdd: () => _openEditor(),
                    onSelected: (ResourceItem item) =>
                        setState(() => _selectedId = item.id),
                    onPreview: _previewItem,
                    onSearchChanged: (String value) =>
                        setState(() => _query = value),
                    onCategoryFilterChanged: (String value) =>
                        setState(() => _categoryFilter = value),
                    onToggleFavoritesOnly: () =>
                        setState(() => _favoritesOnly = !_favoritesOnly),
                    onOpenSelected: () {
                      if (selected != null) {
                        _open(selected);
                      }
                    },
                    onEditSelected: () {
                      if (selected != null) {
                        _openEditor(item: selected);
                      }
                    },
                    onDeleteSelected: _handleDelete,
                    onToggleFavoriteSelected: () {
                      if (selected != null) {
                        _toggleFavorite(selected);
                      }
                    },
                    onCheckPaths: _checkPaths,
                    onImport: _importCollection,
                    onExport: _exportCollection,
                    actions: ResourceTableActions(
                      onOpen: _open,
                      onReveal: _reveal,
                      onEdit: (ResourceItem item) => _openEditor(item: item),
                      onToggleFavorite: _toggleFavorite,
                      onCopyPath: _copyPath,
                      onDelete: (ResourceItem item) {
                        setState(() => _selectedId = item.id);
                        _handleDelete();
                      },
                    ),
                    reorderEnabled: _canReorder,
                    onMoveItem: (ResourceItem item, int targetIndex) =>
                        unawaited(_handleMoveItem(item, targetIndex)),
                    onSortByAdded: () => unawaited(_sortByAdded()),
                        onOpenSettings: _openSettings,
                      );
                    },
                  ),
          ),
          AppStatusBar(
            message: status?.resolve(strings) ??
                _loadFailure ??
                _defaultStatus(strings),
            tone: tone,
            trailing: _buildStatusTrailing(strings),
          ),
        ],
      ),
    );

    // Keyboard alternative to dragging (Alt+Up / Alt+Down). The bindings live
    // inside the page, so dialogs with text fields are unaffected.
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.arrowUp, alt: true): () =>
            unawaited(_moveSelected(-1)),
        const SingleActivator(LogicalKeyboardKey.arrowDown, alt: true): () =>
            unawaited(_moveSelected(1)),
      },
      child: Focus(autofocus: true, child: shell),
    );
  }

  Widget? _buildStatusTrailing(AppStrings strings) {
    if (_undo != null) {
      return TextButton(
        onPressed: () => unawaited(_undoOrder()),
        style: TextButton.styleFrom(
          minimumSize: const Size(0, 24),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          visualDensity: VisualDensity.compact,
        ),
        child: Text(strings.tx('undo')),
      );
    }
    if (_dataCorrupt) {
      return Text(
        strings.tx('read_only_badge'),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.error,
              fontWeight: FontWeight.w700,
            ),
      );
    }
    return null;
  }
}
