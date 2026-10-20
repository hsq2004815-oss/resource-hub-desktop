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
const bool kDefaultBookmarkSyncEnabled = true;
const String kDefaultBookmarkCustomDir = '';
const String kDefaultBookmarkDeleteMode = 'ask';
const bool kDefaultShellContextMenuEnabled = true;
const String kDefaultAiBaseUrl = 'https://api.deepseek.com';
const String kDefaultAiModel = 'deepseek-chat';

/// `ask` = ask per delete, `remove` = also remove the browser bookmark,
/// `keep` = only delete locally (Phase 18).
const String kBookmarkDeleteAsk = 'ask';
const String kBookmarkDeleteRemove = 'remove';
const String kBookmarkDeleteKeep = 'keep';

/// Settings as stored by the backend (`settings.json`).
class AppSettings {
  const AppSettings({
    this.language = 'zh',
    this.globalHotkeyEnabled = true,
    this.globalHotkeyId = kDefaultGlobalHotkey,
    this.quickLinksHotkeyId = kDefaultQuickLinksHotkey,
    this.quickFoldersHotkeyId = kDefaultQuickFoldersHotkey,
    this.mouseSideButtonsEnabled = false,
    this.bookmarkSyncEnabled = kDefaultBookmarkSyncEnabled,
    this.bookmarkCustomDir = kDefaultBookmarkCustomDir,
    this.bookmarkDeleteMode = kDefaultBookmarkDeleteMode,
    this.shellContextMenuEnabled = kDefaultShellContextMenuEnabled,
    this.aiEnabled = false,
    this.aiBaseUrl = kDefaultAiBaseUrl,
    this.aiModel = kDefaultAiModel,
    this.launchAtStartup = false,
  });

  final String language;
  final bool globalHotkeyEnabled;
  final String globalHotkeyId;

  /// Phase 16: opens the compact web-links tree HUD without the main window.
  final String quickLinksHotkeyId;

  /// Phase 16: opens the compact folder tree HUD without the main window.
  final String quickFoldersHotkeyId;

  /// Opt-in: XBUTTON1 ("back") opens the web links HUD and XBUTTON2
  /// ("forward") the folders HUD. The hook swallows both buttons.
  final bool mouseSideButtonsEnabled;

  /// Phase 17: import new Chrome/Edge bookmarks into the sites list.
  final bool bookmarkSyncEnabled;

  /// Optional custom browser data directory (User Data dir, profile dir or a
  /// `Bookmarks` file). Empty means "auto-detect Chrome and Edge".
  final String bookmarkCustomDir;

  /// What a delete does with the browser bookmark (Phase 18):
  /// `ask`, `remove` or `keep`.
  final String bookmarkDeleteMode;

  /// Phase 19: show "添加到抽屉" in the Explorer folder context menu.
  final bool shellContextMenuEnabled;

  /// Phase 22: DeepSeek-compatible category suggestions (opt-in, off by
  /// default). The API key itself lives in an encrypted file, not here.
  final bool aiEnabled;
  final String aiBaseUrl;
  final String aiModel;
  final bool launchAtStartup;

