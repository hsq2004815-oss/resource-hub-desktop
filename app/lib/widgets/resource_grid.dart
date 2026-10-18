/// Grid layout for the resource collection.
///
/// Same data and actions as [ResourceTable], just a different presentation:
/// the workspace offers a list/grid switch and both views must behave
/// identically (click selects, double-click opens, right-click shows the same
/// context menu).
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../design/app_theme.dart';
import '../design/app_tokens.dart';
import '../l10n/strings_scope.dart';
import '../models/resource_item.dart';
import '../util/formatters.dart';
import 'app_card.dart';
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
    this.emptyState,
  });

  final List<ResourceItem> items;
  final ViewMode mode;
  final String? selectedId;
  final ValueChanged<ResourceItem> onSelected;
  final ResourceTableActions actions;
  final Widget? emptyState;

  @override
  State<ResourceGrid> createState() => _ResourceGridState();
}

class _ResourceGridState extends State<ResourceGrid> {
  final ScrollController _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.items.isEmpty) {
      return widget.emptyState ?? const SizedBox.shrink();
    }
    return Scrollbar(
      controller: _scroll,
      child: GridView.builder(
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
            item: item,
            mode: widget.mode,
            selected: item.id == widget.selectedId,
            actions: widget.actions,
            onSelected: () => widget.onSelected(item),
          );
        },
      ),
    );
  }
}

class _ResourceCard extends StatefulWidget {
  const _ResourceCard({
    required this.item,
    required this.mode,
    required this.selected,
    required this.actions,
    required this.onSelected,
  });

  final ResourceItem item;
  final ViewMode mode;
  final bool selected;
  final ResourceTableActions actions;
  final VoidCallback onSelected;

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
