/// Phase 16: compact "quick panel" HUD.
///
/// The global hotkeys registered by the backend ask the shell for a tree without
/// opening the full window: the runner shrinks the window into a frameless,
/// topmost panel (see [WindowControl.enterQuickMode]) and this widget fills it.
///
/// Two trees share the same chrome:
///  * sites — `分类 → 网站`, ordered exactly like the stored list;
///  * folders — `分类 → 资源 → 真实子目录/文件`, children loaded lazily through
///    `fs.children` (the same read-only API the details map uses).
///
/// Typing filters into a flat result list so a HUD press is usually: hotkey,
/// type a few letters, Enter. Keyboard is handled through [HardwareKeyboard]
/// instead of a [Focus] shortcut because the search field owns focus and would
/// otherwise swallow arrow keys (spotlight-style panels must keep ↑/↓ working
/// while the query is being typed). IME composition is never intercepted.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../data/backend_models.dart';
import '../../design/app_tokens.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../models/resource_item.dart';
import '../../platform/backend_client.dart';
import '../../widgets/site_icon.dart';

/// Which tree the quick panel is showing.
enum QuickPanelKind {
  links,
  folders;

  bool get isLinks => this == QuickPanelKind.links;
}

/// A Spotlight-style tree overlay for one dataset.
class QuickPanel extends StatefulWidget {
  const QuickPanel({
    super.key,
    required this.kind,
    required this.links,
    required this.folders,
    this.browsers = const <BrowserInfo>[],
    required this.loadChildren,
    required this.onOpenItem,
    this.onOpenWith,
    required this.onOpenPath,
    required this.onSwitchKind,
    required this.onClose,
  });

  final QuickPanelKind kind;

  /// Both collections are passed in full; the HUD is a browser, not a filter of
  /// the main window's state.
  final List<ResourceItem> links;
  final List<ResourceItem> folders;
  final Future<FsListing> Function(String path) loadChildren;
  final ValueChanged<ResourceItem> onOpenItem;

  /// Right-click a link row: opens it in the picked browser (empty id = system
  /// default). Null hides the context menu.
  final void Function(ResourceItem item, String browserId)? onOpenWith;

  /// Installed browsers for the right-click "open with" menu.
  final List<BrowserInfo> browsers;

  /// Opens a raw filesystem entry (file) with the default handler.
  final ValueChanged<String> onOpenPath;
  final VoidCallback onSwitchKind;
  final VoidCallback onClose;

  @override
  State<QuickPanel> createState() => _QuickPanelState();
}

class _QuickPanelState extends State<QuickPanel> {
  static const double _indent = 14;

  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode(debugLabel: 'quick-search');
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _rowKeys = <String, GlobalKey>{};

  /// Node keys (`i:<id>`, `f:<path>`) whose children are expanded.
  final Set<String> _expanded = <String>{};

  /// Lazily loaded directory listings, keyed by absolute path.
  final Map<String, FsListing> _listings = <String, FsListing>{};
  final Set<String> _loading = <String>{};
  final Map<String, String> _errors = <String, String>{};