  AppSettings copyWith({
    String? language,
    bool? globalHotkeyEnabled,
    String? globalHotkeyId,
    String? quickLinksHotkeyId,
    String? quickFoldersHotkeyId,
    bool? mouseSideButtonsEnabled,
    bool? bookmarkSyncEnabled,
    String? bookmarkCustomDir,
    String? bookmarkDeleteMode,
    bool? shellContextMenuEnabled,
    bool? aiEnabled,
    String? aiBaseUrl,
    String? aiModel,
    bool? launchAtStartup,
  }) {
    return AppSettings(
      language: language ?? this.language,
      globalHotkeyEnabled: globalHotkeyEnabled ?? this.globalHotkeyEnabled,
      globalHotkeyId: globalHotkeyId ?? this.globalHotkeyId,
      quickLinksHotkeyId: quickLinksHotkeyId ?? this.quickLinksHotkeyId,
      quickFoldersHotkeyId:
          quickFoldersHotkeyId ?? this.quickFoldersHotkeyId,
      mouseSideButtonsEnabled:
          mouseSideButtonsEnabled ?? this.mouseSideButtonsEnabled,
      bookmarkSyncEnabled: bookmarkSyncEnabled ?? this.bookmarkSyncEnabled,
      bookmarkCustomDir: bookmarkCustomDir ?? this.bookmarkCustomDir,
      bookmarkDeleteMode: bookmarkDeleteMode ?? this.bookmarkDeleteMode,
      shellContextMenuEnabled:
          shellContextMenuEnabled ?? this.shellContextMenuEnabled,
      aiEnabled: aiEnabled ?? this.aiEnabled,
      aiBaseUrl: aiBaseUrl ?? this.aiBaseUrl,
      aiModel: aiModel ?? this.aiModel,
      launchAtStartup: launchAtStartup ?? this.launchAtStartup,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'language': language,
        'globalHotkeyEnabled': globalHotkeyEnabled,
        'globalHotkeyId': globalHotkeyId,
        'quickLinksHotkeyId': quickLinksHotkeyId,
        'quickFoldersHotkeyId': quickFoldersHotkeyId,
        'mouseSideButtonsEnabled': mouseSideButtonsEnabled,
        'bookmarkSyncEnabled': bookmarkSyncEnabled,
        'bookmarkCustomDir': bookmarkCustomDir,
        'bookmarkDeleteMode': bookmarkDeleteMode,
        'shellContextMenuEnabled': shellContextMenuEnabled,
        'aiEnabled': aiEnabled,
        'aiBaseUrl': aiBaseUrl,
        'aiModel': aiModel,
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
      mouseSideButtonsEnabled:
          json['mouseSideButtonsEnabled'] as bool? ?? false,
      bookmarkSyncEnabled: json['bookmarkSyncEnabled'] as bool? ??
          kDefaultBookmarkSyncEnabled,
      bookmarkCustomDir: json['bookmarkCustomDir'] as String? ??
          kDefaultBookmarkCustomDir,
      bookmarkDeleteMode: json['bookmarkDeleteMode'] as String? ??
          kDefaultBookmarkDeleteMode,
      shellContextMenuEnabled: json['shellContextMenuEnabled'] as bool? ??
          kDefaultShellContextMenuEnabled,
      aiEnabled: json['aiEnabled'] as bool? ?? false,
      aiBaseUrl: json['aiBaseUrl'] as String? ?? kDefaultAiBaseUrl,
      aiModel: json['aiModel'] as String? ?? kDefaultAiModel,
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

/// One browser profile whose bookmarks are watched (Phase 17).
class BookmarkProfile {
  const BookmarkProfile({
    required this.label,
    required this.path,
    required this.bookmarks,
  });

  /// e.g. `Chrome · Default`, `Edge · Profile 1`, `自定义`.
  final String label;
  final String path;
  final int bookmarks;

  factory BookmarkProfile.fromJson(Map<String, dynamic> json) {
    return BookmarkProfile(
      label: json['label'] as String? ?? '',
      path: json['path'] as String? ?? '',
      bookmarks: (json['bookmarks'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Result of `bookmarks.status`.
class BookmarkStatus {
  const BookmarkStatus({
    this.enabled = true,
    this.customDir = '',
    this.profiles = const <BookmarkProfile>[],
    this.lastSyncAt,
    this.syncedUrls = 0,
  });

  final bool enabled;
  final String customDir;
  final List<BookmarkProfile> profiles;
  final String? lastSyncAt;
  final int syncedUrls;

  int get totalBookmarks => profiles.fold<int>(
        0,
        (int sum, BookmarkProfile profile) => sum + profile.bookmarks,
      );

  factory BookmarkStatus.fromJson(Map<String, dynamic> json) {
    return BookmarkStatus(
      enabled: json['enabled'] as bool? ?? true,
      customDir: json['customDir'] as String? ?? '',
      profiles: (json['profiles'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => BookmarkProfile.fromJson(
                e as Map<String, dynamic>,
              ))
          .toList(growable: false),
      lastSyncAt: json['lastSyncAt'] as String?,
      syncedUrls: (json['syncedUrls'] as num?)?.toInt() ?? 0,
    );
  }
}

/// Result of `bookmarks.sync`.
class BookmarkSyncResult {
  const BookmarkSyncResult({
    this.added = 0,
    this.skipped = 0,
    this.total = 0,
    this.profiles = const <BookmarkProfile>[],
    this.lastSyncAt,
  });

  final int added;
  final int skipped;
  final int total;
  final List<BookmarkProfile> profiles;
  final String? lastSyncAt;

  factory BookmarkSyncResult.fromJson(Map<String, dynamic> json) {
    return BookmarkSyncResult(
      added: (json['added'] as num?)?.toInt() ?? 0,
      skipped: (json['skipped'] as num?)?.toInt() ?? 0,
      total: (json['total'] as num?)?.toInt() ?? 0,
      profiles: (json['profiles'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => BookmarkProfile.fromJson(
                e as Map<String, dynamic>,
              ))
          .toList(growable: false),
      lastSyncAt: json['lastSyncAt'] as String?,
    );
  }
}

/// One browser bookmark matching a resource URL (Phase 18).
class BookmarkMatch {
  const BookmarkMatch({
    required this.url,
    this.title = '',
    this.label = '',
    this.path = '',
  });

  final String url;
  final String title;

  /// Browser profile label, e.g. `Chrome · Default`.
  final String label;
  final String path;

  factory BookmarkMatch.fromJson(Map<String, dynamic> json) {
    return BookmarkMatch(
      url: json['url'] as String? ?? '',
      title: json['title'] as String? ?? '',
      label: json['label'] as String? ?? '',
      path: json['path'] as String? ?? '',
    );
  }
}

/// Result of `bookmarks.extensionStatus` (Phase 18).
class BookmarkExtensionStatus {
  const BookmarkExtensionStatus({
    this.connected = false,
    this.lastSeenAt,
    this.port,
    this.pendingCommands = 0,
    this.extensionPath = '',
  });

  final bool connected;
  final String? lastSeenAt;
  final int? port;
  final int pendingCommands;

  /// Folder shipped next to the exe with the unpacked extension.
  final String extensionPath;

  factory BookmarkExtensionStatus.fromJson(Map<String, dynamic> json) {
    return BookmarkExtensionStatus(
      connected: json['connected'] == true,
      lastSeenAt: json['lastSeenAt'] as String?,
      port: (json['port'] as num?)?.toInt(),
      pendingCommands: (json['pendingCommands'] as num?)?.toInt() ?? 0,
      extensionPath: json['extensionPath'] as String? ?? '',
    );
  }
}

/// Result of `resources.delete` (Phase 18 adds the browser flags).
class DeleteOutcome {
  const DeleteOutcome({
    this.deleted = false,
    this.browserQueued = false,
    this.extensionConnected = false,
  });

  final bool deleted;

  /// A "remove bookmark" command was queued for the extension.
  final bool browserQueued;
  final bool extensionConnected;

  factory DeleteOutcome.fromJson(Map<String, dynamic> json) {
    return DeleteOutcome(
      deleted: json['deleted'] != false,
      browserQueued: json['browserQueued'] == true,
      extensionConnected: json['extensionConnected'] == true,
    );
  }
}

/// Result of `ai.status` (Phase 22).
class AiStatus {
  const AiStatus({
    this.enabled = false,
    this.configured = false,
    this.baseUrl = kDefaultAiBaseUrl,
    this.model = kDefaultAiModel,
  });

  final bool enabled;
  final bool configured;
  final String baseUrl;
  final String model;

  factory AiStatus.fromJson(Map<String, dynamic> json) {
    return AiStatus(
      enabled: json['enabled'] == true,
      configured: json['configured'] == true,
      baseUrl: json['baseUrl'] as String? ?? kDefaultAiBaseUrl,
      model: json['model'] as String? ?? kDefaultAiModel,
    );
  }
}

/// One AI category suggestion for an uncategorized resource (Phase 22).
class AiSuggestion {
  const AiSuggestion({
    required this.mode,
    required this.id,
    required this.name,
    required this.target,
    this.note = '',
    this.currentCategory = '',
    required this.suggestedCategory,
    this.reason = '',
  });

  final ViewMode mode;
  final String id;
  final String name;

  /// Path for folders, URL for links (echoed by the backend so the update can
  /// be applied without relying on a possibly stale local list).
  final String target;
  final String note;
  final String currentCategory;
  final String suggestedCategory;
  final String reason;

  factory AiSuggestion.fromJson(Map<String, dynamic> json) {
    return AiSuggestion(
      mode: json['mode'] == 'folders' ? ViewMode.folders : ViewMode.links,
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      target: json['target'] as String? ?? '',
      note: json['note'] as String? ?? '',
      currentCategory: json['currentCategory'] as String? ?? '',
      suggestedCategory: json['suggestedCategory'] as String? ?? '',
      reason: json['reason'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'mode': mode.name,
        'id': id,
        'name': name,
        'target': target,
        'note': note,
        'currentCategory': currentCategory,
        'suggestedCategory': suggestedCategory,
        'reason': reason,
      };
}
