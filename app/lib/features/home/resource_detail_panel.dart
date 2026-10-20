/// Right-hand details panel opened by clicking a resource row (Phase 9).
///
/// Non-modal by design: it floats over the right part of the workspace, the
/// toolbar and drag handles stay usable, and selecting another row switches the
/// content. Folder resources render the [MindMap]; links and single files get a
/// compact info panel (no map) with the same header actions.
///
/// The panel owns only presentation state (selected map node, entrance slide);
/// data loading and mutations are callbacks provided by the shell.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../data/backend_models.dart';
import '../../design/app_theme.dart';
import '../../design/app_tokens.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../models/resource_item.dart';
import '../../util/formatters.dart';
import '../../widgets/mind_map.dart';
import '../../widgets/site_icon.dart';

class ResourceDetailPanel extends StatefulWidget {
  const ResourceDetailPanel({
    super.key,
    required this.item,
    this.browsers = const <BrowserInfo>[],
    this.onChangeBrowser,
    required this.loadChildren,
    required this.onClose,
    required this.onResize,
    required this.onOpenItem,
    required this.onRevealItem,
    required this.onEditItem,
    required this.onToggleFavoriteItem,
    required this.onOpenPath,
    required this.onRevealPath,
    required this.onAddResource,
    required this.onCopyText,
  });

  final ResourceItem item;
  final List<BrowserInfo> browsers;

  /// Persists the per-link "open with" browser; ``null`` hides the dropdown.
  final ValueChanged<String>? onChangeBrowser;
  final Future<FsListing> Function(String path) loadChildren;
  final VoidCallback onClose;

  /// Horizontal delta of the left-edge drag handle; the shell clamps the width.
  final ValueChanged<double> onResize;
  final ValueChanged<ResourceItem> onOpenItem;
  final ValueChanged<ResourceItem> onRevealItem;
  final ValueChanged<ResourceItem> onEditItem;
  final ValueChanged<ResourceItem> onToggleFavoriteItem;
  final ValueChanged<String> onOpenPath;
  final ValueChanged<String> onRevealPath;
  final ValueChanged<FsEntry> onAddResource;
  final ValueChanged<String> onCopyText;

  @override
  State<ResourceDetailPanel> createState() => _ResourceDetailPanelState();
}

class _ResourceDetailPanelState extends State<ResourceDetailPanel> {
  final MindMapController _map = MindMapController();
  final FocusNode _panelFocus = FocusNode(debugLabel: 'resource-detail-panel');
  Offset _slide = const Offset(1, 0);
  String? _selectedNodePath;

