/// The left-hand editor form.
///
/// Legacy equivalent: `left_panel` (`resource_hub.pyw:2029-2114`) with
/// `name_entry`, `path_entry` + browse buttons, `category_entry`, `notes_text`,
/// `added_value`, `data_note`, save / clear buttons.
library;

import 'package:flutter/material.dart';

import '../../design/app_tokens.dart';
import '../../l10n/strings_scope.dart';
import '../../models/resource_item.dart';
import '../../util/formatters.dart';
import '../../widgets/app_button.dart';
import '../../widgets/app_card.dart';
import '../../widgets/app_fields.dart';

class ResourceForm extends StatefulWidget {
  const ResourceForm({
    super.key,
    required this.mode,
    required this.categories,
    required this.editing,
    required this.onSubmit,
    required this.onClear,
    this.onBrowseFolder,
    this.onBrowseFile,
    this.onClose,
  });

  final ViewMode mode;
  final List<String> categories;

  /// Non-null puts the form into edit mode and pre-fills the fields.
  final ResourceItem? editing;

  final ValueChanged<ResourceItem> onSubmit;
  final VoidCallback onClear;
  final VoidCallback? onBrowseFolder;
  final VoidCallback? onBrowseFile;

  /// When shown in a dialog, renders a close affordance in the header.
  final VoidCallback? onClose;

  @override
  State<ResourceForm> createState() => ResourceFormState();
}

