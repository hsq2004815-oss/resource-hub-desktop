/// The data operations the shell needs.
///
/// [BackendRepository] is the real implementation (over the Python process);
/// tests use an in-memory fake so the UI can be exercised without spawning
/// anything. Keeping this interface small is deliberate — if a widget needs a
/// new capability it shows up here first.
library;

import '../models/resource_item.dart';
import '../platform/backend_client.dart';
import 'backend_models.dart';

abstract interface class ResourceApi {
  /// Backend-pushed events (global hotkey, later tray actions).
  Stream<BackendEvent> get events;

  Future<ResourceListPage> list(
    ViewMode mode, {
    String? query,
    String? category,
    bool? favoritesOnly,
    String? uncategorizedLabel,
    String? favoriteMark,
  });

  Future<ResourceItem> add(
    ViewMode mode, {
    required String name,
    required String target,
    String? category,
    String? note,
  });

  Future<ResourceItem> update(
    ViewMode mode, {
    required String id,
    required String name,
    required String target,
    String? category,
    String? note,
    String? browser,
  });

  Future<DeleteOutcome> delete(
    ViewMode mode,
    String id, {
    bool removeFromBrowser = false,
  });

  Future<ResourceItem> setFavorite(ViewMode mode, String id, {bool? value});

  /// Persists a manual order for [mode].
  ///
  /// [ids] must contain every entry of the collection exactly once (the UI
  /// always holds the unfiltered list, so drags inside a filtered view can send
  /// the complete order). Reordering never changes ids, categories or favourite
  /// flags — only the stored array order.
  Future<List<ResourceItem>> reorder(ViewMode mode, List<String> ids);

  /// Opens a resource. Links use their stored browser unless [browser]
  /// overrides it (empty string = system default browser).
  Future<void> open(ViewMode mode, String id, {String? browser});

  Future<void> reveal(ViewMode mode, String id);

  Future<PathCheckOutcome> checkPaths(ViewMode mode);

  /// Adds files/folders dropped onto the window to the folders collection.
  ///
  /// The backend always writes to `folders.json` (legacy behaviour), so the
  /// shell switches to folder mode after a successful drop.
  Future<DropOutcome> drop(List<String> paths);

  /// The current collection as plain JSON objects, for the export dialog.
  Future<List<Map<String, dynamic>>> export(ViewMode mode);

  /// Replaces the collection with [items] (legacy import semantics: import is a
  /// replacement, not a merge) and returns how many rows were kept/skipped.
  Future<ImportOutcome> import(
    ViewMode mode,
    List<Map<String, dynamic>> items,
  );

  /// One directory level under [path], for the folder preview panel.
  ///
  /// Read-only and lazy: the panel calls this once per expanded node.
  Future<FsListing> listChildren(String path);

  /// Opens an arbitrary discovered folder/file with the shell handler.
  Future<void> openPath(String path);

  /// Reveals an arbitrary discovered folder/file in Explorer.
  Future<void> revealPath(String path);

  /// Phase 17: imports new Chrome/Edge bookmarks into the sites collection.
  ///
  /// The backend only reads the browser files; this never modifies them.
  Future<BookmarkSyncResult> syncBookmarks();

  /// Watched browser profiles and the last bookmark sync state.
  Future<BookmarkStatus> loadBookmarkStatus();

  /// Installed browsers for the per-site "open with" choice (empty off Windows).
  Future<List<BrowserInfo>> listBrowsers();

  /// Cached site favicons as host → absolute icon path (empty before the first
  /// fetch). Icon failures are cosmetic: the UI keeps its generic glyph.
  Future<Map<String, String>> faviconMap();

  /// [faviconMap] and also asks the backend to download missing icons; the
  /// call returns immediately and the finished map arrives as a `favicons`
  /// event.
  Future<Map<String, String>> refreshFavicons();

  /// Browser bookmarks whose URL matches one of [urls] (read-only, Phase 18).
  Future<List<BookmarkMatch>> bookmarkMatches(List<String> urls);

  /// Whether the browser extension is connected (Phase 18).
  Future<BookmarkExtensionStatus> loadBookmarkExtensionStatus();

  // -- Phase 22: AI category suggestions (suggestion-only) -----------------
  /// Whether AI is enabled and an API key is configured.
  Future<AiStatus> loadAiStatus();

  /// Stores the API key in the backend's DPAPI-encrypted file. Empty clears it.
  Future<bool> setAiApiKey(String apiKey);

  /// Asks the configured AI endpoint to suggest categories for uncategorized
  /// resources. Nothing is written until the user confirms in the UI.
  Future<List<AiSuggestion>> suggestAiCategories();

  /// Whether [hotkeyId] can be registered right now.
  Future<bool> probeHotkey(String hotkeyId);

  /// (Re-)registers the global hotkey from the persisted settings.
  Future<HotkeyStatus> startHotkey();

  /// Releases the global hotkey (used while the settings dialog records a new
  /// combination, so the old one cannot fire and hide the window).
  Future<void> stopHotkey();
}
