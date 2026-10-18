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
  });

  Future<bool> delete(ViewMode mode, String id);

  Future<ResourceItem> setFavorite(ViewMode mode, String id, {bool? value});

  /// Persists a manual order for [mode].
  ///
  /// [ids] must contain every entry of the collection exactly once (the UI
  /// always holds the unfiltered list, so drags inside a filtered view can send
  /// the complete order). Reordering never changes ids, categories or favourite
  /// flags — only the stored array order.
  Future<List<ResourceItem>> reorder(ViewMode mode, List<String> ids);

  Future<void> open(ViewMode mode, String id);

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

  /// Whether [hotkeyId] can be registered right now.
  Future<bool> probeHotkey(String hotkeyId);

  /// (Re-)registers the global hotkey from the persisted settings.
  Future<HotkeyStatus> startHotkey();

  /// Releases the global hotkey (used while the settings dialog records a new
  /// combination, so the old one cannot fire and hide the window).
  Future<void> stopHotkey();
}