  String _query = '';
  String? _selectedKey;
  String? _hoveredKey;

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_onHardwareKey);
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_onHardwareKey);
    _search.dispose();
    _searchFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(QuickPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.kind != widget.kind) {
      // Defensive: the shell normally rebuilds the panel with a new key, but a
      // hotkey change while the panel is open must not keep stale state.
      _query = '';
      _search.clear();
      _selectedKey = null;
      _expanded.clear();
      _listings.clear();
      _loading.clear();
      _errors.clear();
    }
  }

  // -- keyboard -----------------------------------------------------------
  bool _onHardwareKey(KeyEvent event) {
    if (!mounted) {
      return false;
    }
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return false;
    }
    // Never hijack system/menu shortcuts, and let the IME own everything while a
    // composition is active (Enter/arrows belong to the candidate window then).
    if (HardwareKeyboard.instance.isControlPressed ||
        HardwareKeyboard.instance.isAltPressed ||
        HardwareKeyboard.instance.isMetaPressed) {
      return false;
    }
    if (_search.value.composing.isValid) {
      return false;
    }

    final AppStrings t = context.l10n;
    switch (event.logicalKey) {
      case LogicalKeyboardKey.arrowDown:
        _moveSelection(1, t);
        return true;
      case LogicalKeyboardKey.arrowUp:
        _moveSelection(-1, t);
        return true;
      case LogicalKeyboardKey.enter:
      case LogicalKeyboardKey.numpadEnter:
        _activateSelected(t);
        return true;
      case LogicalKeyboardKey.escape:
        widget.onClose();
        return true;
      case LogicalKeyboardKey.tab:
        if (!HardwareKeyboard.instance.isShiftPressed) {
          widget.onSwitchKind();
          return true;
        }
        return false;
      case LogicalKeyboardKey.arrowRight:
        if (_query.trim().isEmpty) {
          _expandSelected(expand: true, t: t);
          return true;
        }
        return false;
      case LogicalKeyboardKey.arrowLeft:
        if (_query.trim().isEmpty) {
          _expandSelected(expand: false, t: t);
          return true;
        }
        return false;
    }
    return false;
  }

  List<_QuickRow> _rows(AppStrings t) {
    final String query = _query.trim().toLowerCase();
    final bool isLinks = widget.kind.isLinks;
    final List<ResourceItem> items = isLinks ? widget.links : widget.folders;

    if (query.isNotEmpty) {
      final List<ResourceItem> matches = items
          .where((ResourceItem item) => _matches(item, query))
          .toList(growable: false);
      return <_QuickRow>[
        for (final ResourceItem item in matches)
          _QuickRow.resource(
            key: 'q:${item.id}',
            item: item,
            depth: 0,
            subtitle: item.path,
          ),
      ];
    }

    final Map<String, List<ResourceItem>> grouped =
        <String, List<ResourceItem>>{};
    for (final ResourceItem item in items) {
      grouped.putIfAbsent(item.category, () => <ResourceItem>[]).add(item);
    }
    final List<String> categories = grouped.keys
        .where((String category) => category != kUncategorized)
        .toList(growable: false)
      ..sort();
    final List<String> ordered = <String>[
      ...categories,
      if (grouped.containsKey(kUncategorized)) kUncategorized,
    ];

    final List<_QuickRow> rows = <_QuickRow>[];
    for (final String category in ordered) {
      final List<ResourceItem> groupItems = grouped[category]!;
      rows.add(
        _QuickRow.header(
          key: 'h:$category',
          label: category == kUncategorized
              ? t.t('uncategorized')
              : category,
          count: groupItems.length,
        ),
      );
      for (final ResourceItem item in groupItems) {
        final String rowKey = 'i:${item.id}';
        final bool expandable =
            !isLinks && item.kind == ResourceKind.folder;
        final bool expanded = _expanded.contains(rowKey);
        rows.add(
          _QuickRow.resource(
            key: rowKey,
            item: item,
            depth: 1,
            expandable: expandable,
            expanded: expanded,
            subtitle: isLinks ? null : item.path,
          ),
        );
        if (expandable && expanded) {
          _appendChildren(rows, item.path, 2, t);
        }
      }
    }
    return rows;
  }

  /// Recursively appends one directory's children. Symlinks/junctions are not
  /// expandable (they can form cycles) and the depth cap keeps a runaway folder
  /// from wedging the HUD.
  void _appendChildren(
    List<_QuickRow> rows,
    String path,
    int depth,
    AppStrings t,
  ) {
    if (depth > 8) {
      rows.add(
        _QuickRow.note(
          key: 'deep:$path',
          label: t.tx('empty_folder'),
          depth: depth,
        ),
      );
      return;
    }
    if (_loading.contains(path)) {
      rows.add(
        _QuickRow.note(
          key: 'load:$path',
          label: t.tx('quick_loading'),
          depth: depth,
          loading: true,
        ),
      );
      return;
    }
    final String? error = _errors[path];
    if (error != null) {
      rows.add(
        _QuickRow.note(
          key: 'err:$path',
          label: error,
          depth: depth,
          error: true,
        ),
      );
      return;
    }
    final FsListing? listing = _listings[path];
    if (listing == null) {
      rows.add(
        _QuickRow.note(
          key: 'load:$path',
          label: t.tx('quick_loading'),
          depth: depth,
          loading: true,
        ),
      );
      return;
    }
    if (listing.entries.isEmpty) {
      rows.add(
        _QuickRow.note(
          key: 'empty:$path',
          label: t.tx('empty_folder'),
          depth: depth,
        ),
      );
      return;
    }
    for (final FsEntry entry in listing.entries) {
      final String childKey = 'f:${entry.path}';
      final bool expandable = entry.isFolder && !entry.isLink;
      final bool expanded = _expanded.contains(childKey);
      rows.add(
        _QuickRow.fs(
          key: childKey,
          path: entry.path,
          label: entry.name,
          depth: depth,
          isFolder: entry.isFolder,
          expandable: expandable,
          expanded: expanded,
        ),
      );
      if (expandable && expanded) {
        _appendChildren(rows, entry.path, depth + 1, t);
      }
    }
    if (listing.truncated && listing.remaining > 0) {
      rows.add(
        _QuickRow.note(
          key: 'more:$path',
          label: t.tx('more_items', <Object?>[listing.remaining]),
          depth: depth,
        ),
      );
    }
  }

  static bool _matches(ResourceItem item, String query) {
    final String haystack = <String>[
      item.name,
      item.path,
      item.category,
      item.note,
      item.kind.name,
    ].join(' ').toLowerCase();
    return haystack.contains(query);
  }

  List<String> _selectableKeys(List<_QuickRow> rows) => <String>[
        for (final _QuickRow row in rows)
          if (row.selectable) row.key,
      ];

  String? _effectiveSelection(List<_QuickRow> rows) {
    final List<String> keys = _selectableKeys(rows);
    if (keys.isEmpty) {
      return null;
    }
    final String? selected = _selectedKey;
    if (selected != null && keys.contains(selected)) {
      return selected;
    }
    return keys.first;
  }

  void _moveSelection(int delta, AppStrings t) {
    final List<_QuickRow> rows = _rows(t);
    final List<String> keys = _selectableKeys(rows);
    if (keys.isEmpty) {
      return;
    }
    final int current = keys.indexOf(_selectedKey ?? '');
    int next;
    if (current < 0) {
      next = delta > 0 ? 0 : keys.length - 1;
    } else {
      next = (current + delta) % keys.length;
      if (next < 0) {
        next += keys.length;
      }
    }
    setState(() => _selectedKey = keys[next]);
    _reveal(keys[next]);
  }

  void _reveal(String rowKey) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final BuildContext? rowContext = _rowKeys[rowKey]?.currentContext;
      if (rowContext == null) {
        return;
      }
      Scrollable.ensureVisible(
        rowContext,
        duration: AppDurations.fast,
        alignment: 0.35,
      );
    });
  }

  _QuickRow? _selectedRow(AppStrings t) {
    final List<_QuickRow> rows = _rows(t);
    final String? key = _effectiveSelection(rows);
    if (key == null) {
      return null;
    }
    for (final _QuickRow row in rows) {
      if (row.key == key) {
        return row;
      }
    }
    return null;
  }

  void _activateSelected(AppStrings t) {
    final _QuickRow? row = _selectedRow(t);
    if (row == null) {
      return;
    }
    _activateRow(row, t);
  }

  void _activateRow(_QuickRow row, AppStrings t) {
    setState(() => _selectedKey = row.key);
    final ResourceItem? item = row.item;
    if (item != null) {
      widget.onOpenItem(item);
      return;
    }
    if (row.kind == _QuickRowKind.folder && row.path != null) {
      unawaited(_toggleFolder(row, t));
      return;
    }
    if (row.path != null) {
      widget.onOpenPath(row.path!);
    }
  }

  /// Right-click menu for a link row: open it once in the picked browser.
  Future<void> _showOpenWithMenu(
    ResourceItem item,
    Offset position,
    AppStrings t,
  ) async {
    final RenderBox overlay =
        Overlay.of(context).context.findRenderObject()! as RenderBox;
    final String? choice = await showMenu<String>(
      context: context,
      position: RelativeRect.fromRect(
        position & const Size(1, 1),
        Offset.zero & overlay.size,
      ),
      items: <PopupMenuEntry<String>>[
        PopupMenuItem<String>(
          value: '',
          child: Text(t.tx('open_with_default')),
        ),
        for (final BrowserInfo browser in widget.browsers)
          PopupMenuItem<String>(
            value: browser.id,
            child: Text(browser.name),
          ),
      ],
    );
    if (choice != null && mounted) {
      widget.onOpenWith!(item, choice);
    }
  }

  void _expandSelected({required bool expand, required AppStrings t}) {
    final _QuickRow? row = _selectedRow(t);
    if (row == null || !row.expandable) {
      return;
    }
    if (expand == row.expanded) {
      return;
    }
    unawaited(_toggleFolder(row, t));
  }

  Future<void> _toggleFolder(_QuickRow row, AppStrings t) async {
    if (!row.expandable) {
      return;
    }
    final String path = row.item?.path ?? row.path ?? '';
    if (path.isEmpty) {
      return;
    }
    final bool willExpand = !_expanded.contains(row.key);
    setState(() {
      _selectedKey = row.key;
      if (willExpand) {
        _expanded.add(row.key);
      } else {
        _expanded.remove(row.key);
      }
    });
    if (!willExpand ||
        _listings.containsKey(path) ||
        _loading.contains(path)) {
      return;
    }
    setState(() => _loading.add(path));
    try {
      final FsListing listing = await widget.loadChildren(path);
      if (!mounted) {
        return;
      }
      setState(() {
        _loading.remove(path);
        _errors.remove(path);
        _listings[path] = listing;
      });
    } on BackendException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading.remove(path);
        _errors[path] = _fsError(error, t);
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading.remove(path);
        _errors[path] = '$error';
      });
    }
  }

  String _fsError(BackendException error, AppStrings t) {
    final String? key = error.key;
    if (key != null) {
      return t.tx(key);
    }
    return error.detail.isEmpty ? error.code : error.detail;
  }

  GlobalKey _keyFor(String rowKey) =>
      _rowKeys.putIfAbsent(rowKey, () => GlobalKey(debugLabel: rowKey));

  /// Clicking any blank space *inside* the panel must not dismiss it.
  ///
  /// Dismissal is owned by the runner: when the HUD loses activation because the
  /// user clicked another window (or the desktop), Windows sends
  /// WM_ACTIVATE(WA_INACTIVE) and Dart receives `quickDismissed`. This handler
  /// only keeps the search field focused so typing/arrow keys keep working after
  /// a blank click; it deliberately never calls [QuickPanel.onClose].
  void _handlePanelTap() {
    if (_searchFocus.canRequestFocus && !_searchFocus.hasFocus) {
      _searchFocus.requestFocus();
    }
  }

  // -- build --------------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final List<_QuickRow> rows = _rows(t);
    final String? selectedKey = _effectiveSelection(rows);
    final bool hasSearch = _query.trim().isNotEmpty;

    final Widget body;
    if (rows.isEmpty) {
      body = _emptyState(context, t, scheme, text, hasSearch);
    } else {
      body = ListView.builder(
        controller: _scroll,
        padding: const EdgeInsets.fromLTRB(6, 2, 6, 8),
        itemCount: rows.length,
        itemBuilder: (BuildContext context, int index) {
          final _QuickRow row = rows[index];
          return _buildRow(
            context,
            row,
            selectedKey,
            scheme,
            text,
            t,
          );
        },
      );
    }

    return Material(
      color: scheme.surfaceContainerLow,
      child: Column(
        children: <Widget>[
          _buildSearchBar(context, t, scheme, text),
          Divider(height: 1, thickness: 1, color: scheme.outlineVariant),
          Expanded(
            child: GestureDetector(
              // Taps on rows/folders are claimed by their own recognizers; taps
              // on blank space fall through to here and only keep focus.
              behavior: HitTestBehavior.opaque,
              onTap: _handlePanelTap,
              child: body,
            ),
          ),
          _buildFooter(context, t, scheme, text),
        ],
      ),
    );
  }

  Widget _buildSearchBar(
    BuildContext context,
    AppStrings t,
    ColorScheme scheme,
    TextTheme text,
  ) {
    final bool isLinks = widget.kind.isLinks;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.sm,
      ),
      child: TextField(
        controller: _search,
        focusNode: _searchFocus,
        autofocus: true,
        onChanged: (String value) => setState(() {
          _query = value;
          _selectedKey = null;
        }),
        onSubmitted: (String _) => _activateSelected(t),
        textInputAction: TextInputAction.go,
        style: text.bodyMedium,
        decoration: InputDecoration(
          hintText:
              isLinks ? t.tx('quick_search_links') : t.tx('quick_search_folders'),
          hintStyle: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          prefixIcon: Icon(
            Icons.search,
            size: 18,
            color: scheme.onSurfaceVariant,
          ),
          prefixIconConstraints: const BoxConstraints(minWidth: 38),
          suffixIcon: IconButton(
            tooltip: t.tx('quick_switch'),
            onPressed: widget.onSwitchKind,
            icon: Icon(
              Icons.swap_horiz,
              size: 17,
              color: scheme.onSurfaceVariant,
            ),
            visualDensity: VisualDensity.compact,
          ),
          isDense: true,
          filled: true,
          fillColor: scheme.surfaceContainerHighest,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
          border: OutlineInputBorder(
            borderRadius: AppRadius.lgAll,
            borderSide: BorderSide.none,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: AppRadius.lgAll,
            borderSide: BorderSide.none,
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: AppRadius.lgAll,
            borderSide: BorderSide(color: scheme.primary, width: 1.2),
          ),
        ),
      ),
    );
  }

  Widget _buildFooter(
    BuildContext context,
    AppStrings t,
    ColorScheme scheme,
    TextTheme text,
  ) {
    final bool isLinks = widget.kind.isLinks;
    final TextStyle? label = text.labelSmall?.copyWith(
      color: scheme.onSurfaceVariant,
      letterSpacing: 0.1,
    );
    return Container(
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
      child: Row(
        children: <Widget>[
          Icon(
            isLinks ? Icons.language : Icons.account_tree_outlined,
            size: 13,
            color: scheme.onSurfaceVariant,
          ),
          const SizedBox(width: AppSpacing.xs),
          Text(
            isLinks ? t.tx('quick_links_title') : t.tx('quick_folders_title'),
            style: text.labelSmall?.copyWith(
              color: scheme.onSurfaceVariant,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              isLinks ? t.tx('quick_keys_links') : t.tx('quick_keys_folders'),
              style: label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyState(
    BuildContext context,
    AppStrings t,
    ColorScheme scheme,
    TextTheme text,
    bool hasSearch,
  ) {
    final String message;
    final IconData icon;
    if (hasSearch) {
      message = t.tx('quick_no_match');
      icon = Icons.search_off;
    } else if (widget.kind.isLinks) {
      message = t.tx('quick_empty_links');
      icon = Icons.language;
    } else {
      message = t.tx('quick_empty_folders');
      icon = Icons.folder_open_outlined;
    }
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 30, color: scheme.onSurfaceVariant),
          const SizedBox(height: AppSpacing.sm),
          Text(
            message,
            style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Widget _buildRow(
    BuildContext context,
    _QuickRow row,
    String? selectedKey,
    ColorScheme scheme,
    TextTheme text,
    AppStrings t,
  ) {
    if (row.kind == _QuickRowKind.header) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(10, 12, 10, 4),
        child: Row(
          children: <Widget>[
            Text(
              row.label,
              style: text.labelSmall?.copyWith(
                color: scheme.onSurfaceVariant,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.2,
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Text(
              '${row.count}',
              style: text.labelSmall?.copyWith(
                color: scheme.onSurfaceVariant.withValues(alpha: 0.7),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Divider(height: 1, color: scheme.outlineVariant),
            ),
          ],
        ),
      );
    }

    if (row.kind == _QuickRowKind.note) {
      return Padding(
        padding: EdgeInsets.only(
          left: 10 + row.depth * _indent,
          right: 10,
          top: 5,
          bottom: 5,
        ),
        child: Row(
          children: <Widget>[
            SizedBox(
              width: 16,
              height: 16,
              child: row.loading
                  ? CircularProgressIndicator(
                      strokeWidth: 1.6,
                      color: scheme.onSurfaceVariant,
                    )
                  : Icon(
                      row.error ? Icons.error_outline : Icons.more_horiz,
                      size: 14,
                      color: row.error ? scheme.error : scheme.onSurfaceVariant,
                    ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                row.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: text.bodySmall?.copyWith(
                  color: row.error ? scheme.error : scheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
      );
    }

    final bool selected = row.key == selectedKey;
    final bool hovered = row.key == _hoveredKey;
    // Every state is opaque and starts from the panel colour: animating from
    // Colors.transparent interpolates through a translucent dark grey and shows
    // exactly the "grey shadow for a moment" the user reported. The un-hovered
    // colour is the panel colour, so it still looks transparent.
    final Color panelColor = scheme.surfaceContainerLow;
    final Color background;
    if (selected) {
      background = scheme.primaryContainer;
    } else if (hovered) {
      background = Color.alphaBlend(
        scheme.primary.withValues(alpha: 0.05),
        panelColor,
      );
    } else {
      background = panelColor;
    }
    final bool dark = Theme.of(context).brightness == Brightness.dark;
    final Color favoriteColor =
        dark ? AppColors.favoriteDark : AppColors.favoriteLight;
    final bool warn = row.item?.pathState.isMissing ?? false;

    return Padding(
      padding: EdgeInsets.only(
        left: 4 + row.depth * _indent,
        right: 4,
        bottom: 1,
      ),
      child: MouseRegion(
        onEnter: (_) => setState(() => _hoveredKey = row.key),
        onExit: (_) {
          if (_hoveredKey == row.key) {
            setState(() => _hoveredKey = null);
          }
        },
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            key: _keyFor(row.key),
            borderRadius: AppRadius.smAll,
            // The row's own animated background is the only hover/selection
            // feedback: Material's default hover/highlight ink is dark and shows
            // through the 120 ms colour transition as a black shimmer.
            hoverColor: Colors.transparent,
            highlightColor: Colors.transparent,
            splashColor: Colors.transparent,
            splashFactory: NoSplash.splashFactory,
            onTap: () => _activateRow(row, t),
            onSecondaryTapDown: row.item?.kind == ResourceKind.link &&
                    widget.onOpenWith != null
                ? (TapDownDetails details) => unawaited(
                      _showOpenWithMenu(
                        row.item!,
                        details.globalPosition,
                        t,
                      ),
                    )
                : null,
            child: AnimatedContainer(
              duration: AppDurations.fast,
              constraints: const BoxConstraints(minHeight: 32),
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
              decoration: BoxDecoration(
                color: background,
                borderRadius: AppRadius.smAll,
              ),
              child: Row(
                children: <Widget>[
                  SizedBox(
                    width: 20,
                    height: 22,
                    child: row.expandable
                        ? InkResponse(
                            onTap: () => unawaited(_toggleFolder(row, t)),
                            radius: 12,
                            hoverColor: Colors.transparent,
                            highlightColor: Colors.transparent,
                            splashColor: Colors.transparent,
                            child: Center(
                              child: AnimatedRotation(
                                turns: row.expanded ? 0.25 : 0,
                                duration: AppDurations.fast,
                                child: Icon(
                                  Icons.chevron_right,
                                  size: 16,
                                  color: scheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                          )
                        : Center(
                            child: row.item == null
                                ? Icon(
                                    _iconFor(row),
                                    size: 15,
                                    color: scheme.onSurfaceVariant,
                                  )
                                : SiteIcon(
                                    item: row.item!,
                                    fallback: _iconFor(row),
                                    size: 16,
                                    color: scheme.onSurfaceVariant,
                                  ),
                          ),
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          row.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: text.bodyMedium?.copyWith(
                            color: warn ? scheme.error : scheme.onSurface,
                            fontWeight:
                                selected ? FontWeight.w600 : FontWeight.w500,
                            height: 1.25,
                          ),
                        ),
                        if (row.subtitle != null && row.subtitle!.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 1),
                            child: Text(
                              row.subtitle!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: text.bodySmall?.copyWith(
                                fontSize: 11,
                                height: 1.2,
                                color: scheme.onSurfaceVariant,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                  if (warn)
                    Padding(
                      padding: const EdgeInsets.only(left: AppSpacing.xs),
                      child: Icon(
                        Icons.error_outline,
                        size: 14,
                        color: scheme.error,
                      ),
                    ),
                  if (row.item?.favorite == true)
                    Padding(
                      padding: const EdgeInsets.only(left: AppSpacing.xxs),
                      child: Icon(
                        Icons.star_rounded,
                        size: 14,
                        color: favoriteColor,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  IconData _iconFor(_QuickRow row) {
    final ResourceItem? item = row.item;
    if (item != null) {
      switch (item.kind) {
        case ResourceKind.link:
          return Icons.language;
        case ResourceKind.folder:
          return Icons.folder_outlined;
        case ResourceKind.file:
          return Icons.description_outlined;
      }
    }
    return row.kind == _QuickRowKind.folder
        ? Icons.folder_outlined
        : Icons.description_outlined;
  }
}

enum _QuickRowKind { header, item, folder, file, note }

class _QuickRow {
  _QuickRow._({
    required this.key,
    required this.kind,
    required this.label,
    this.subtitle,
    this.depth = 0,
    this.count = 0,
    this.item,
    this.path,
    this.expandable = false,
    this.expanded = false,
    this.loading = false,
    this.error = false,
  });

  factory _QuickRow.header({
    required String key,
    required String label,
    required int count,
  }) =>
      _QuickRow._(
        key: key,
        kind: _QuickRowKind.header,
        label: label,
        count: count,
      );

  factory _QuickRow.resource({
    required String key,
    required ResourceItem item,
    required int depth,
    String? subtitle,
    bool expandable = false,
    bool expanded = false,
  }) =>
      _QuickRow._(
        key: key,
        kind: _QuickRowKind.item,
        label: item.name,
        subtitle: subtitle,
        depth: depth,
        item: item,
        expandable: expandable,
        expanded: expanded,
      );

  factory _QuickRow.fs({
    required String key,
    required String path,
    required String label,
    required int depth,
    required bool isFolder,
    bool expandable = false,
    bool expanded = false,
  }) =>
      _QuickRow._(
        key: key,
        kind: isFolder ? _QuickRowKind.folder : _QuickRowKind.file,
        label: label,
        path: path,
        depth: depth,
        expandable: expandable,
        expanded: expanded,
      );

  factory _QuickRow.note({
    required String key,
    required String label,
    required int depth,
    bool loading = false,
    bool error = false,
  }) =>
      _QuickRow._(
        key: key,
        kind: _QuickRowKind.note,
        label: label,
        depth: depth,
        loading: loading,
        error: error,
      );

  final String key;
  final _QuickRowKind kind;
  final String label;
  final String? subtitle;
  final int depth;
  final int count;
  final ResourceItem? item;
  final String? path;
  final bool expandable;
  final bool expanded;
  final bool loading;
  final bool error;

  bool get selectable =>
      kind == _QuickRowKind.item ||
      kind == _QuickRowKind.folder ||
      kind == _QuickRowKind.file;
}
