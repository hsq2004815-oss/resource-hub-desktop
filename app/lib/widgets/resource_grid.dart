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
  final Widget? emptyState;

  @override
  State<ResourceGrid> createState() => _ResourceGridState();
}

class _ResourceGridState extends State<ResourceGrid> {
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _cardKeys = <String, GlobalKey>{};

  int? _draggingIndex;
  int? _dropSlot;
  Offset? _lastPointer;
  Timer? _autoScroll;
  double _autoScrollStep = 0;
  RenderBox? _viewportBox;

  static const double _edgeZone = 44;

  @override
  void dispose() {
    _autoScroll?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  GlobalKey _keyFor(ResourceItem item) =>
      _cardKeys.putIfAbsent(item.id, GlobalKey.new);

  // -- drag lifecycle ------------------------------------------------------
  void _handleDragStarted(int index) {
    setState(() {
      _draggingIndex = index;
      _dropSlot = index;
    });
  }

  void _handleDragUpdate(Offset globalPosition) {
    _lastPointer = globalPosition;
    _updateDropSlot(globalPosition);
    _updateAutoScroll(globalPosition);
  }

  void _handleDragEnd() {
    _stopAutoScroll();
    final int? from = _draggingIndex;
    final int? slot = _dropSlot;
    setState(() {
      _draggingIndex = null;
      _dropSlot = null;
      _lastPointer = null;
    });
    if (from == null || slot == null) {
      return;
    }
    final int target = slot > from ? slot - 1 : slot;
    if (target == from) {
      return;
    }
    widget.onMoveItem(widget.items[from], target);
  }

  /// Finds the insertion slot (0..items.length) for [global].
  ///
  /// The pointer over a card decides before/after by its x position relative to
  /// the card centre; gaps and empty space fall back to the nearest card so the
  /// indicator always has a sensible place to land.
  void _updateDropSlot(Offset global) {
    final RenderBox? viewport = _viewportBox;
    if (viewport == null) {
      return;
    }
    final Rect viewportRect =
        viewport.localToGlobal(Offset.zero) & viewport.size;
    if (!viewportRect.inflate(48).contains(global)) {
      if (_dropSlot != null) {
        setState(() => _dropSlot = null);
      }
      return;
    }

    int? slot;
    double bestDistance = double.infinity;
    for (int index = 0; index < widget.items.length; index++) {
      final BuildContext? cardContext =
          _cardKeys[widget.items[index].id]?.currentContext;
      final RenderBox? box =
          cardContext?.findRenderObject() as RenderBox?;
      if (box == null || !box.hasSize) {
        continue;
      }
      final Rect rect = box.localToGlobal(Offset.zero) & box.size;
      final Offset center = rect.center;
      if (rect.contains(global)) {
        slot = global.dx >= center.dx ? index + 1 : index;
        break;
      }
      final double distance = (center - global).distance;
      if (distance < bestDistance) {
        bestDistance = distance;
        final bool after;
        if (global.dy > rect.bottom) {
          after = true;
        } else if (global.dy < rect.top) {
          after = false;
        } else {
          after = global.dx >= center.dx;
        }
        slot = after ? index + 1 : index;
      }
    }
    if (slot != null && slot != _dropSlot) {
      setState(() => _dropSlot = slot);
    }
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
      delta = -14 * (1 - dy / _edgeZone);
    } else if (dy > rect.height - _edgeZone) {
      delta = 14 * (1 - (rect.height - dy) / _edgeZone);
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
      _updateDropSlot(pointer);
    }
  }

  void _stopAutoScroll() {
    _autoScroll?.cancel();
    _autoScroll = null;
    _autoScrollStep = 0;
  }

  // -- build ---------------------------------------------------------------
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
          return GridView.builder(
            controller: _scroll,
            primary: false,
            padding: EdgeInsets.zero,
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 360,
              mainAxisExtent: 132,
              crossAxisSpacing: AppSpacing.sm,
              mainAxisSpacing: AppSpacing.sm,
            ),
            itemCount: widget.items.length,
            itemBuilder: (BuildContext context, int index) {
              final ResourceItem item = widget.items[index];
              return _ResourceCard(
                key: _keyFor(item),
                index: index,
                item: item,
                mode: widget.mode,
                selected: item.id == widget.selectedId,
                actions: widget.actions,
                reorderEnabled: widget.reorderEnabled,
                dragging: _draggingIndex == index,
                showLeftLine: _dropSlot == index,
                showRightLine: _dropSlot == widget.items.length &&
                    index == widget.items.length - 1,
                onSelected: () => widget.onSelected(item),
                onDragStarted: () => _handleDragStarted(index),
                onDragUpdate: _handleDragUpdate,
                onDragEnd: _handleDragEnd,
              );
            },
          );
        },
      ),
    );
  }
}

class _ResourceCard extends StatefulWidget {
  const _ResourceCard({
    super.key,
    required this.index,
    required this.item,
    required this.mode,
    required this.selected,
    required this.actions,
    required this.reorderEnabled,
    required this.dragging,
    required this.showLeftLine,
    required this.showRightLine,
    required this.onSelected,
    required this.onDragStarted,
    required this.onDragUpdate,
    required this.onDragEnd,
  });

  final int index;
  final ResourceItem item;
  final ViewMode mode;
  final bool selected;
  final ResourceTableActions actions;
  final bool reorderEnabled;
  final bool dragging;
  final bool showLeftLine;
  final bool showRightLine;
  final VoidCallback onSelected;
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
        final Widget card = Opacity(
          opacity: widget.dragging ? 0.45 : 1,
          child: _buildCard(context, grip: _buildGrip(layoutContext, constraints)),
        );
        return Stack(
          clipBehavior: Clip.none,
          children: <Widget>[
            Positioned.fill(child: card),
            if (widget.showLeftLine) const _DropLine(left: -4),
            if (widget.showRightLine) const _DropLine(right: -4),
          ],
        );
      },
    );
  }

  /// Drag source. The handle is the only grab area; the feedback is a full-size
  /// ghost of the card, anchored so it keeps the pointer's original offset.
  Widget _buildGrip(BuildContext layoutContext, BoxConstraints constraints) {
    final Widget grip = ReorderGrip(
      visible: _hovered || widget.dragging,
      enabled: widget.reorderEnabled,
    );
    if (!widget.reorderEnabled) {
      return grip;
    }
    return Draggable<int>(
      data: widget.index,
      dragAnchorStrategy: (
        Draggable<Object> draggable,
        BuildContext context,
        Offset position,
      ) {
        final RenderBox? box =
            layoutContext.findRenderObject() as RenderBox?;
        return box == null ? Offset.zero : box.globalToLocal(position);
      },
      feedback: SizedBox(
        width: constraints.maxWidth,
        height: constraints.maxHeight,
        child: _CardGhost(item: widget.item),
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
            onTap: widget.onSelected,
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

/// 2px primary insertion marker drawn in the gap next to a card.
class _DropLine extends StatelessWidget {
  const _DropLine({this.left, this.right});

  final double? left;
  final double? right;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Positioned(
      left: left,
      right: right,
      top: AppSpacing.sm,
      bottom: AppSpacing.sm,
      child: Container(
        width: 2,
        decoration: BoxDecoration(
          color: scheme.primary,
          borderRadius: BorderRadius.circular(1),
        ),
      ),
    );
  }
}
