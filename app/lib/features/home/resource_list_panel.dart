/// Resource workspace: compact header (title + count + view/mode controls + add
/// action), one search/filter/tool row, then the list or grid.
///
/// Layout notes:
/// * The app bar above is a separate compact widget; everything that acts on the
///   collection lives here so the list gets the vertical space.
/// * The title area is plain text on the app surface — no card, no tinted band.
/// * `添加资源` is the only filled (primary) control in the header.
library;

import 'package:flutter/material.dart';

import '../../design/app_theme.dart';
import '../../design/app_tokens.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../models/resource_item.dart';
import '../../widgets/app_button.dart';
import '../../widgets/app_fields.dart';
import '../../widgets/resource_grid.dart';
import '../../widgets/resource_table.dart';
import '../../widgets/status_bar.dart';

class ResourceListPanel extends StatelessWidget {
  const ResourceListPanel({
    super.key,
    required this.mode,
    required this.items,
    required this.allItems,
    required this.categories,
    required this.summary,
    required this.selectedId,
    required this.searchController,
    this.searchFocusNode,
    required this.categoryFilter,
    required this.favoritesOnly,
    required this.scrollController,
    required this.actions,
    required this.layout,
    required this.onLayoutChanged,
    required this.onModeChanged,
    required this.onAdd,
    required this.onSelected,
    this.onPreview,
    required this.onSearchChanged,
    required this.onCategoryFilterChanged,
    required this.onToggleFavoritesOnly,
    required this.onOpenSelected,
    required this.onEditSelected,
    required this.onDeleteSelected,
    required this.onToggleFavoriteSelected,
    required this.onCheckPaths,
    required this.onImport,
    required this.onExport,
    required this.reorderEnabled,
    required this.onMoveItem,
    required this.onSortByAdded,
    this.detailsPanel,
  });

  final ViewMode mode;
  final List<ResourceItem> items;
  final List<ResourceItem> allItems;
  final List<String> categories;
  final ListSummary summary;
  final String? selectedId;
  final TextEditingController searchController;
  final FocusNode? searchFocusNode;
  final String categoryFilter;
  final bool favoritesOnly;
  final ScrollController scrollController;
  final ResourceTableActions actions;
  final ResourceLayout layout;
  final ValueChanged<ResourceLayout> onLayoutChanged;
  final ValueChanged<ViewMode> onModeChanged;
  final VoidCallback onAdd;
  final ValueChanged<ResourceItem> onSelected;

  /// Single click on a row/card: opens the details panel.
  final ValueChanged<ResourceItem>? onPreview;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<String> onCategoryFilterChanged;
  final VoidCallback onToggleFavoritesOnly;
  final VoidCallback onOpenSelected;
  final VoidCallback onEditSelected;
  final VoidCallback onDeleteSelected;
  final VoidCallback onToggleFavoriteSelected;
  final VoidCallback onCheckPaths;
  final VoidCallback onImport;
  final VoidCallback onExport;

  /// Dragging is disabled while a search is active and while a reorder is being
  /// saved; both views show the same dimmed handle.
  final bool reorderEnabled;
  final ResourceMoveCallback onMoveItem;

  /// One-shot "sort by date added (newest first)" from the overflow menu.
  final VoidCallback onSortByAdded;

  /// Right-hand details panel, floated over the list content so the workspace
  /// header/toolbar above stays clickable.
  final Widget? detailsPanel;

  bool get _hasSelection => selectedId != null;

  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final bool isLinks = mode.isLinks;

