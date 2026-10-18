import 'package:flutter/material.dart';

import '../../data/backend_models.dart';
import '../../l10n/app_strings_ext.dart';
import '../../l10n/strings_scope.dart';
import '../../widgets/app_button.dart';
import '../../design/app_tokens.dart';

/// Phase 22: review list for AI category suggestions.
///
/// Nothing is written here: the dialog returns the selected suggestions and the
/// home page applies them through the normal `resources.update` path after the
/// user confirms.
class AiSuggestionsDialog extends StatefulWidget {
  const AiSuggestionsDialog({
    super.key,
    required this.suggestions,
    required this.model,
  });

  final List<AiSuggestion> suggestions;
  final String model;

  @override
  State<AiSuggestionsDialog> createState() => _AiSuggestionsDialogState();
}

class _AiSuggestionsDialogState extends State<AiSuggestionsDialog> {
  late final Set<String> _selected;

  @override
  void initState() {
    super.initState();
    _selected = widget.suggestions.map((AiSuggestion s) => s.id).toSet();
  }

  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    final List<AiSuggestion> links = widget.suggestions
        .where((AiSuggestion s) => s.mode.isLinks)
        .toList(growable: false);
    final List<AiSuggestion> folders = widget.suggestions
        .where((AiSuggestion s) => !s.mode.isLinks)
        .toList(growable: false);

    return Dialog(
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560, maxHeight: 680),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.xxl,
                AppSpacing.xl,
                AppSpacing.md,
                AppSpacing.md,
              ),
              child: Row(
                children: <Widget>[
                  Icon(Icons.auto_awesome, size: 20, color: scheme.primary),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      t.tx('ai_suggest_title'),
                      style: text.titleLarge,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    splashRadius: 18,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: scheme.outlineVariant),
            Flexible(
              child: ListView(
                padding: const EdgeInsets.all(AppSpacing.xxl),
                children: <Widget>[
                  Text(
                    t.tx('ai_suggest_hint'),
                    style: text.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  if (links.isNotEmpty) ...<Widget>[
                    _GroupLabel(label: t.tx('ai_group_links')),
                    for (final AiSuggestion suggestion in links)
                      _SuggestionTile(
                        suggestion: suggestion,
                        selected: _selected.contains(suggestion.id),
                        onChanged: (bool value) => setState(() {
                          if (value) {
                            _selected.add(suggestion.id);
                          } else {
                            _selected.remove(suggestion.id);
                          }
                        }),
                      ),
                  ],
                  if (folders.isNotEmpty) ...<Widget>[
                    _GroupLabel(label: t.tx('ai_group_folders')),
                    for (final AiSuggestion suggestion in folders)
                      _SuggestionTile(
                        suggestion: suggestion,
                        selected: _selected.contains(suggestion.id),
                        onChanged: (bool value) => setState(() {
                          if (value) {
                            _selected.add(suggestion.id);
                          } else {
                            _selected.remove(suggestion.id);
                          }
                        }),
                      ),
                  ],
                ],
              ),
            ),
            Divider(height: 1, color: scheme.outlineVariant),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.xxl,
                AppSpacing.sm,
                AppSpacing.xxl,
                AppSpacing.md,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: <Widget>[
                  Text(
                    widget.model,
                    style: text.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const Spacer(),
                  AppButton(
                    label: t.tx('settings_cancel'),
                    variant: AppButtonVariant.ghost,
                    compact: true,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  AppButton(
                    key: const ValueKey<String>('ai-apply-button'),
                    label: t.tx('ai_suggest_apply', <Object?>[_selected.length]),
                    compact: true,
                    onPressed: _selected.isEmpty
                        ? null
                        : () => Navigator.of(context).pop(
                              widget.suggestions
                                  .where((AiSuggestion s) =>
                                      _selected.contains(s.id))
                                  .toList(growable: false),
                            ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GroupLabel extends StatelessWidget {
  const _GroupLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm, bottom: AppSpacing.xs),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: scheme.onSurfaceVariant,
            ),
      ),
    );
  }
}

class _SuggestionTile extends StatelessWidget {
  const _SuggestionTile({
    required this.suggestion,
    required this.selected,
    required this.onChanged,
  });

  final AiSuggestion suggestion;
  final bool selected;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    return CheckboxListTile(
      value: selected,
      onChanged: (bool? value) => onChanged(value ?? false),
      dense: true,
      contentPadding: EdgeInsets.zero,
      controlAffinity: ListTileControlAffinity.leading,
      title: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              suggestion.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: text.bodyMedium,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Icon(Icons.arrow_forward, size: 14, color: scheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.xs),
          Text(
            suggestion.suggestedCategory,
            style: text.bodyMedium?.copyWith(
              color: scheme.primary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
      subtitle: suggestion.reason.isEmpty
          ? null
          : Text(
              suggestion.reason,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: text.bodySmall?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            ),
    );
  }
}
