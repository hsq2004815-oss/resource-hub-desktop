/// Horizontal mind map for the folder preview panel (Phase 9).
///
/// The root is the folder resource; expanding a folder node loads exactly one
/// level through `fs.children` and renders it as a tidy horizontal tree with
/// curved connectors (the NotebookLM mind-map reference saved in
/// `migration/screenshots/phase9-mindmap-reference.png`).
///
/// Interaction contract (confirmed with the user):
/// * a circular chevron on the node's right edge expands/collapses one level —
///   it appears on hover, selection or keyboard focus and stays visible while
///   expanded;
/// * single click selects a node (double click opens it in Explorer; files open
///   with their default handler);
/// * `Ctrl + wheel` zooms around the pointer, plain wheel pans, shift+wheel pans
///   horizontally, dragging the background pans, double-clicking it fits the
///   view; the panel toolbar mirrors zoom in/out/fit;
/// * expand/collapse is lazy and cached per panel session; files are leaves.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/backend_models.dart';
import '../design/app_theme.dart';
import '../design/app_tokens.dart';
import '../l10n/app_strings_ext.dart';
import '../l10n/strings_scope.dart';
import '../platform/backend_client.dart';

/// Imperative hooks used by the panel's zoom toolbar.
class MindMapController {
  _MindMapState? _state;

  /// Current zoom, for the toolbar percentage label.
  final ValueNotifier<double> zoom = ValueNotifier<double>(1.0);

  bool get attached => _state != null;

  void zoomIn() => _state?._zoomStep(1.25);
  void zoomOut() => _state?._zoomStep(0.8);
  void fit() => _state?._fitView();

  void _attach(_MindMapState state) {
    _state = state;
  }

  void _detach(_MindMapState state) {
    if (identical(_state, state)) {
      _state = null;
    }
  }
}

/// Callbacks the map needs from the panel/shell.
class MindMapActions {
  const MindMapActions({
    required this.onOpenEntry,
    required this.onRevealEntry,
    required this.onCopyPath,
    required this.onAddResource,
    required this.onSelectionChanged,
  });

  final ValueChanged<FsEntry> onOpenEntry;
  final ValueChanged<FsEntry> onRevealEntry;
  final ValueChanged<String> onCopyPath;
  final ValueChanged<FsEntry> onAddResource;
  final ValueChanged<FsEntry?> onSelectionChanged;
}

class MindMap extends StatefulWidget {
  const MindMap({
    super.key,
    required this.rootName,
    required this.rootPath,
    required this.loadChildren,
    required this.actions,
    this.controller,
  });

  final String rootName;
  final String rootPath;
  final Future<FsListing> Function(String path) loadChildren;
  final MindMapActions actions;
  final MindMapController? controller;

  @override
  State<MindMap> createState() => _MindMapState();
}

class _MindMapState extends State<MindMap> {
  static const double _rootHeight = 44;
  static const double _folderHeight = 36;
  static const double _fileHeight = 30;
  static const double _placeholderHeight = 28;
  static const double _levelGap = 40;
  static const double _siblingGap = 10;
  static const double _margin = 28;
  static const double _toggleSize = 22;
  static const double _minZoom = 0.4;
  static const double _maxZoom = 2.0;

  final FocusNode _focus = FocusNode(debugLabel: 'mind-map');
  final List<_MapNode> _visible = <_MapNode>[];
  final List<_Edge> _edges = <_Edge>[];
  List<_MapNode> _navNodes = <_MapNode>[];

  late _MapNode _root;
  String? _selectedKey;
  String? _hoveredKey;
  String? _toggleHoverKey;
  _MapNode? _nodeToReveal;
  Size _viewport = Size.zero;
  Size _content = Size.zero;
  double _zoom = 1.0;
  Offset _offset = Offset.zero;
  bool _initialFitDone = false;
  bool _fitScheduled = false;

  @override
  void initState() {
    super.initState();
    widget.controller?._attach(this);
    _root = _MapNode(
      key: r'$',
      name: widget.rootName,
      path: widget.rootPath,
      kind: FsEntryKind.folder,
      isRoot: true,
    );
    unawaited(_loadNode(_root));
  }

