/// Domain models mirroring the legacy JSON contract.
///
/// Field names and sentinels are taken from `resource_hub.pyw` (`_normalize_site`
/// / `_normalize_folder`) so the Flutter layer can be pointed at the existing
/// `sites.json` / `folders.json` without a conversion step.
library;

/// Sentinel stored in `category` when the user did not pick one.
/// Matches `resource_hub.pyw:1915`.
const String kUncategorized = '__uncategorized__';

/// In-memory filter sentinel for "all categories". Never persisted.
/// Matches `resource_hub.pyw:955`.
const String kAllCategories = '__all__';

/// Which dataset the window is showing. Legacy `self.mode` (`links` / `folders`).
enum ViewMode {
  links,
  folders;

  bool get isLinks => this == ViewMode.links;
}

/// What a resource entry points at.
enum ResourceKind {
  link,
  folder,
  file;

  static ResourceKind fromJson(String? raw, {required bool isDirectory}) {
    switch (raw) {
      case 'link':
        return ResourceKind.link;
      case 'folder':
        return ResourceKind.folder;
      case 'file':
        return ResourceKind.file;
      default:
        return isDirectory ? ResourceKind.folder : ResourceKind.file;
    }
  }

  String get jsonValue => name;
}

/// Health of the underlying path, used for the red row tint.
enum PathState {
  unknown,
  ok,
  missing;

  bool get isMissing => this == PathState.missing;
}

/// One entry in `sites.json` or `folders.json`.
class ResourceItem {
  const ResourceItem({
    required this.id,
    required this.name,
    required this.path,
    required this.kind,
    this.category = kUncategorized,
    this.note = '',
    this.favorite = false,
    this.createdAt,
    this.pathState = PathState.unknown,
  });

  final String id;
  final String name;

  /// URL for [ResourceKind.link], filesystem path otherwise.
  final String path;

  final ResourceKind kind;
  final String category;
  final String note;
  final bool favorite;

  /// Local-time ISO8601 with offset, e.g. `2026-04-22T13:53:49.313959+08:00`.
  final DateTime? createdAt;

  final PathState pathState;

  bool get isUncategorized => category == kUncategorized;

  /// Stable key used for de-duplication. Links compare case-insensitively with
  /// trailing slashes stripped; paths compare case-insensitively on Windows.
  /// Mirrors `_comparable_value` (`resource_hub.pyw:1906`).
  String get dedupeKey {
    if (kind == ResourceKind.link) {
      return path.toLowerCase().replaceAll(RegExp(r'/+$'), '');
    }
    return path.replaceAll('/', r'\').toLowerCase();
  }

  ResourceItem copyWith({
    String? id,
    String? name,
    String? path,
    ResourceKind? kind,
    String? category,
    String? note,
    bool? favorite,
    DateTime? createdAt,
    PathState? pathState,
  }) {
    return ResourceItem(
      id: id ?? this.id,
      name: name ?? this.name,
      path: path ?? this.path,
      kind: kind ?? this.kind,
      category: category ?? this.category,
      note: note ?? this.note,
      favorite: favorite ?? this.favorite,
      createdAt: createdAt ?? this.createdAt,
      pathState: pathState ?? this.pathState,
    );
  }

  /// Strict conversion of a backend payload (`resources.list` item).
  ///
  /// The backend always returns complete entries, so missing fields indicate a
  /// protocol bug; they fall back to safe defaults instead of throwing.
  static ResourceItem fromJson(Map<String, dynamic> json) {
    final bool isLink = json.containsKey('url');
    final String category = (json['category'] as String?) ?? kUncategorized;
    return ResourceItem(
      id: (json['id'] as String?) ?? '',
      name: (json['name'] as String?) ?? '',
      path: (json['url'] ?? json['path'] ?? '') as String,
      kind: isLink
          ? ResourceKind.link
          : ResourceKind.fromJson(
              json['kind'] as String?,
              isDirectory: json['kind'] == null,
            ),
      category: category.isEmpty ? kUncategorized : category,
      note: (json['note'] as String?) ?? '',
      favorite: json['favorite'] == true,
      createdAt: DateTime.tryParse((json['createdAt'] as String?) ?? ''),
    );
  }

  /// Lenient parse: entries missing `name` or `path`/`url` are rejected, exactly
  /// like `_normalize_site` / `_normalize_folder` do on load.
  static ResourceItem? tryFromJson(
    Map<String, dynamic> json, {
    required ViewMode mode,
  }) {
    final String? name = (json['name'] as String?)?.trim();
    final String? rawPath =
        (json['path'] as String?)?.trim() ?? (json['url'] as String?)?.trim();
    if (name == null || name.isEmpty || rawPath == null || rawPath.isEmpty) {
      return null;
    }
    final String rawCategory = (json['category'] as String?)?.trim() ?? '';
    final String category = rawCategory.isEmpty ||
            rawCategory == '未分类' ||
            rawCategory == 'Uncategorized'
        ? kUncategorized
        : rawCategory;
    return ResourceItem(
      id: (json['id'] as String?) ?? name,
      name: name,
      path: rawPath,
      kind: mode == ViewMode.links
          ? ResourceKind.link
          : ResourceKind.fromJson(
              json['kind'] as String?,
              isDirectory: (json['kind'] as String?) == null,
            ),
      category: category,
      note: (json['note'] as String?) ?? '',
      favorite: json['favorite'] == true,
      createdAt: DateTime.tryParse((json['createdAt'] as String?) ?? ''),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'id': id,
      'name': name,
      if (kind == ResourceKind.link) 'url': path else 'path': path,
      if (kind != ResourceKind.link) 'kind': kind.jsonValue,
      'category': category,
      'note': note,
      'favorite': favorite,
      'createdAt': createdAt?.toIso8601String(),
    };
  }
}

/// Snapshot of the list state after search + category filter.
class ListSummary {
  const ListSummary({
    required this.visible,
    required this.total,
    this.category = kAllCategories,
    this.query = '',
  });

  final int visible;
  final int total;
  final String category;
  final String query;

  bool get hasCategory => category != kAllCategories;
  bool get hasQuery => query.trim().isNotEmpty;
}