  bool get _isFolder => widget.item.kind == ResourceKind.folder;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      setState(() => _slide = Offset.zero);
      // Own the keyboard focus while the panel is open: Esc closes it, and the
      // mind map gets arrow-key navigation once it is focused.
      _panelFocus.requestFocus();
    });
  }

  @override
  void didUpdateWidget(covariant ResourceDetailPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.item.id != widget.item.id) {
      _selectedNodePath = null;
    }
  }

  @override
  void dispose() {
    _map.zoom.dispose();
    _panelFocus.dispose();
    super.dispose();
  }

  Future<FsListing> _loadChildren(String path) => widget.loadChildren(path);

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.escape): widget.onClose,
      },
      child: Focus(
        focusNode: _panelFocus,
        child: TapRegion(
          // Clicking anywhere outside the panel (blank table area, another row,
          // toolbar, status bar…) dismisses it; a row click both closes and
          // immediately re-opens for the new selection, so switching is seamless.
          onTapOutside: (_) => widget.onClose(),
          child: AnimatedSlide(
            offset: _slide,
            duration: AppDurations.normal,
            curve: Curves.easeOutCubic,
            child: Stack(
            children: <Widget>[
              Container(
                decoration: BoxDecoration(
                  color: scheme.surfaceContainerLow,
                  borderRadius: const BorderRadius.horizontal(
                    left: Radius.circular(AppRadius.lg),
                  ),
                  border: Border(
                    left: BorderSide(color: scheme.outlineVariant),
                  ),
                  boxShadow: <BoxShadow>[
                    BoxShadow(
                      color: scheme.shadow.withValues(alpha: 0.10),
                      blurRadius: 24,
                      offset: const Offset(-4, 0),
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: const BorderRadius.horizontal(
                    left: Radius.circular(AppRadius.lg),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      _buildHeader(context),
                      _buildPathRow(context),
                      _buildActionsRow(context),
                      if (!_isFolder) _buildBrowserRow(context),
                      if (_isFolder) _buildZoomBar(context),
                      const Divider(height: 1),
                      Expanded(
                        child: _isFolder
                            ? _buildFolderBody(context)
                            : _buildInfoBody(context),
                      ),
                      if (_isFolder && _selectedNodePath != null)
                        _buildSelectedFooter(context),
                    ],
                  ),
                ),
              ),
              Positioned(
                left: 0,
                top: 0,
                bottom: 0,
                child: MouseRegion(
                  cursor: SystemMouseCursors.resizeLeftRight,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onHorizontalDragUpdate: (DragUpdateDetails details) =>
                        widget.onResize(details.delta.dx),
                    child: const SizedBox(width: 8),
                  ),
                ),
              ),
            ],
          ),
        ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final ResourceItem item = widget.item;
    final (IconData icon, String kindLabel) = switch (item.kind) {
      ResourceKind.link => (Icons.link, t.t('col_url')),
      ResourceKind.folder => (Icons.folder_outlined, t.t('kind_folder')),
      ResourceKind.file => (Icons.description_outlined, t.t('kind_file')),
    };
    final String category =
        item.isUncategorized ? t.t('uncategorized') : item.category;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.xs,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHigh,
              borderRadius: BorderRadius.circular(AppRadius.sm),
            ),
            child: SiteIcon(
              item: item,
              fallback: icon,
              size: 22,
              color: scheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(width: AppSpacing.sm + 2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  item.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: text.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  '$kindLabel · $category',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: text.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: t.tx('close'),
            icon: const Icon(Icons.close, size: 18),
            onPressed: widget.onClose,
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }

  Widget _buildPathRow(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        0,
        AppSpacing.sm,
        AppSpacing.xs,
      ),
      child: Row(
        children: <Widget>[
          Icon(Icons.link, size: 13, color: scheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Tooltip(
              message: widget.item.path,
              waitDuration: const Duration(milliseconds: 600),
              child: Text(
                widget.item.path,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11.5,
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: t.t('copy_path'),
            icon: const Icon(Icons.copy_outlined, size: 15),
            onPressed: () => widget.onCopyText(widget.item.path),
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints.tightFor(width: 28, height: 28),
          ),
        ],
      ),
    );
  }

  /// Per-link "open with" choice: empty means the system default browser.
  Widget _buildBrowserRow(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final String value = widget.item.browser;
    final bool known = value.isEmpty ||
        widget.browsers.any((BrowserInfo browser) => browser.id == value);
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        0,
        AppSpacing.sm,
        AppSpacing.xs,
      ),
      child: Row(
        children: <Widget>[
          Icon(Icons.public, size: 13, color: scheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.xs),
          Text(
            '${t.tx('open_with')} ',
            style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          Expanded(
            child: DropdownButton<String>(
              key: const ValueKey<String>('link-browser-dropdown'),
              value: value,
              isDense: true,
              isExpanded: true,
              underline: const SizedBox.shrink(),
              style: text.bodySmall,
              items: <DropdownMenuItem<String>>[
                DropdownMenuItem<String>(
                  value: '',
                  child: Text(
                    t.tx('open_with_default'),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                for (final BrowserInfo browser in widget.browsers)
                  DropdownMenuItem<String>(
                    value: browser.id,
                    child: Text(
                      browser.name,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                if (!known)
                  DropdownMenuItem<String>(
                    value: value,
                    child: Text(value, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: widget.onChangeBrowser == null
                  ? null
                  : (String? next) {
                      if (next != null) {
                        widget.onChangeBrowser!(next);
                      }
                    },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionsRow(BuildContext context) {
    final AppStrings t = context.l10n;
    final ResourceItem item = widget.item;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        0,
        AppSpacing.md,
        AppSpacing.sm,
      ),
      child: Row(
        children: <Widget>[
          _ActionButton(
            icon: Icons.open_in_new,
            tooltip: t.t('open'),
            onPressed: () => widget.onOpenItem(item),
          ),
          if (item.kind != ResourceKind.link)
            _ActionButton(
              icon: Icons.folder_open_outlined,
              tooltip: t.t('open_location'),
              onPressed: () => widget.onRevealItem(item),
            ),
          _ActionButton(
            icon: Icons.edit_outlined,
            tooltip: t.t('edit'),
            onPressed: () => widget.onEditItem(item),
          ),
          _ActionButton(
            icon: item.favorite ? Icons.star : Icons.star_border,
            tooltip: item.favorite ? t.t('unfavorite') : t.t('favorite'),
            onPressed: () => widget.onToggleFavoriteItem(item),
            highlighted: item.favorite,
          ),
        ],
      ),
    );
  }

  Widget _buildZoomBar(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        0,
        AppSpacing.md,
        AppSpacing.xs,
      ),
      child: Row(
        children: <Widget>[
          _ActionButton(
            icon: Icons.remove,
            tooltip: t.tx('zoom_out'),
            onPressed: _map.zoomOut,
            dense: true,
          ),
          ValueListenableBuilder<double>(
            valueListenable: _map.zoom,
            builder: (BuildContext context, double value, Widget? _) {
              return SizedBox(
                width: 44,
                child: Text(
                  '${(value * 100).round()}%',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 11.5,
                    color: scheme.onSurfaceVariant,
                    fontFeatures: const <FontFeature>[
                      FontFeature.tabularFigures(),
                    ],
                  ),
                ),
              );
            },
          ),
          _ActionButton(
            icon: Icons.add,
            tooltip: t.tx('zoom_in'),
            onPressed: _map.zoomIn,
            dense: true,
          ),
          _ActionButton(
            icon: Icons.fit_screen_outlined,
            tooltip: t.tx('fit_view'),
            onPressed: _map.fit,
            dense: true,
          ),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              t.tx('zoom_hint'),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
              style: TextStyle(
                fontSize: 11,
                color: scheme.onSurfaceVariant.withValues(alpha: 0.8),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFolderBody(BuildContext context) {
    final ResourceItem item = widget.item;
    return MindMap(
      key: ValueKey<String>('mind-map-${item.id}'),
      rootName: item.name,
      rootPath: item.path,
      loadChildren: _loadChildren,
      controller: _map,
      actions: MindMapActions(
        onOpenEntry: (FsEntry entry) => widget.onOpenPath(entry.path),
        onRevealEntry: (FsEntry entry) => widget.onRevealPath(entry.path),
        onCopyPath: widget.onCopyText,
        onAddResource: widget.onAddResource,
        onSelectionChanged: (FsEntry? entry) {
          setState(() => _selectedNodePath = entry?.path);
        },
      ),
    );
  }

  Widget _buildInfoBody(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final ResourceItem item = widget.item;
    final List<Widget> rows = <Widget>[
      _InfoRow(
        label: t.t('col_category'),
        value: item.isUncategorized ? t.t('uncategorized') : item.category,
      ),
      _InfoRow(
        label: t.t('col_added_at'),
        value: formatAddedAt(item.createdAt),
      ),
      if (item.note.trim().isNotEmpty)
        _InfoRow(label: t.t('col_notes'), value: item.note),
      _InfoRow(
        label: t.t(item.kind == ResourceKind.link ? 'col_url' : 'col_path'),
        value: item.path,
        onCopy: () => widget.onCopyText(item.path),
      ),
    ];
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: <Widget>[
        for (final Widget row in rows) ...<Widget>[
          row,
          const SizedBox(height: AppSpacing.md),
        ],
        if (item.kind == ResourceKind.file)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => widget.onRevealItem(item),
              icon: const Icon(Icons.folder_open_outlined, size: 16),
              label: Text(t.t('open_location')),
            ),
          ),
        if (item.kind == ResourceKind.link)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => widget.onCopyText(item.path),
              icon: const Icon(Icons.copy_outlined, size: 16),
              label: Text(t.t('copy_url')),
            ),
          ),
        Padding(
          padding: const EdgeInsets.only(top: AppSpacing.sm),
          child: Text(
            t.tx('detail_collection_hint'),
            style: TextStyle(
              fontSize: 11,
              color: scheme.onSurfaceVariant.withValues(alpha: 0.8),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSelectedFooter(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final String path = _selectedNodePath!;
    return Container(
      height: 30,
      padding: const EdgeInsets.only(left: AppSpacing.md, right: AppSpacing.xs),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: <Widget>[
          Text(
            '${t.tx('selected_path')}: ',
            style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
          ),
          Expanded(
            child: Tooltip(
              message: path,
              waitDuration: const Duration(milliseconds: 600),
              child: Text(
                path,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11,
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: t.t('copy_path'),
            icon: const Icon(Icons.copy_outlined, size: 14),
            onPressed: () => widget.onCopyText(path),
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints.tightFor(width: 26, height: 26),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
    this.highlighted = false,
    this.dense = false,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;
  final bool highlighted;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors semantic = context.semantic;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return IconButton(
      tooltip: tooltip,
      icon: Icon(
        icon,
        size: dense ? 16 : 18,
        color: highlighted ? semantic.favorite : scheme.onSurfaceVariant,
      ),
      onPressed: onPressed,
      visualDensity: VisualDensity.compact,
      padding: EdgeInsets.zero,
      constraints: BoxConstraints.tightFor(
        width: dense ? 28 : 34,
        height: dense ? 28 : 34,
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value, this.onCopy});

  final String label;
  final String value;
  final VoidCallback? onCopy;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          label,
          style: TextStyle(
            fontSize: 11,
            color: scheme.onSurfaceVariant,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.2,
          ),
        ),
        const SizedBox(height: 3),
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                value,
                style: TextStyle(fontSize: 12.5, color: scheme.onSurface),
              ),
            ),
            if (onCopy != null)
              IconButton(
                tooltip: context.l10n.t('copy_path'),
                icon: const Icon(Icons.copy_outlined, size: 14),
                onPressed: onCopy,
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints:
                    const BoxConstraints.tightFor(width: 26, height: 26),
              ),
          ],
        ),
      ],
    );
  }
}
