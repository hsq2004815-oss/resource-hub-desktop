/// Grid layout for the resource collection.
///
/// Same data and actions as [ResourceTable], just a different presentation:
/// the workspace offers a list/grid switch and both views must behave
/// identically (click selects, double-click opens, right-click shows the same
/// context menu, dragging a handle reorders).
///
/// Flutter has no `ReorderableGridView`, so the grid implements its own drag:
/// the hover grip starts a [Draggable], the state below tracks the insertion
/// slot from the pointer position over the cards, and a 2px primary line marks
/// the slot. The result is reported through [ResourceMoveCallback] exactly like
/// the table's `ReorderableListView`.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../design/app_theme.dart';
import '../design/app_tokens.dart';
import '../l10n/strings_scope.dart';
import '../models/resource_item.dart';
import '../util/formatters.dart';
import 'app_card.dart';
import 'reorder_grip.dart';
import 'resource_table.dart';

/// Presentation chosen by the workspace view toggle.
enum ResourceLayout { list, grid }

class ResourceGrid extends StatefulWidget {
  const ResourceGrid({
    super.key,
    required this.items,
    required this.mode,
    required this.selectedId,
    required this.onSelected,
    required this.actions,
    required this.reorderEnabled,
    required this.onMoveItem,
    this.onPreview,
    this.emptyState,
  });

  final List<ResourceItem> items;
  final ViewMode mode;
  final String? selectedId;
  final ValueChanged<ResourceItem> onSelected;
  final ResourceTableActions actions;

  /// False while a search is active (or a reorder is already being saved).
  final bool reorderEnabled;
  final ResourceMoveCallback onMoveItem;

  /// A completed click (not a drag): opens the details panel.
  final ValueChanged<ResourceItem>? onPreview;
  final Widget? emptyState;

  @override
  State<ResourceGrid> createState() => _ResourceGridState();
}

class _ResourceGridState extends State<ResourceGrid> {
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _cardKeys = <String, GlobalKey>{};
  final GlobalKey _gridKey = GlobalKey(debugLabel: 'resource-grid');

  /// Local copy in on-screen order. Reordering mutates this on every drag
  /// update so the cards below animate to their new slots while the pointer
  /// still moves (the list view gets the same feel from ReorderableListView).
  List<ResourceItem> _displayItems = <ResourceItem>[];

  String? _draggingId;
  Offset? _lastPointer;
  Timer? _autoScroll;
  double _autoScrollStep = 0;
  RenderBox? _viewportBox;
  int _columns = 1;
  double _cardWidth = 0;

  static const double _edgeZone = 44;
  static const double _maxCardExtent = 360;
  static const double _rowHeight = 132;
  static const double _cardSpacing = AppSpacing.sm;
  static const Duration _shiftDuration = Duration(milliseconds: 180);

  @override
  void initState() {
    super.initState();
    _displayItems = List<ResourceItem>.of(widget.items);
  }