  @override
  void dispose() {
    widget.controller?._detach(this);
    _focus.dispose();
    super.dispose();
  }

  // -- data ---------------------------------------------------------------
  Future<void> _loadNode(_MapNode node) async {
    if (node.loading) {
      return;
    }
    setState(() {
      node.loading = true;
      node.errorKey = null;
      node.expanded = true;
    });
    try {
      final FsListing listing = await widget.loadChildren(node.path);
      if (!mounted) {
        return;
      }
      final List<_MapNode> children = <_MapNode>[
        for (final FsEntry entry in listing.entries)
          _MapNode(
            key: '${node.key}\u0000${entry.path}',
            name: entry.name,
            path: entry.path,
            kind: entry.kind,
            isLink: entry.isLink,
            parent: node,
          ),
      ];
      setState(() {
        node.loading = false;
        node.children = children;
        node.total = listing.total;
        node.truncated = listing.truncated;
        node.expanded = true;
        _nodeToReveal = node.isRoot || children.isEmpty ? null : children.last;
      });
      if (node.isRoot) {
        // The first fit ran against the "loading" placeholder; once the real
        // children are known, fit again so the whole first level is visible.
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _fitView();
          }
        });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        node.loading = false;
        node.children = null;
        node.expanded = true;
        node.errorKey = _errorKey(error);
      });
    }
  }

  static String _errorKey(Object error) {
    if (error is BackendException) {
      final String? key = error.key;
      if (key != null && key.startsWith('fs_')) {
        return key;
      }
    }
    return 'fs_unreadable';
  }

  int _depthOf(_MapNode node) {
    int depth = 0;
    _MapNode? parent = node.parent;
    while (parent != null) {
      depth += 1;
      parent = parent.parent;
    }
    return depth;
  }

  Future<void> _toggleNode(_MapNode node) async {
    if (node.placeholder != null || node.loading || !node.isFolder) {
      return;
    }
    // Junction/symlink loops are bounded by this depth guard; each expansion is
    // one explicit user click, so a hard cap is enough here.
    if (_depthOf(node) >= 12) {
      return;
    }
    if (node.expanded) {
      setState(() => node.expanded = false);
      return;
    }
    if (node.children != null) {
      setState(() => node.expanded = true);
      return;
    }
    await _loadNode(node);
  }

  void _retryNode(_MapNode node) {
    if (node.loading) {
      return;
    }
    unawaited(_loadNode(node));
  }

  // -- layout -------------------------------------------------------------
  TextStyle _textStyle(_MapNode node) {
    return TextStyle(
      fontFamily: AppTypography.fontFamily,
      fontFamilyFallback: AppTypography.fontFamilyFallback,
      fontSize: node.isRoot ? 13.5 : (node.isFile ? 12 : 12.8),
      fontWeight: node.isRoot || node.isFolder
          ? FontWeight.w600
          : FontWeight.w500,
    );
  }

  double _nodeWidth(BuildContext context, _MapNode node) {
    if (node.placeholder != null) {
      return 188;
    }
    final TextPainter painter = TextPainter(
      text: TextSpan(text: node.name, style: _textStyle(node)),
      maxLines: 1,
      textDirection: TextDirection.ltr,
    )..layout();
    final double extra = node.isRoot
        ? 74
        : (node.isFolder
            ? 62
            : 50);
    return (painter.width + extra).clamp(node.isRoot ? 150.0 : 98.0,
        node.isRoot ? 280.0 : 226.0);
  }

  List<_MapNode> _visibleChildren(_MapNode node) {
    if (!node.expanded) {
      return const <_MapNode>[];
    }
    if (node.loading) {
      return <_MapNode>[_placeholder(_PlaceholderKind.loading, node)];
    }
    if (node.errorKey != null) {
      return <_MapNode>[_placeholder(_PlaceholderKind.error, node)];
    }
    final List<_MapNode> children = node.children ?? const <_MapNode>[];
    if (children.isEmpty) {
      return <_MapNode>[_placeholder(_PlaceholderKind.empty, node)];
    }
    final List<_MapNode> result = <_MapNode>[...children];
    if (node.truncated) {
      result.add(_placeholder(_PlaceholderKind.more, node));
    }
    return result;
  }

  _MapNode _placeholder(_PlaceholderKind kind, _MapNode parent) {
    return _MapNode(
      key: '${parent.key}#${kind.name}',
      name: '',
      path: parent.path,
      kind: FsEntryKind.folder,
      parent: parent,
      placeholder: kind,
    );
  }

  double _cursor = 0;

  void _layout(BuildContext context) {
    _visible.clear();
    _edges.clear();
    _cursor = 0;
    _layoutNode(context, _root, 0);

    double minY = double.infinity;
    for (final _MapNode node in _visible) {
      minY = math.min(minY, node.y);
    }
    final double shift = _margin - (minY.isFinite ? minY : 0);
    double maxRight = 0;
    double maxBottom = 0;
    for (final _MapNode node in _visible) {
      node.y += shift;
      maxRight = math.max(maxRight, node.x + node.width);
      maxBottom = math.max(maxBottom, node.y + node.height);
    }
    _content = Size(
      maxRight + _margin + _toggleSize,
      maxBottom + _margin,
    );
    _navNodes = _visible
        .where((_MapNode node) => node.placeholder == null)
        .toList()
      ..sort((_MapNode a, _MapNode b) {
        final int byY = a.y.compareTo(b.y);
        return byY != 0 ? byY : a.x.compareTo(b.x);
      });
  }

  void _layoutNode(BuildContext context, _MapNode node, double x) {
    node.width = _nodeWidth(context, node);
    node.height = node.placeholder != null
        ? _placeholderHeight
        : (node.isRoot
            ? _rootHeight
            : (node.isFile ? _fileHeight : _folderHeight));
    node.x = x;
    final List<_MapNode> children = _visibleChildren(node);
    if (children.isEmpty) {
      node.y = _cursor;
      _cursor += node.height + _siblingGap;
    } else {
      double firstCenter = 0;
      double lastCenter = 0;
      for (int index = 0; index < children.length; index++) {
        final _MapNode child = children[index];
        _layoutNode(context, child, x + node.width + _levelGap);
        final double center = child.y + child.height / 2;
        if (index == 0) {
          firstCenter = center;
        }
        lastCenter = center;
        _edges.add(_Edge(node, child));
      }
      node.y = (firstCenter + lastCenter) / 2 - node.height / 2;
    }
    _visible.add(node);
  }

  // -- transform ----------------------------------------------------------
  void _scheduleInitialFit() {
    if (_fitScheduled || _initialFitDone) {
      return;
    }
    _fitScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _fitScheduled = false;
      if (!mounted) {
        return;
      }
      _fitView();
      _initialFitDone = true;
    });
  }

  void _fitView() {
    if (_viewport.width <= 0 || _content.width <= 0) {
      return;
    }
    final double fit = math.min(
      _viewport.width / _content.width,
      _viewport.height / _content.height,
    );
    final double next = fit.clamp(_minZoom, 1.0);
    final Offset offset = Offset(
      (_viewport.width - _content.width * next) / 2,
      (_viewport.height - _content.height * next) / 2,
    );
    setState(() {
      _zoom = next;
      _offset = offset;
    });
    widget.controller?.zoom.value = next;
  }

  void _zoomStep(double factor) {
    _zoomAt(Offset(_viewport.width / 2, _viewport.height / 2), factor);
  }

  void _zoomAt(Offset localPosition, double factor) {
    final double next = (_zoom * factor).clamp(_minZoom, _maxZoom);
    if ((next - _zoom).abs() < 0.001) {
      return;
    }
    final Offset contentPoint = (localPosition - _offset) / _zoom;
    setState(() {
      _zoom = next;
      _offset = localPosition - contentPoint * next;
    });
    widget.controller?.zoom.value = next;
  }

  void _handlePointerSignal(PointerSignalEvent event) {
    if (event is! PointerScrollEvent) {
      return;
    }
    if (HardwareKeyboard.instance.isControlPressed) {
      final double factor = math.exp(-event.scrollDelta.dy / 240);
      _zoomAt(event.localPosition, factor);
      return;
    }
    final bool horizontal =
        HardwareKeyboard.instance.isShiftPressed ||
            event.scrollDelta.dx.abs() > event.scrollDelta.dy.abs();
    setState(() {
      _offset += horizontal
          ? Offset(-event.scrollDelta.dy, 0)
          : Offset(0, -event.scrollDelta.dy);
    });
  }

  void _revealNode(_MapNode node) {
    if (_viewport == Size.zero) {
      return;
    }
    final Rect rect = Rect.fromLTWH(
      node.x * _zoom + _offset.dx,
      node.y * _zoom + _offset.dy,
      node.width * _zoom,
      node.height * _zoom,
    );
    const double pad = 20;
    double dx = 0;
    double dy = 0;
    if (rect.right > _viewport.width - pad) {
      dx = _viewport.width - pad - rect.right;
    }
    if (rect.left + dx < pad) {
      dx = pad - rect.left;
    }
    if (rect.bottom > _viewport.height - pad) {
      dy = _viewport.height - pad - rect.bottom;
    }
    if (rect.top + dy < pad) {
      dy = pad - rect.top;
    }
    if (dx != 0 || dy != 0) {
      setState(() => _offset += Offset(dx, dy));
    }
  }

  // -- selection / keyboard ----------------------------------------------
  void _selectNode(_MapNode node) {
    setState(() {
      _selectedKey = node.key;
      _hoveredKey = node.key;
    });
    _focus.requestFocus();
    final FsEntry? entry = node.entry;
    if (entry != null) {
      widget.actions.onSelectionChanged(entry);
    }
  }

  void _clearSelection() {
    if (_selectedKey == null) {
      return;
    }
    setState(() => _selectedKey = null);
    widget.actions.onSelectionChanged(null);
  }

  _MapNode? get _selectedNode {
    final String? key = _selectedKey;
    if (key == null) {
      return null;
    }
    for (final _MapNode node in _visible) {
      if (node.key == key && node.placeholder == null) {
        return node;
      }
    }
    return null;
  }

  void _moveSelection(int delta) {
    if (_navNodes.isEmpty) {
      return;
    }
    final _MapNode? current = _selectedNode;
    final int index = current == null ? -1 : _navNodes.indexOf(current);
    final int next = index < 0
        ? (delta > 0 ? 0 : _navNodes.length - 1)
        : (index + delta).clamp(0, _navNodes.length - 1);
    _selectNode(_navNodes[next]);
  }

  Future<void> _expandOrChild() async {
    final _MapNode? node = _selectedNode;
    if (node == null || !node.isFolder) {
      return;
    }
    if (!node.expanded) {
      await _toggleNode(node);
      return;
    }
    final List<_MapNode> children = node.children ?? const <_MapNode>[];
    if (children.isNotEmpty) {
      _selectNode(children.first);
    }
  }

  void _collapseOrParent() {
    final _MapNode? node = _selectedNode;
    if (node == null) {
      return;
    }
    if (node.expanded && node.children != null && node.children!.isNotEmpty) {
      setState(() => node.expanded = false);
      return;
    }
    final _MapNode? parent = node.parent;
    if (parent != null) {
      _selectNode(parent);
    }
  }

  void _openSelected() {
    final _MapNode? node = _selectedNode;
    if (node == null || node.isRoot) {
      return;
    }
    final FsEntry? entry = node.entry;
    if (entry != null) {
      widget.actions.onOpenEntry(entry);
    }
  }

  KeyEventResult _handleKeyEvent(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) {
      return KeyEventResult.ignored;
    }
    final LogicalKeyboardKey key = event.logicalKey;
    if (key == LogicalKeyboardKey.digit0) {
      _fitView();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.equal ||
        key == LogicalKeyboardKey.add ||
        key == LogicalKeyboardKey.numpadAdd) {
      _zoomStep(1.2);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.minus ||
        key == LogicalKeyboardKey.numpadSubtract) {
      _zoomStep(0.8);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowDown) {
      _moveSelection(1);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowUp) {
      _moveSelection(-1);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowRight) {
      unawaited(_expandOrChild());
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowLeft) {
      _collapseOrParent();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.enter) {
      _openSelected();
      return KeyEventResult.handled;
    }
    // Esc is handled by the panel so it can close itself.
    return KeyEventResult.ignored;
  }

  // -- context menu -------------------------------------------------------
  Future<void> _showNodeMenu(_MapNode node, Offset globalPosition) async {
    if (node.placeholder != null) {
      return;
    }
    final AppStrings t = context.l10n;
    final RenderBox overlay =
        Overlay.of(context).context.findRenderObject()! as RenderBox;
    final RelativeRect position = RelativeRect.fromLTRB(
      globalPosition.dx,
      globalPosition.dy,
      overlay.size.width - globalPosition.dx,
      overlay.size.height - globalPosition.dy,
    );
    final FsEntry? entry = node.entry;
    final String? choice = await showMenu<String>(
      context: context,
      position: position,
      items: <PopupMenuEntry<String>>[
        if (entry != null)
          PopupMenuItem<String>(
            value: 'open',
            child: _MenuRow(icon: Icons.open_in_new, label: t.t('open')),
          ),
        if (entry != null)
          PopupMenuItem<String>(
            value: 'reveal',
            child: _MenuRow(
              icon: Icons.folder_open_outlined,
              label: t.t('open_location'),
            ),
          ),
        if (entry != null)
          PopupMenuItem<String>(
            value: 'copy',
            child: _MenuRow(icon: Icons.copy_outlined, label: t.t('copy_path')),
          ),
        if (entry != null) ...<PopupMenuEntry<String>>[
          const PopupMenuDivider(),
          PopupMenuItem<String>(
            value: 'add',
            child: _MenuRow(
              icon: Icons.add,
              label: t.tx('add_as_resource'),
            ),
          ),
        ],
      ],
    );
    if (entry == null || !mounted) {
      return;
    }
    switch (choice) {
      case 'open':
        widget.actions.onOpenEntry(entry);
      case 'reveal':
        widget.actions.onRevealEntry(entry);
      case 'copy':
        widget.actions.onCopyPath(entry.path);
      case 'add':
        widget.actions.onAddResource(entry);
    }
  }

  // -- build --------------------------------------------------------------
  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        _viewport = constraints.biggest;
        _layout(context);
        _scheduleInitialFit();
        final _MapNode? reveal = _nodeToReveal;
        if (reveal != null && _initialFitDone) {
          _nodeToReveal = null;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              _revealNode(reveal);
            }
          });
        }
        return ClipRect(
          child: Listener(
            onPointerSignal: _handlePointerSignal,
            child: Focus(
              focusNode: _focus,
              autofocus: true,
              onKeyEvent: _handleKeyEvent,
              child: Stack(
                children: <Widget>[
                  Positioned.fill(
                    child: ColoredBox(
                      color: scheme.surfaceContainerLowest,
                    ),
                  ),
                  // Background-only gestures: taps/drags on empty canvas pan,
                  // clear the selection or double-click to fit. Keeping this
                  // behind the transformed content means node taps do not have
                  // to wait for this double-tap recogniser.
                  Positioned.fill(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: _clearSelection,
                      onDoubleTap: _fitView,
                      onPanUpdate: (DragUpdateDetails details) =>
                          setState(() => _offset += details.delta),
                    ),
                  ),
                  Transform(
                    transform: Matrix4.identity()
                      ..setEntry(0, 0, _zoom)
                      ..setEntry(1, 1, _zoom)
                      ..setEntry(0, 3, _offset.dx)
                      ..setEntry(1, 3, _offset.dy),
                    alignment: Alignment.topLeft,
                    child: SizedBox(
                      width: _content.width,
                      height: _content.height,
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: <Widget>[
                          Positioned.fill(
                            child: CustomPaint(
                              painter: _EdgePainter(
                                edges: _edges,
                                color: scheme.outlineVariant,
                              ),
                            ),
                          ),
                          for (final _MapNode node in _visible)
                            Positioned(
                              left: node.x,
                              top: node.y,
                              width: node.width,
                              height: node.height,
                              child: _buildNode(node),
                            ),
                          for (final _MapNode node in _visible)
                            if (node.placeholder == null && node.isFolder)
                              Positioned(
                                left: node.x + node.width - _toggleSize / 2,
                                top: node.y + (node.height - _toggleSize) / 2,
                                width: _toggleSize,
                                height: _toggleSize,
                                child: _buildToggle(t, node),
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
      },
    );
  }

  Widget _buildNode(_MapNode node) {
    if (node.placeholder != null) {
      return _buildPlaceholder(context.l10n, node);
    }
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semantic;
    final bool selected = node.key == _selectedKey;
    final bool hovered = node.key == _hoveredKey;
    final Color background = selected
        ? scheme.primaryContainer
        : node.isRoot
            ? scheme.surfaceContainerHigh
            : hovered
                ? scheme.surfaceContainerHigh
                : scheme.surfaceContainerLowest;
    final Color foreground =
        selected ? scheme.onPrimaryContainer : scheme.onSurface;
    final Color muted = selected
        ? scheme.onPrimaryContainer.withValues(alpha: 0.72)
        : scheme.onSurfaceVariant;
    return MouseRegion(
      onEnter: (_) => setState(() => _hoveredKey = node.key),
      onExit: (_) {
        if (_hoveredKey == node.key) {
          setState(() => _hoveredKey = null);
        }
      },
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        // Select on pointer-down so the hover toggle appears immediately; the
        // tap callback keeps semantics/accessibility working.
        onTapDown: (_) => _selectNode(node),
        onTap: () => _selectNode(node),
        onDoubleTap: node.isRoot
            ? null
            : () {
                final FsEntry? entry = node.entry;
                if (entry != null) {
                  widget.actions.onOpenEntry(entry);
                }
              },
        onSecondaryTapDown: (TapDownDetails details) =>
            _showNodeMenu(node, details.globalPosition),
        child: AnimatedContainer(
          duration: AppDurations.fast,
          padding: EdgeInsets.symmetric(horizontal: node.isRoot ? 14 : 10),
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(node.isRoot ? 12 : 10),
            border: Border.all(
              color: selected ? scheme.primary : scheme.outlineVariant,
            ),
            boxShadow: node.isRoot
                ? <BoxShadow>[
                    BoxShadow(
                      color: scheme.shadow.withValues(alpha: 0.06),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : const <BoxShadow>[],
          ),
          child: Row(
            children: <Widget>[
              Icon(
                node.isRoot
                    ? Icons.folder
                    : node.isFile
                        ? Icons.insert_drive_file_outlined
                        : Icons.folder_outlined,
                size: node.isRoot ? 18 : 15,
                color: node.isFile
                    ? muted
                    : selected
                        ? foreground
                        : scheme.onSurfaceVariant,
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  node.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: _textStyle(node).copyWith(color: foreground),
                ),
              ),
              if (node.isLink && !node.isRoot) ...<Widget>[
                const SizedBox(width: 3),
                Icon(
                  Icons.link,
                  size: 11,
                  color: semantic.favorite.withValues(alpha: 0.8),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildToggle(AppStrings t, _MapNode node) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool visible = node.key == _hoveredKey ||
        node.key == _toggleHoverKey ||
        node.key == _selectedKey ||
        node.expanded ||
        node.loading;
    if (!visible) {
      return const SizedBox.shrink();
    }
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _toggleHoverKey = node.key),
      onExit: (_) {
        if (_toggleHoverKey == node.key) {
          setState(() => _toggleHoverKey = null);
        }
      },
      child: Tooltip(
        message: node.expanded ? t.tx('collapse_node') : t.tx('expand_node'),
        waitDuration: const Duration(milliseconds: 500),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            unawaited(_toggleNode(node));
          },
          child: Container(
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest,
              shape: BoxShape.circle,
              border: Border.all(color: scheme.outlineVariant),
            ),
            alignment: Alignment.center,
            child: node.loading
                ? Padding(
                    padding: const EdgeInsets.all(5),
                    child: CircularProgressIndicator(
                      strokeWidth: 1.8,
                      color: scheme.onSurfaceVariant,
                    ),
                  )
                : AnimatedRotation(
                    turns: node.expanded ? 0.5 : 0,
                    duration: AppDurations.fast,
                    child: Icon(
                      Icons.chevron_right,
                      size: 15,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
          ),
        ),
      ),
    );
  }

  Widget _buildPlaceholder(AppStrings t, _MapNode node) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semantic;
    final _PlaceholderKind kind = node.placeholder!;
    final bool error = kind == _PlaceholderKind.error;
    final String label;
    switch (kind) {
      case _PlaceholderKind.loading:
        label = t.tx('loading_children');
      case _PlaceholderKind.error:
        label = '${t.tx(node.parent!.errorKey ?? 'fs_unreadable')} · ${t.tx('retry')}';
      case _PlaceholderKind.empty:
        label = t.tx('empty_folder');
      case _PlaceholderKind.more:
        final _MapNode parent = node.parent!;
        final int remaining = math.max(0, parent.total - (parent.children?.length ?? 0));
        label = t.tx('more_items', <Object?>[remaining]);
    }
    final Widget content = Row(
      children: <Widget>[
        if (kind == _PlaceholderKind.loading)
          const SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(strokeWidth: 1.8),
          )
        else
          Icon(
            error
                ? Icons.error_outline
                : kind == _PlaceholderKind.empty
                    ? Icons.folder_off_outlined
                    : Icons.more_horiz,
            size: 14,
            color: error ? semantic.danger : scheme.onSurfaceVariant,
          ),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 11.5,
              color: error ? semantic.danger : scheme.onSurfaceVariant,
              fontStyle: FontStyle.italic,
            ),
          ),
        ),
      ],
    );
    return GestureDetector(
      onTap: error ? () => _retryNode(node.parent!) : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: error ? semantic.dangerContainer : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: error ? semantic.danger.withValues(alpha: 0.4) : scheme.outlineVariant,
          ),
        ),
        child: content,
      ),
    );
  }
}

