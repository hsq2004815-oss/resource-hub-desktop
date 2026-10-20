/// Per-site favicon rendering for link resources.
///
/// The backend caches one icon per host under `data/favicons`; [FaviconIndex]
/// holds the host → file map in memory and refreshes whenever the backend sends
/// a `favicons` event. Until an icon exists (or when a site has none) the widget
/// falls back to the generic per-kind glyph.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/resource_item.dart';

class FaviconIndex {
  FaviconIndex._();

  /// Host → absolute icon path. Shared by every card, list row and panel.
  static final ValueNotifier<Map<String, String>> icons =
      ValueNotifier<Map<String, String>>(const <String, String>{});

  static void update(Map<String, String> value) {
    if (mapEquals(icons.value, value)) {
      return;
    }
    icons.value = Map<String, String>.unmodifiable(value);
  }

  static String? pathFor(ResourceItem item, Map<String, String> value) {
    if (item.kind != ResourceKind.link) {
      return null;
    }
    final String host = Uri.tryParse(item.path)?.host.toLowerCase() ?? '';
    if (host.isEmpty) {
      return null;
    }
    return value[host];
  }
}

/// The site icon for [item], or [fallback] when no cached image exists.
class SiteIcon extends StatelessWidget {
  const SiteIcon({
    super.key,
    required this.item,
    required this.fallback,
    required this.size,
    this.color,
    this.borderRadius,
  });

  final ResourceItem item;
  final IconData fallback;
  final double size;
  final Color? color;
  final BorderRadius? borderRadius;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Map<String, String>>(
      valueListenable: FaviconIndex.icons,
      builder: (BuildContext context, Map<String, String> icons, Widget? _) {
        final String? path = FaviconIndex.pathFor(item, icons);
        if (path == null) {
          return Icon(fallback, size: size, color: color);
        }
        return ClipRRect(
          borderRadius: borderRadius ?? BorderRadius.circular(3),
          child: Image.file(
            File(path),
            width: size,
            height: size,
            fit: BoxFit.contain,
            filterQuality: FilterQuality.medium,
            errorBuilder: (BuildContext context, Object error, StackTrace? _) =>
                Icon(fallback, size: size, color: color),
          ),
        );
      },
    );
  }
}
