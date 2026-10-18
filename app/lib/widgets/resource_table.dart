/// The resource table.
///
/// Replaces the `ttk.Treeview` with 8 columns (`resource_hub.pyw:2165`). A hand
/// rolled table is used instead of [DataTable] because the legacy layout relies on
/// proportional column widths, per-row hover, a red tint for missing paths, and a
/// right-click context menu — all of which fight DataTable's fixed-width model.
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../design/app_theme.dart';
import '../design/app_tokens.dart';
import '../l10n/strings_scope.dart';
import '../models/resource_item.dart';
import '../util/formatters.dart';
import 'app_card.dart';
import 'reorder_grip.dart';

/// Moves [item] to [targetIndex] of the visible list *after* removing it.
///
/// Both views report this shape: the table converts `ReorderableListView`'s
/// `(oldIndex, newIndex)` into it, the grid converts its drop slot. The shell
/// translates it into a full-collection order before saving.
typedef ResourceMoveCallback = void Function(ResourceItem item, int targetIndex);

/// Callbacks wired into the row context menu. Any null entry hides that item.
class ResourceTableActions {
  const ResourceTableActions({
    this.onOpen,
    this.onReveal,
    this.onEdit,
    this.onToggleFavorite,
    this.onCopyPath,
    this.onDelete,
  });

  final ValueChanged<ResourceItem>? onOpen;
  final ValueChanged<ResourceItem>? onReveal;
  final ValueChanged<ResourceItem>? onEdit;
  final ValueChanged<ResourceItem>? onToggleFavorite;
  final ValueChanged<ResourceItem>? onCopyPath;
  final ValueChanged<ResourceItem>? onDelete;
}

/// Right-click menu shared by the list table and the grid cards.
Future<void> showResourceContextMenu(
  BuildContext context, {
  required ResourceItem item,
  required ViewMode mode,
  required ResourceTableActions actions,
  required Offset globalPosition,
}) async {
  final AppStrings t = context.l10n;
  final RenderBox overlay =
      Overlay.of(context).context.findRenderObject()! as RenderBox;
  final RelativeRect position = RelativeRect.fromLTRB(
    globalPosition.dx,
    globalPosition.dy,
    overlay.size.width - globalPosition.dx,
    overlay.size.height - globalPosition.dy,
  );

  final String favoriteLabel =
      item.favorite ? t.t('unfavorite') : t.t('favorite');
  final String copyLabel = mode.isLinks ? t.t('copy_url') : t.t('copy_path');

  final String? choice = await showMenu<String>(
    context: context,
    position: position,
    items: <PopupMenuEntry<String>>[
      if (actions.onOpen != null)
        PopupMenuItem<String>(
          value: 'open',
          child: _MenuRow(icon: Icons.open_in_new, label: t.t('open')),
        ),
      if (actions.onReveal != null && !mode.isLinks)
        PopupMenuItem<String>(
          value: 'reveal',
          child: _MenuRow(
            icon: Icons.folder_open_outlined,
            label: t.t('open_location'),
          ),
        ),
      if (actions.onEdit != null)
        PopupMenuItem<String>(
          value: 'edit',
          child: _MenuRow(icon: Icons.edit_outlined, label: t.t('edit')),
        ),
      if (actions.onToggleFavorite != null)
        PopupMenuItem<String>(
          value: 'favorite',
          child: _MenuRow(
            icon: item.favorite ? Icons.star_outline : Icons.star_border_outlined,
            label: favoriteLabel,
          ),
        ),
      if (actions.onCopyPath != null)
        PopupMenuItem<String>(
          value: 'copy',
          child: _MenuRow(icon: Icons.copy_outlined, label: copyLabel),
        ),
      if (actions.onDelete != null) ...<PopupMenuEntry<String>>[
        const PopupMenuDivider(),
        PopupMenuItem<String>(
          value: 'delete',
          child: _MenuRow(
            icon: Icons.delete_outline,
            label: t.t('delete'),
            danger: true,
          ),
        ),
      ],
    ],
  );

  switch (choice) {
    case 'open':
      actions.onOpen?.call(item);
    case 'reveal':
      actions.onReveal?.call(item);
    case 'edit':
      actions.onEdit?.call(item);
    case 'favorite':
      actions.onToggleFavorite?.call(item);
    case 'copy':
      actions.onCopyPath?.call(item);
    case 'delete':
      actions.onDelete?.call(item);
  }
}