    final String summaryText = _buildSummary(t, summary);
    // The status bar already reports the unfiltered "showing X of Y" summary;
    // the header only repeats it when a filter is active.
    final bool showSummary =
        summary.hasCategory || summary.hasQuery || favoritesOnly;
    final List<String> filterEntries = <String>[
      kAllCategories,
      ...categories,
    ];
    final Widget emptyState = AppEmptyState(
      icon: isLinks ? Icons.link_off : Icons.folder_off_outlined,
      title: t.t(isLinks ? 'empty_links' : 'empty_folders'),
      hint: allItems.isEmpty
          ? t.t(isLinks ? 'form_tip_links' : 'form_tip_folders')
          : t.t('show_all_items'),
    );

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.xl,
        AppSpacing.sm,
        AppSpacing.xl,
        AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          // -- header: title + auxiliary count + view/mode/add --------------
          Row(
            children: <Widget>[
              Expanded(
                child: Row(
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        t.t(
                          isLinks ? 'collection_links' : 'collection_folders',
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: text.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.xs + 2),
                    Text(
                      '(${summary.total})',
                      style: text.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                    if (showSummary) ...<Widget>[
                      const SizedBox(width: AppSpacing.md),
                      Flexible(
                        child: Text(
                          summaryText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: text.bodySmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              SegmentedButton<ViewMode>(
                segments: <ButtonSegment<ViewMode>>[
                  ButtonSegment<ViewMode>(
                    value: ViewMode.links,
                    icon: const Icon(Icons.link, size: 14),
                    label: Text(t.t('switch_to_links')),
                  ),
                  ButtonSegment<ViewMode>(
                    value: ViewMode.folders,
                    icon: const Icon(Icons.folder_outlined, size: 14),
                    label: Text(t.t('switch_to_folders')),
                  ),
                ],
                selected: <ViewMode>{mode},
                showSelectedIcon: false,
                onSelectionChanged: (Set<ViewMode> value) =>
                    onModeChanged(value.first),
              ),
              const SizedBox(width: AppSpacing.sm),
              SegmentedButton<ResourceLayout>(
                segments: <ButtonSegment<ResourceLayout>>[
                  ButtonSegment<ResourceLayout>(
                    value: ResourceLayout.list,
                    icon: const Icon(Icons.view_list_outlined, size: 16),
                    tooltip: t.tx('view_list'),
                  ),
                  ButtonSegment<ResourceLayout>(
                    value: ResourceLayout.grid,
                    icon: const Icon(Icons.grid_view_outlined, size: 16),
                    tooltip: t.tx('view_grid'),
                  ),
                ],
                selected: <ResourceLayout>{layout},
                showSelectedIcon: false,
                onSelectionChanged: (Set<ResourceLayout> value) =>
                    onLayoutChanged(value.first),
              ),
              const SizedBox(width: AppSpacing.sm),
              FilledButton.icon(
                onPressed: onAdd,
                icon: const Icon(Icons.add, size: 18),
                label: Text(
                  t.t(isLinks ? 'form_add_link' : 'form_add_folder'),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          // -- search + filters + selection actions ------------------------
          Row(
            children: <Widget>[
              Expanded(
                child: AppSearchField(
                  controller: searchController,
                  focusNode: searchFocusNode,
                  hint: t.t(
                    isLinks ? 'search_links_hint' : 'search_folders_hint',
                  ),
                  onChanged: onSearchChanged,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              AppCategoryDropdown(
                value: categoryFilter,
                items: filterEntries,
                width: 190,
                leadingIcon: Icons.filter_alt_outlined,
                labelBuilder: (String value) => switch (value) {
                  kAllCategories => t.t('all_categories'),
                  kUncategorized => t.t('uncategorized'),
                  _ => value,
                },
                onChanged: onCategoryFilterChanged,
              ),
              const SizedBox(width: AppSpacing.sm),
              ToolbarButton(
                icon: Icons.star,
                tooltip: t.t('favorites_only'),
                selected: favoritesOnly,
                onPressed: onToggleFavoritesOnly,
              ),
              const SizedBox(width: AppSpacing.xs),
              _Toolbar(
                t: t,
                hasSelection: _hasSelection,
                onOpen: _hasSelection ? onOpenSelected : null,
                onToggleFavorite:
                    _hasSelection ? onToggleFavoriteSelected : null,
                onCheckPaths: onCheckPaths,
                onEdit: _hasSelection ? onEditSelected : null,
                onDelete: _hasSelection ? onDeleteSelected : null,
                onImport: onImport,
                onExport: onExport,
              ),
              const SizedBox(width: AppSpacing.xs),
              PopupMenuButton<String>(
                tooltip: t.tx('more_actions'),
                icon: const Icon(Icons.more_vert, size: 18),
                padding: EdgeInsets.zero,
                splashRadius: 18,
                onSelected: (String value) {
                  if (value == 'sort_by_added') {
                    onSortByAdded();
                  }
                },
                itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
                  PopupMenuItem<String>(
                    value: 'sort_by_added',
                    child: Row(
                      children: <Widget>[
                        const Icon(Icons.sort, size: 16),
                        const SizedBox(width: AppSpacing.md),
                        Text(
                          t.tx('sort_by_added'),
                          style: const TextStyle(fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          // -- content ------------------------------------------------------
          Expanded(
            child: Stack(
              children: <Widget>[
                Positioned.fill(
                  child: layout == ResourceLayout.grid
                      ? ResourceGrid(
                          items: items,
                          mode: mode,
                          selectedId: selectedId,
                          onSelected: onSelected,
                          onPreview: onPreview,
                          actions: actions,
                          reorderEnabled: reorderEnabled,
                          onMoveItem: onMoveItem,
                          emptyState: emptyState,
                        )
                      : ResourceTable(
                          items: items,
                          mode: mode,
                          selectedId: selectedId,
                          onSelected: onSelected,
                          onPreview: onPreview,
                          actions: actions,
                          scrollController: scrollController,
                          reorderEnabled: reorderEnabled,
                          onMoveItem: onMoveItem,
                          emptyState: emptyState,
                        ),
                ),
                if (detailsPanel != null)
                  Positioned(
                    top: 0,
                    bottom: 0,
                    right: 0,
                    child: detailsPanel!,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Mirrors the four `summary_*` templates in `resource_hub.pyw:370-373`.
  static String _buildSummary(AppStrings t, ListSummary s) {
    if (s.hasCategory && s.hasQuery) {
      return t.t('summary_search_filtered', <Object?>[
        s.visible,
        s.total,
        s.category,
        s.query,
      ]);
    }
    if (s.hasCategory) {
      return t.t('summary_filtered', <Object?>[s.visible, s.total, s.category]);
    }
    if (s.hasQuery) {
      return t.t('summary_search', <Object?>[s.visible, s.total, s.query]);
    }
    return t.t('summary_all', <Object?>[s.visible, s.total]);
  }
}

class _Toolbar extends StatelessWidget {
  const _Toolbar({
    required this.t,
    required this.hasSelection,
    required this.onOpen,
    required this.onToggleFavorite,
    required this.onCheckPaths,
    required this.onEdit,
    required this.onDelete,
    required this.onImport,
    required this.onExport,
  });

  final AppStrings t;
  final bool hasSelection;
  final VoidCallback? onOpen;
  final VoidCallback? onToggleFavorite;
  final VoidCallback onCheckPaths;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;
  final VoidCallback onImport;
  final VoidCallback onExport;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors semantic = context.semantic;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        ToolbarButton(
          icon: Icons.open_in_new,
          tooltip: t.t('open'),
          onPressed: onOpen,
        ),
        ToolbarButton(
          icon: Icons.star_border,
          tooltip: t.t('favorite'),
          onPressed: onToggleFavorite,
        ),
        ToolbarButton(
          icon: Icons.health_and_safety_outlined,
          tooltip: t.t('check_paths'),
          onPressed: onCheckPaths,
        ),
        ToolbarButton(
          icon: Icons.file_download_outlined,
          tooltip: t.t('export'),
          onPressed: onExport,
        ),
        ToolbarButton(
          icon: Icons.file_upload_outlined,
          tooltip: t.t('import'),
          onPressed: onImport,
        ),
        ToolbarButton(
          icon: Icons.edit_outlined,
          tooltip: t.t('edit'),
          onPressed: onEdit,
        ),
        ToolbarButton(
          icon: Icons.delete_outline,
          tooltip: t.t('delete'),
          tone: hasSelection ? semantic.danger : null,
          onPressed: onDelete,
        ),
      ],
    );
  }
}