  @override
  void didUpdateWidget(ResourceGrid oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_draggingId == null) {
      _displayItems = List<ResourceItem>.of(widget.items);
    }
  }

  @override
  void dispose() {
    _autoScroll?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  GlobalKey _keyFor(ResourceItem item) =>
      _cardKeys.putIfAbsent(item.id, GlobalKey.new);

  // -- drag lifecycle ------------------------------------------------------
  void _handleDragStarted(ResourceItem item) {
    setState(() {
      _draggingId = item.id;
      _lastPointer = null;
    });
  }

  void _handleDragUpdate(Offset globalPosition) {
    _lastPointer = globalPosition;
    _updateDropPosition(globalPosition);
    _updateAutoScroll(globalPosition);
  }

  void _handleDragEnd() {
    _stopAutoScroll();
    final String? draggedId = _draggingId;
    final int finalIndex = draggedId == null
        ? -1
        : _displayItems.indexWhere((ResourceItem item) => item.id == draggedId);
    final int originalIndex = draggedId == null
        ? -1
        : widget.items.indexWhere((ResourceItem item) => item.id == draggedId);
    setState(() {
      _draggingId = null;
      _lastPointer = null;
    });
    if (finalIndex < 0 || originalIndex < 0 || finalIndex == originalIndex) {
      // Keep the local copy in sync even when nothing moved.
      _displayItems = List<ResourceItem>.of(widget.items);
      return;
    }
    // `onMoveItem` wants the index *after* the dragged item was removed, which
    // is exactly its final position in the locally reordered list.
    widget.onMoveItem(_displayItems[finalIndex], finalIndex);
  }

  /// Moves the dragged card in the local list to the slot under the pointer.
  ///
  /// The grid geometry is computed from the pointer position instead of hit
  /// testing every card: that stays correct while cards animate and while the
  /// list scrolls under the pointer.
  void _updateDropPosition(Offset global) {
    final String? draggedId = _draggingId;
    final RenderBox? grid = _gridKey.currentContext?.findRenderObject() as RenderBox?;
    if (draggedId == null || grid == null || !grid.hasSize) {
      return;
    }
    final int from = _displayItems.indexWhere((ResourceItem item) => item.id == draggedId);
    final int count = _displayItems.length;
    if (from < 0 || count == 0) {
      return;
    }
    final Offset local = grid.globalToLocal(global);
    final double cellWidth = _cardWidth + _cardSpacing;
    final double cellHeight = _rowHeight + _cardSpacing;
    final int rows = math.max(1, (count / _columns).ceil());
    final int col = (local.dx / cellWidth).floor().clamp(0, _columns - 1);
    final int row = (local.dy / cellHeight).floor().clamp(0, rows - 1);
    int slot = row * _columns + col;
    if (local.dx - col * cellWidth > _cardWidth / 2) {
      slot += 1;
    }
    slot = slot.clamp(0, count);
    int to = slot > from ? slot - 1 : slot;
    to = to.clamp(0, count - 1);
    if (to == from) {
      return;
    }
    setState(() {
      final ResourceItem moved = _displayItems.removeAt(from);
      _displayItems.insert(to, moved);
    });
  }

  void _updateAutoScroll(Offset global) {
    final RenderBox? viewport = _viewportBox;
    if (viewport == null) {
      return;
    }
    final Rect rect = viewport.localToGlobal(Offset.zero) & viewport.size;
    final double dy = global.dy - rect.top;
    double delta = 0;
    if (dy < _edgeZone) {
      delta = -18 * (1 - dy / _edgeZone);
    } else if (dy > rect.height - _edgeZone) {
      delta = 18 * (1 - (rect.height - dy) / _edgeZone);
    }
    if (delta.abs() < 0.5) {
      _stopAutoScroll();
      return;
    }
    _autoScrollStep = delta;
    _autoScroll ??= Timer.periodic(
      const Duration(milliseconds: 16),
      (_) => _autoScrollTick(),
    );
  }

  void _autoScrollTick() {
    if (!_scroll.hasClients) {
      _stopAutoScroll();
      return;
    }
    final ScrollPosition position = _scroll.position;
    final double next = (position.pixels + _autoScrollStep).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    if (next == position.pixels) {
      _stopAutoScroll();
      return;
    }
    position.jumpTo(next);
    final Offset? pointer = _lastPointer;
    if (pointer != null) {
      _updateDropPosition(pointer);
    }
  }

  void _stopAutoScroll() {
    _autoScroll?.cancel();
    _autoScroll = null;
    _autoScrollStep = 0;
  }

  // -- build ---------------------------------------------------------------
  Widget _buildCard(ResourceItem item) {
    final bool dragged = item.id == _draggingId;
    final Widget card = _ResourceCard(
      key: _keyFor(item),
      item: item,
      mode: widget.mode,
      selected: item.id == widget.selectedId,
      actions: widget.actions,
      reorderEnabled: widget.reorderEnabled,
      onSelected: () => widget.onSelected(item),
      onPreview: widget.onPreview,
      onDragStarted: () => _handleDragStarted(item),
      onDragUpdate: _handleDragUpdate,
      onDragEnd: _handleDragEnd,
    );
    if (!dragged) {
      return card;
    }
    // The drag session belongs to the Draggable inside this card, so the card
    // must stay mounted: keep it invisible above the drop-slot placeholder
    // instead of removing it from the tree.
    return IgnorePointer(
      child: Stack(
        children: <Widget>[
          const Positioned.fill(
            child: _DragPlaceholder(
              key: ValueKey<String>('grid-drop-placeholder'),
            ),
          ),
          Positioned.fill(child: Opacity(opacity: 0, child: card)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (widget.items.isEmpty) {
      return widget.emptyState ?? const SizedBox.shrink();
    }
    return Scrollbar(
      controller: _scroll,
      child: LayoutBuilder(
        builder: (BuildContext viewportContext, BoxConstraints constraints) {
          _viewportBox = viewportContext.findRenderObject() as RenderBox?;
          final double width = constraints.maxWidth;
          _columns = math.max(
            1,
            (width / (_maxCardExtent + _cardSpacing)).ceil(),
          );
          _cardWidth = (width + _cardSpacing) / _columns - _cardSpacing;
          final int rows = math.max(1, (_displayItems.length / _columns).ceil());
          final double height =
              rows * _rowHeight + (rows - 1) * _cardSpacing;
          return SingleChildScrollView(
            controller: _scroll,
            primary: false,
            child: SizedBox(
              key: _gridKey,
              width: width,
              height: height,
              child: Stack(
                clipBehavior: Clip.none,
                children: <Widget>[
                  for (int index = 0; index < _displayItems.length; index++)
                    AnimatedPositioned(
                      key: ValueKey<String>(
                        'grid-card-${_displayItems[index].id}',
                      ),
                      duration: _draggingId == null
                          ? Duration.zero
                          : _shiftDuration,
                      curve: Curves.easeOutCubic,
                      left:
                          (index % _columns) * (_cardWidth + _cardSpacing),
                      top:
                          (index ~/ _columns) * (_rowHeight + _cardSpacing),
                      width: _cardWidth,
                      height: _rowHeight,
                      child: _buildCard(_displayItems[index]),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _ResourceCard extends StatefulWidget {
  const _ResourceCard({
    super.key,
    required this.item,
    required this.mode,
    required this.selected,
    required this.actions,
    required this.reorderEnabled,
    required this.onSelected,
    this.onPreview,
    required this.onDragStarted,
    required this.onDragUpdate,
    required this.onDragEnd,
  });

  final ResourceItem item;
  final ViewMode mode;
  final bool selected;
  final ResourceTableActions actions;
  final bool reorderEnabled;
  final VoidCallback onSelected;
  final ValueChanged<ResourceItem>? onPreview;
  final VoidCallback onDragStarted;
  final ValueChanged<Offset> onDragUpdate;
  final VoidCallback onDragEnd;

  @override
  State<_ResourceCard> createState() => _ResourceCardState();
}

class _ResourceCardState extends State<_ResourceCard> {
  bool _hovered = false;

  Future<void> _showContextMenu(
    BuildContext context,
    Offset globalPosition,
  ) {
    return showResourceContextMenu(
      context,
      item: widget.item,
      mode: widget.mode,
      actions: widget.actions,
      globalPosition: globalPosition,
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext layoutContext, BoxConstraints constraints) {
        return _buildCard(
          context,
          grip: _buildGrip(layoutContext, constraints),
        );
      },
    );
  }

  /// Drag source. The handle is the only grab area; the feedback is a full-size
  /// ghost of the card, anchored so it keeps the pointer's original offset.
  Widget _buildGrip(BuildContext layoutContext, BoxConstraints constraints) {
    final Widget grip = MouseRegion(
      cursor: SystemMouseCursors.grab,
      child: ReorderGrip(
        visible: _hovered,
        enabled: widget.reorderEnabled,
      ),
    );
    if (!widget.reorderEnabled) {
      return grip;
    }
    return Draggable<Object>(
      data: widget.item.id,
      dragAnchorStrategy: (
        Draggable<Object> draggable,
        BuildContext context,
        Offset position,
      ) {
        final RenderBox? box =
            layoutContext.findRenderObject() as RenderBox?;
        return box == null ? Offset.zero : box.globalToLocal(position);
      },
      feedback: MouseRegion(
        cursor: SystemMouseCursors.grabbing,
        child: SizedBox(
          width: constraints.maxWidth,
          height: constraints.maxHeight,
          child: _CardGhost(item: widget.item),
        ),
      ),
      onDragStarted: widget.onDragStarted,
      onDragUpdate: (DragUpdateDetails details) =>
          widget.onDragUpdate(details.globalPosition),
      onDragEnd: (DraggableDetails details) => widget.onDragEnd(),
      onDraggableCanceled: (Velocity velocity, Offset offset) {},
      child: grip,
    );
  }

  Widget _buildCard(BuildContext context, {required Widget grip}) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semantic;
    final AppStrings t = context.l10n;
    final ResourceItem item = widget.item;
    final bool selected = widget.selected;
    final bool missing = item.pathState.isMissing;

    final Color background = selected
        ? scheme.primaryContainer
        : missing
        ? semantic.missingRowTint
        : _hovered
        ? scheme.surfaceContainerHigh
        : scheme.surfaceContainerLowest;
    final Color foreground =
        selected ? scheme.onPrimaryContainer : scheme.onSurface;
    final Color muted = selected
        ? scheme.onPrimaryContainer.withValues(alpha: 0.72)
        : scheme.onSurfaceVariant;
    final (IconData kindIcon, String kindLabel) = switch (item.kind) {
      ResourceKind.link => (Icons.link, t.t('col_url')),
      ResourceKind.folder => (Icons.folder_outlined, t.t('kind_folder')),
      ResourceKind.file => (Icons.description_outlined, t.t('kind_file')),
    };

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: Listener(
        onPointerDown: (PointerDownEvent event) {
          if (event.buttons == kPrimaryButton) {
            widget.onSelected();
          }
        },
        child: Material(
          color: background,
          shape: RoundedRectangleBorder(
            borderRadius: AppRadius.mdAll,
            side: BorderSide(
              color: selected ? scheme.primary : scheme.outlineVariant,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: widget.onPreview != null
                ? () => widget.onPreview!(item)
                : widget.onSelected,
            onDoubleTap: () => widget.actions.onOpen?.call(item),
            onSecondaryTapDown: (TapDownDetails details) =>
                _showContextMenu(context, details.globalPosition),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      grip,
                      const SizedBox(width: AppSpacing.xs),
                      Container(
                        width: 28,
                        height: 28,
                        decoration: BoxDecoration(
                          color: selected
                              ? scheme.onPrimaryContainer.withValues(alpha: 0.1)
                              : scheme.surfaceContainerHigh,
                          borderRadius: BorderRadius.circular(AppRadius.xs),
                        ),
                        child: Icon(kindIcon, size: 16, color: muted),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Text(
                          item.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: foreground,
                          ),
                        ),
                      ),
                      if (widget.actions.onToggleFavorite != null)
                        Tooltip(
                          message: item.favorite
                              ? t.t('unfavorite')
                              : t.t('favorite'),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(AppRadius.xs),
                            onTap: () =>
                                widget.actions.onToggleFavorite?.call(item),
                            child: Padding(
                              padding: const EdgeInsets.all(2),
                              child: Icon(
                                item.favorite
                                    ? Icons.star
                                    : Icons.star_border,
                                size: 16,
                                color: item.favorite
                                    ? semantic.favorite
                                    : muted,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    item.path,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12,
                      color: missing ? semantic.danger : muted,
                    ),
                  ),
                  const Spacer(),
                  Row(
                    children: <Widget>[
                      Icon(kindIcon, size: 12, color: muted),
                      const SizedBox(width: 4),
                      Text(
                        kindLabel,
                        style: TextStyle(fontSize: 11, color: muted),
                      ),
                      if (!item.isUncategorized) ...<Widget>[
                        const SizedBox(width: AppSpacing.sm),
                        StatusPill(
                          label: item.category,
                          foreground: selected
                              ? scheme.onPrimaryContainer
                              : scheme.onSurfaceVariant,
                          background: selected
                              ? scheme.onPrimaryContainer
                                  .withValues(alpha: 0.12)
                              : scheme.surfaceContainerHigh,
                        ),
                      ],
                      const Spacer(),
                      Text(
                        formatAddedAt(item.createdAt),
                        style: TextStyle(
                          fontSize: 11,
                          color: muted,
                          fontFeatures: const <FontFeature>[
                            FontFeature.tabularFigures(),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Full-size card preview that follows the pointer while dragging.
class _CardGhost extends StatelessWidget {
  const _CardGhost({required this.item});

  final ResourceItem item;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppStrings t = context.l10n;
    final (IconData kindIcon, String kindLabel) = switch (item.kind) {
      ResourceKind.link => (Icons.link, t.t('col_url')),
      ResourceKind.folder => (Icons.folder_outlined, t.t('kind_folder')),
      ResourceKind.file => (Icons.description_outlined, t.t('kind_file')),
    };
    return Material(
      elevation: 10,
      color: scheme.surfaceContainerHigh,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdAll,
        side: BorderSide(color: scheme.primary.withValues(alpha: 0.6)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(kindIcon, size: 16, color: scheme.onSurfaceVariant),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: scheme.onSurface,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              item.path,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 12,
                color: scheme.onSurfaceVariant,
              ),
            ),
            const Spacer(),
            Text(
              kindLabel,
              style: TextStyle(
                fontSize: 11,
                color: scheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Soft placeholder left in the grid slot while the card is being dragged.
class _DragPlaceholder extends StatelessWidget {
  const _DragPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: 0.05),
        borderRadius: AppRadius.mdAll,
        border: Border.all(
          color: scheme.primary.withValues(alpha: 0.35),
          width: 1.5,
        ),
      ),
      child: Center(
        child: Icon(
          Icons.drag_indicator,
          size: 18,
          color: scheme.primary.withValues(alpha: 0.45),
        ),
      ),
    );
  }
}