/// One column definition. Either a fixed [width] or a proportional [flex].
class _Column {
  const _Column({
    required this.key,
    required this.label,
    this.width,
    this.flex,
    this.align = Alignment.centerLeft,
  }) : assert(width != null || flex != null, 'column needs width or flex');

  final String key;
  final String label;
  final double? width;
  final int? flex;
  final Alignment align;
}

class ResourceTable extends StatelessWidget {
  const ResourceTable({
    super.key,
    required this.items,
    required this.mode,
    required this.selectedId,
    required this.onSelected,
    required this.actions,
    required this.scrollController,
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
  final ScrollController scrollController;

  /// False while a search is active (or a reorder is already being saved).
  final bool reorderEnabled;
  final ResourceMoveCallback onMoveItem;

  /// A completed click (not a drag): opens the details panel.
  final ValueChanged<ResourceItem>? onPreview;
  final Widget? emptyState;

  List<_Column> _columns(BuildContext context) {
    final AppStrings t = context.l10n;
    return <_Column>[
      _Column(
        key: 'favorite',
        label: t.t('col_favorite'),
        // Wide enough for the English header "Favorite" in Microsoft YaHei UI;
        // Chinese "收藏" is shorter. Measured from the Phase 2 screenshot pass.
        width: 96,
        align: Alignment.center,
      ),
      _Column(key: 'name', label: t.t('col_name'), flex: 3),
      _Column(key: 'kind', label: t.t('col_kind'), width: 82),
      _Column(key: 'state', label: t.t('col_state'), width: 100),
      _Column(key: 'category', label: t.t('col_category'), flex: 2),
      _Column(key: 'added', label: t.t('col_added_at'), width: 132),
      _Column(
        key: 'path',
        label: t.t(mode.isLinks ? 'col_url' : 'col_path'),
        flex: 4,
      ),
      _Column(key: 'notes', label: t.t('col_notes'), flex: 2),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final List<_Column> columns = _columns(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        borderRadius: AppRadius.mdAll,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: ClipRRect(
        borderRadius: AppRadius.mdAll,
        child: Column(
          children: <Widget>[
            _TableHeader(columns: columns),
            Expanded(
              child: items.isEmpty
                  ? (emptyState ?? const SizedBox.shrink())
                  : Scrollbar(
                      controller: scrollController,
                      child: ReorderableListView.builder(
                        scrollController: scrollController,
                        primary: false,
                        buildDefaultDragHandles: false,
                        itemExtent: AppSizes.tableRowHeight,
                        itemCount: items.length,
                        // `onReorderItem` reports the insertion index *after*
                        // the dragged row has been removed, which is exactly the
                        // position `onMoveItem` expects.
                        onReorderItem: (int oldIndex, int newIndex) {
                          if (newIndex == oldIndex) {
                            return;
                          }
                          onMoveItem(items[oldIndex], newIndex);
                        },
                        proxyDecorator: (
                          Widget child,
                          int index,
                          Animation<double> animation,
                        ) {
                          return AnimatedBuilder(
                            animation: animation,
                            builder: (BuildContext context, Widget? _) {
                              return Material(
                                elevation: 8,
                                color: scheme.surfaceContainerHigh,
                                borderRadius: AppRadius.smAll,
                                clipBehavior: Clip.antiAlias,
                                child: child,
                              );
                            },
                          );
                        },
                        itemBuilder: (BuildContext context, int index) {
                          final ResourceItem item = items[index];
                          return _TableRow(
                            key: ValueKey<String>(item.id),
                            index: index,
                            item: item,
                            columns: columns,
                            mode: mode,
                            selected: item.id == selectedId,
                            reorderEnabled: reorderEnabled,
                            onTap: () => onSelected(item),
                            onPreview: onPreview,
                            actions: actions,
                          );
                        },
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TableHeader extends StatelessWidget {
  const _TableHeader({required this.columns});

  final List<_Column> columns;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    return Container(
      height: AppSizes.tableHeaderHeight,
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: <Widget>[
          // Leading grip column: keeps the header aligned with the row handles.
          const SizedBox(width: AppSizes.tableGripWidth),
          ...columns.map(
            (_Column column) => _TableCell(
              column: column,
              child: Text(
                column.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: text.labelSmall?.copyWith(
                  color: scheme.onSurfaceVariant,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.3,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TableRow extends StatefulWidget {
  const _TableRow({
    super.key,
    required this.index,
    required this.item,
    required this.columns,
    required this.mode,
    required this.selected,
    required this.reorderEnabled,
    required this.onTap,
    this.onPreview,
    required this.actions,
  });

  final int index;
  final ResourceItem item;
  final List<_Column> columns;
  final ViewMode mode;
  final bool selected;
  final bool reorderEnabled;
  final VoidCallback onTap;
  final ValueChanged<ResourceItem>? onPreview;
  final ResourceTableActions actions;

  @override
  State<_TableRow> createState() => _TableRowState();
}

class _TableRowState extends State<_TableRow> {
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
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semantic;
    final ResourceItem item = widget.item;
    final bool selected = widget.selected;
    final bool missing = item.pathState.isMissing;

    final Color background = selected
        ? scheme.primaryContainer
        : missing
        ? semantic.missingRowTint
        : _hovered
        ? scheme.primary.withValues(alpha: 0.05)
        : Colors.transparent;
    final Color foreground = selected
        ? scheme.onPrimaryContainer
        : scheme.onSurface;
    final Color muted = selected
        ? scheme.onPrimaryContainer.withValues(alpha: 0.72)
        : scheme.onSurfaceVariant;

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      // `onDoubleTap` below installs a double-tap recogniser, and a competing
      // recogniser delays InkWell.onTap by ~300 ms (the double-tap timeout).
      // Selecting on raw pointer-down keeps the highlight instant; the drag case
      // does not matter because selection is only a highlight.
      child: Listener(
        onPointerDown: (PointerDownEvent event) {
          if (event.buttons == kPrimaryButton) {
            widget.onTap();
          }
        },
        child: Material(
          color: background,
          child: InkWell(
            onTap: widget.onPreview != null
                ? () => widget.onPreview!(item)
                : widget.onTap,
            onDoubleTap: () => widget.actions.onOpen?.call(item),
            onSecondaryTapDown: (TapDownDetails details) =>
                _showContextMenu(context, details.globalPosition),
            child: Container(
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: scheme.outlineVariant.withValues(alpha: 0.55),
                  ),
                ),
              ),
              child: Row(
                children: <Widget>[
                  SizedBox(
                    width: AppSizes.tableGripWidth,
                    child: Center(
                      child: ReorderableDragStartListener(
                        index: widget.index,
                        enabled: widget.reorderEnabled,
                        child: ReorderGrip(
                          visible: _hovered,
                          enabled: widget.reorderEnabled,
                        ),
                      ),
                    ),
                  ),
                  _TableCell(
                    column: widget.columns[0],
                    child: Icon(
                      item.favorite ? Icons.star : Icons.star_border,
                      size: 17,
                      color: item.favorite ? semantic.favorite : muted,
                    ),
                  ),
                  _TableCell(
                    column: widget.columns[1],
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
                  _TableCell(
                    column: widget.columns[2],
                    child: _KindCell(item: item, color: muted),
                  ),
                  _TableCell(
                    column: widget.columns[3],
                    child: _StateCell(item: item),
                  ),
                  _TableCell(
                    column: widget.columns[4],
                    child: item.isUncategorized
                        ? Text(
                            context.l10n.t('uncategorized'),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 12, color: muted),
                          )
                        : StatusPill(
                            label: item.category,
                            // Neutral chip: the accent is reserved for the
                            // primary action, selection and focus.
                            foreground: selected
                                ? scheme.onPrimaryContainer
                                : scheme.onSurfaceVariant,
                            background: selected
                                ? scheme.onPrimaryContainer
                                    .withValues(alpha: 0.10)
                                : scheme.surfaceContainerHigh,
                          ),
                  ),
                  _TableCell(
                    column: widget.columns[5],
                    child: Text(
                      formatAddedAt(item.createdAt),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        color: muted,
                        fontFeatures: const <FontFeature>[
                          FontFeature.tabularFigures(),
                        ],
                      ),
                    ),
                  ),
                  _TableCell(
                    column: widget.columns[6],
                    child: Tooltip(
                      message: item.path,
                      waitDuration: const Duration(milliseconds: 600),
                      child: Text(
                        item.path,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          color: missing ? semantic.danger : muted,
                        ),
                      ),
                    ),
                  ),
                  _TableCell(
                    column: widget.columns[7],
                    child: Text(
                      item.note.isEmpty ? '—' : item.note,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: muted),
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
}

class _KindCell extends StatelessWidget {
  const _KindCell({required this.item, required this.color});

  final ResourceItem item;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final (IconData icon, String key) = switch (item.kind) {
      ResourceKind.link => (Icons.link, 'col_url'),
      ResourceKind.folder => (Icons.folder_outlined, 'kind_folder'),
      ResourceKind.file => (Icons.description_outlined, 'kind_file'),
    };
    final String label = item.kind == ResourceKind.link
        ? context.l10n.t('col_url')
        : context.l10n.t(key);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 5),
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: color),
          ),
        ),
      ],
    );
  }
}

class _StateCell extends StatelessWidget {
  const _StateCell({required this.item});

  final ResourceItem item;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors semantic = context.semantic;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    switch (item.pathState) {
      case PathState.ok:
        return StatusPill(
          label: context.l10n.t('path_ok'),
          foreground: semantic.success,
          background: semantic.successContainer,
          icon: Icons.check,
        );
      case PathState.missing:
        return StatusPill(
          label: context.l10n.t('path_missing'),
          foreground: semantic.danger,
          background: semantic.dangerContainer,
          icon: Icons.error_outline,
        );
      case PathState.unknown:
        return Text(
          '—',
          style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
        );
    }
  }
}

class _TableCell extends StatelessWidget {
  const _TableCell({required this.column, required this.child});

  final _Column column;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final Widget content = Align(alignment: column.align, child: child);
    final EdgeInsetsGeometry padding = const EdgeInsets.symmetric(
      horizontal: AppSpacing.md,
    );
    if (column.width != null) {
      return SizedBox(
        width: column.width,
        child: Padding(padding: padding, child: content),
      );
    }
    return Expanded(
      flex: column.flex!,
      child: Padding(padding: padding, child: content),
    );
  }
}

class _MenuRow extends StatelessWidget {
  const _MenuRow({
    required this.icon,
    required this.label,
    this.danger = false,
  });

  final IconData icon;
  final String label;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final Color color = danger
        ? context.semantic.danger
        : Theme.of(context).colorScheme.onSurface;
    return Row(
      children: <Widget>[
        Icon(icon, size: 16, color: color),
        const SizedBox(width: AppSpacing.md),
        Text(label, style: TextStyle(fontSize: 13, color: color)),
      ],
    );
  }
}