class ResourceFormState extends State<ResourceForm> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _path = TextEditingController();
  final TextEditingController _note = TextEditingController();
  final ScrollController _scroll = ScrollController();
  String _category = kUncategorized;
  String? _nameError;
  String? _pathError;

  @override
  void initState() {
    super.initState();
    _syncFromEditing();
  }

  @override
  void didUpdateWidget(ResourceForm oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.editing?.id != widget.editing?.id ||
        oldWidget.mode != widget.mode) {
      _syncFromEditing();
    }
  }

  void _syncFromEditing() {
    final ResourceItem? item = widget.editing;
    _name.text = item?.name ?? '';
    _path.text = item?.path ?? '';
    _note.text = item?.note ?? '';
    _category = item?.category ?? kUncategorized;
    _nameError = null;
    _pathError = null;
  }

  @override
  void dispose() {
    _name.dispose();
    _path.dispose();
    _note.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _handleSubmit() {
    final AppStrings t = context.l10n;
    final bool isLinks = widget.mode.isLinks;
    final String name = _name.text.trim();
    final String path = _path.text.trim();

    setState(() {
      _nameError = name.isEmpty
          ? t.t(isLinks ? 'enter_link_name' : 'enter_folder_name')
          : null;
      _pathError = path.isEmpty
          ? t.t(isLinks ? 'enter_link_path' : 'enter_folder_path')
          : null;
    });
    if (_nameError != null || _pathError != null) {
      return;
    }

    widget.onSubmit(
      ResourceItem(
        id: widget.editing?.id ?? 'draft',
        name: name,
        path: path,
        kind: isLinks
            ? ResourceKind.link
            : (widget.editing?.kind ?? ResourceKind.folder),
        category: _category,
        note: _note.text.trim(),
        favorite: widget.editing?.favorite ?? false,
        createdAt: widget.editing?.createdAt,
      ),
    );
  }

  void _handleClear() {
    clearForm();
    widget.onClear();
  }

  /// Resets every field. Called by the shell after a successful save, which is
  /// what the legacy `clear_form()` did (``resource_hub.pyw:2818``).
  void clearForm() {
    if (!mounted) {
      return;
    }
    setState(() {
      _name.clear();
      _path.clear();
      _note.clear();
      _category = kUncategorized;
      _nameError = null;
      _pathError = null;
    });
  }

  /// Pre-fills the path field — used once the file picker is wired in.
  void setPath(String path) {
    if (!mounted) {
      return;
    }
    setState(() {
      _path.text = path;
      _pathError = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final bool isLinks = widget.mode.isLinks;
    final bool editing = widget.editing != null;
    final List<String> categories = <String>[
      kUncategorized,
      ...widget.categories.where((String c) => c != kUncategorized),
    ];

    final String titleKey = editing
        ? (isLinks ? 'form_edit_link' : 'form_edit_folder')
        : (isLinks ? 'form_add_link' : 'form_add_folder');
    final String saveKey = editing
        ? 'save_changes'
        : (isLinks ? 'save_link' : 'save_folder');

    // The form scrolls on short windows; an always-visible bar makes that
    // discoverable (the theme sets `thumbVisibility`).
    return Scrollbar(
      controller: _scroll,
      child: SingleChildScrollView(
        controller: _scroll,
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
          SectionHeader(
            title: t.t(titleKey),
            subtitle: t.t(isLinks ? 'form_tip_links' : 'form_tip_folders'),
            dense: true,
            trailing: widget.onClose == null
                ? null
                : IconButton(
                    tooltip: t.t('settings_cancel'),
                    visualDensity: VisualDensity.compact,
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: widget.onClose,
                  ),
          ),
          const SizedBox(height: AppSpacing.lg),
          AppTextField(
            controller: _name,
            label: t.t(isLinks ? 'name_link' : 'name_folder'),
            hint: isLinks ? 'OpenAI' : t.t('name_folder'),
            prefixIcon: Icons.label_outline,
            errorText: _nameError,
            onChanged: (_) {
              if (_nameError != null) {
                setState(() => _nameError = null);
              }
            },
          ),
          const SizedBox(height: AppSpacing.md),
          AppTextField(
            controller: _path,
            label: t.t(isLinks ? 'path_link' : 'path_folder'),
            hint: isLinks ? 'https://example.com' : r'D:\Workspace\项目',
            prefixIcon: isLinks ? Icons.link : Icons.folder_outlined,
            errorText: _pathError,
            trailing: isLinks
                ? null
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      ToolbarButton(
                        icon: Icons.folder_open_outlined,
                        tooltip: t.t('browse_folder'),
                        onPressed: widget.onBrowseFolder,
                      ),
                      ToolbarButton(
                        icon: Icons.description_outlined,
                        tooltip: t.t('browse_file'),
                        onPressed: widget.onBrowseFile,
                      ),
                    ],
                  ),
            onChanged: (_) {
              if (_pathError != null) {
                setState(() => _pathError = null);
              }
            },
          ),
          const SizedBox(height: AppSpacing.md),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                t.t('category'),
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
              const SizedBox(height: AppSpacing.xs),
              AppCategoryDropdown(
                value: _category,
                items: categories,
                labelBuilder: (String value) =>
                    value == kUncategorized ? t.t('uncategorized') : value,
                onChanged: (String value) =>
                    setState(() => _category = value),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          AppTextField(
            controller: _note,
            label: t.t('notes'),
            hint: t.t('no_notes'),
            maxLines: 3,
          ),
          const SizedBox(height: AppSpacing.md),
          AppReadonlyValue(
            label: t.t('added_at'),
            value: widget.editing?.createdAt == null
                ? t.t('added_auto')
                : formatAddedAt(widget.editing!.createdAt),
          ),
          const SizedBox(height: AppSpacing.lg),
          AppButton(
            label: t.t(saveKey),
            icon: editing ? Icons.save_outlined : Icons.add,
            expand: true,
            onPressed: _handleSubmit,
          ),
          const SizedBox(height: AppSpacing.sm),
          AppButton(
            label: t.t('clear_form'),
            icon: Icons.backspace_outlined,
            variant: AppButtonVariant.secondary,
            expand: true,
            onPressed: _handleClear,
          ),
          const SizedBox(height: AppSpacing.lg),
          AppNoteBanner(
            text: t.t(isLinks ? 'data_note_links' : 'data_note_folders'),
          ),
          ],
        ),
      ),
    );
  }
}
