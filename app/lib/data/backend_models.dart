/// Data-transfer objects shared by the backend client, the repository and the UI.
///
/// Kept separate from [BackendRepository] so tests can build fake results without
/// pulling in the process/transport layer.
library;

import '../models/resource_item.dart';

/// Result of `app.hello`.
class BackendHello {
  const BackendHello({
    required this.protocolVersion,
    required this.dataStatus,
    required this.loadError,
    required this.baseDir,
    required this.methods,
  });

  final int protocolVersion;

  /// `"ok"` or `"corrupt"`. When corrupt, every resource call is refused.
  final String dataStatus;
  final String? loadError;
  final String baseDir;
  final List<String> methods;

  bool get isCorrupt => dataStatus == 'corrupt';

  factory BackendHello.fromJson(Map<String, dynamic> json) {
    return BackendHello(
      protocolVersion: json['protocolVersion'] as int? ?? 0,
      dataStatus: json['dataStatus'] as String? ?? 'ok',
      loadError: json['loadError'] as String?,
      baseDir: json['baseDir'] as String? ?? '',
      methods: (json['methods'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => e as String)
          .toList(),
    );
  }
}

/// One page of `resources.list`.
class ResourceListPage {
  const ResourceListPage({
    required this.items,
    required this.total,
    required this.visible,
    required this.categories,
  });

  final List<ResourceItem> items;
  final int total;
  final int visible;
  final List<String> categories;