enum _PlaceholderKind { loading, error, empty, more }

class _MapNode {
  _MapNode({
    required this.key,
    required this.name,
    required this.path,
    required this.kind,
    this.isLink = false,
    this.isRoot = false,
    this.parent,
    this.placeholder,
  });

  final String key;
  final String name;
  final String path;
  final FsEntryKind kind;
  final bool isLink;
  final bool isRoot;
  final _MapNode? parent;
  final _PlaceholderKind? placeholder;

  List<_MapNode>? children;
  bool expanded = false;
  bool loading = false;
  String? errorKey;
  int total = 0;
  bool truncated = false;

  double width = 160;
  double height = 36;
  double x = 0;
  double y = 0;

  bool get isFolder => placeholder == null && kind == FsEntryKind.folder;
  bool get isFile => placeholder == null && kind == FsEntryKind.file;

  FsEntry? get entry => placeholder == null && !isRoot
      ? FsEntry(name: name, path: path, kind: kind, isLink: isLink)
      : null;
}

class _Edge {
  const _Edge(this.parent, this.child);

  final _MapNode parent;
  final _MapNode child;
}

class _EdgePainter extends CustomPainter {
  _EdgePainter({required this.edges, required this.color});

  final List<_Edge> edges;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final Paint paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round;
    for (final _Edge edge in edges) {
      final double startX = edge.parent.x + edge.parent.width;
      final double startY = edge.parent.y + edge.parent.height / 2;
      final double endX = edge.child.x;
      final double endY = edge.child.y + edge.child.height / 2;
      final double handle = (endX - startX) * 0.55;
      final Path path = Path()
        ..moveTo(startX, startY)
        ..cubicTo(startX + handle, startY, endX - handle, endY, endX, endY);
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_EdgePainter oldDelegate) {
    return oldDelegate.edges != edges || oldDelegate.color != color;
  }
}

class _MenuRow extends StatelessWidget {
  const _MenuRow({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(icon, size: 16, color: Theme.of(context).colorScheme.onSurface),
        const SizedBox(width: AppSpacing.md),
        Text(label, style: const TextStyle(fontSize: 13)),
      ],
    );
  }
}