  factory ResourceListPage.fromJson(Map<String, dynamic> json) {
    return ResourceListPage(
      items: (json['items'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => ResourceItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int? ?? 0,
      visible: json['visible'] as int? ?? 0,
      categories: (json['categories'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => e as String)
          .toList(),
    );
  }
}

/// Outcome of `resources.checkPaths`.
class PathCheckOutcome {
  const PathCheckOutcome({
    required this.supported,
    required this.total,
    required this.missingIds,
  });

  final bool supported;
  final int total;
  final List<String> missingIds;

  int get missingCount => missingIds.length;
}

/// Outcome of `resources.drop`.
class DropOutcome {
  const DropOutcome({
    required this.added,
    required this.skipped,
    required this.invalid,
  });

  final int added;
  final int skipped;
  final int invalid;
}

/// Outcome of `resources.import`.
class ImportOutcome {
  const ImportOutcome({required this.imported, required this.skipped});

  final int imported;
  final int skipped;
}

/// Defaults shared by the settings model and its tests. They mirror
/// `backend/resource_hub_core/settings.py`.
///
/// The quick-panel combinations include Shift on purpose: `Ctrl+Alt+L/F` are
/// claimed by other applications on the reference Windows machine, where the
/// backend reports them as taken.
const String kDefaultGlobalHotkey = 'Ctrl + Alt + Space';
const String kDefaultQuickLinksHotkey = 'Ctrl + Alt + Shift + L';
const String kDefaultQuickFoldersHotkey = 'Ctrl + Alt + Shift + F';

/// Settings as stored by the backend (`settings.json`).
class AppSettings {
  const AppSettings({
    this.language = 'zh',
    this.globalHotkeyEnabled = true,
    this.globalHotkeyId = kDefaultGlobalHotkey,
    this.quickLinksHotkeyId = kDefaultQuickLinksHotkey,
    this.quickFoldersHotkeyId = kDefaultQuickFoldersHotkey,
    this.launchAtStartup = false,
  });

  final String language;
  final bool globalHotkeyEnabled;
  final String globalHotkeyId;

  /// Phase 16: opens the compact web-links tree HUD without the main window.
  final String quickLinksHotkeyId;

  /// Phase 16: opens the compact folder tree HUD without the main window.
  final String quickFoldersHotkeyId;
  final bool launchAtStartup;

  AppSettings copyWith({
    String? language,
    bool? globalHotkeyEnabled,
    String? globalHotkeyId,
    String? quickLinksHotkeyId,
    String? quickFoldersHotkeyId,
    bool? launchAtStartup,
  }) {
    return AppSettings(
      language: language ?? this.language,
      globalHotkeyEnabled: globalHotkeyEnabled ?? this.globalHotkeyEnabled,
      globalHotkeyId: globalHotkeyId ?? this.globalHotkeyId,
      quickLinksHotkeyId: quickLinksHotkeyId ?? this.quickLinksHotkeyId,
      quickFoldersHotkeyId:
          quickFoldersHotkeyId ?? this.quickFoldersHotkeyId,
      launchAtStartup: launchAtStartup ?? this.launchAtStartup,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'language': language,
        'globalHotkeyEnabled': globalHotkeyEnabled,
        'globalHotkeyId': globalHotkeyId,
        'quickLinksHotkeyId': quickLinksHotkeyId,
        'quickFoldersHotkeyId': quickFoldersHotkeyId,
        'launchAtStartup': launchAtStartup,
      };

  factory AppSettings.fromJson(Map<String, dynamic> json) {
    return AppSettings(
      language: json['language'] as String? ?? 'zh',
      globalHotkeyEnabled: json['globalHotkeyEnabled'] as bool? ?? true,
      globalHotkeyId: json['globalHotkeyId'] as String? ?? kDefaultGlobalHotkey,
      quickLinksHotkeyId:
          json['quickLinksHotkeyId'] as String? ?? kDefaultQuickLinksHotkey,
      quickFoldersHotkeyId:
          json['quickFoldersHotkeyId'] as String? ?? kDefaultQuickFoldersHotkey,
      launchAtStartup: json['launchAtStartup'] as bool? ?? false,
    );
  }
}

/// One `hotkey.start` registration entry (Phase 16: one per action).
class HotkeyRegistration {
  const HotkeyRegistration({
    required this.action,
    required this.label,
    required this.registered,
    this.reason,
  });

  /// `"toggle"`, `"quickLinks"` or `"quickFolders"`.
  final String action;
  final String label;
  final bool registered;

  /// `"disabled"`, `"unavailable"`, or null when registered.
  final String? reason;

  bool get isUnavailable => !registered && reason == 'unavailable';

  factory HotkeyRegistration.fromJson(Map<String, dynamic> json) {
    return HotkeyRegistration(
      action: json['action'] as String? ?? '',
      label: json['label'] as String? ?? '',
      registered: json['registered'] as bool? ?? false,
      reason: json['reason'] as String?,
    );
  }
}

/// Result of `hotkey.start`.
class HotkeyStatus {
  const HotkeyStatus({
    required this.registered,
    required this.label,
    this.reason,
    this.registrations = const <HotkeyRegistration>[],
  });

  final bool registered;
  final String label;

  /// `"disabled"`, `"unavailable"`, or null when registered.
  final String? reason;

  /// Every action's registration state (toggle + the two quick-panel hotkeys).
  final List<HotkeyRegistration> registrations;

  /// Combinations taken by another app; surfaced in the status bar.
  List<HotkeyRegistration> get unavailable =>
      registrations.where((HotkeyRegistration entry) => entry.isUnavailable)
          .toList(growable: false);
}

/// What a `fs.children` entry is.
enum FsEntryKind { folder, file }

/// One child returned by `fs.children` (folder preview panel).
class FsEntry {
  const FsEntry({
    required this.name,
    required this.path,
    required this.kind,
    this.isLink = false,
  });

  final String name;
  final String path;
  final FsEntryKind kind;

  /// Symlink / Windows reparse point (junction); shown with a small badge.
  final bool isLink;

  bool get isFolder => kind == FsEntryKind.folder;

  factory FsEntry.fromJson(Map<String, dynamic> json) {
    return FsEntry(
      name: json['name'] as String? ?? '',
      path: json['path'] as String? ?? '',
      kind: json['kind'] == 'folder' ? FsEntryKind.folder : FsEntryKind.file,
      isLink: json['isLink'] == true,
    );
  }
}

/// One directory level returned by `fs.children`.
class FsListing {
  const FsListing({
    required this.path,
    required this.entries,
    required this.total,
    required this.truncated,
  });

  final String path;
  final List<FsEntry> entries;

  /// Total children on disk (may exceed [entries] when capped).
  final int total;
  final bool truncated;

  int get shown => entries.length;
  int get remaining => total - shown;

  factory FsListing.fromJson(Map<String, dynamic> json) {
    return FsListing(
      path: json['path'] as String? ?? '',
      entries: (json['entries'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => FsEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int? ?? 0,
      truncated: json['truncated'] == true,
    );
  }
}

