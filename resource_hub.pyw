import ctypes
import json
import os
import subprocess
import sys
import traceback
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD


THEME = {
    "bg": "#f5efe5",
    "panel": "#fff9f1",
    "panel_strong": "#ffffff",
    "border": "#d7c5b1",
    "accent": "#bf5b2b",
    "accent_soft": "#efe4d3",
    "accent_muted": "#f4e4d7",
    "ink": "#2d241d",
    "muted": "#6d5a4c",
    "success": "#2f6b47",
    "danger": "#9d3f32",
}


STRINGS = {
    "zh": {
        "window_title": "常用资源工具",
        "current_mode": "当前模块",
        "mode_links_label": "网站管理",
        "mode_folders_label": "资源管理",
        "subtitle_links": "把常用网站放在同一个桌面工具里统一管理，列表会直接显示加入时间。",
        "subtitle_folders": "把常用文件和文件夹放在同一个桌面工具里统一管理，列表会直接显示加入时间。",
        "language_button": "EN",
        "switch_to_links": "网站",
        "switch_to_folders": "资源",
        "total_links": "链接总数",
        "total_folders": "资源总数",
        "categories": "分类数量",
        "visible_now": "当前显示",
        "form_add_link": "新增链接",
        "form_edit_link": "编辑链接",
        "form_add_folder": "新增资源",
        "form_edit_folder": "编辑资源",
        "save_link": "保存链接",
        "save_folder": "保存资源",
        "save_changes": "保存修改",
        "clear_form": "清空表单",
        "name_link": "网站名称",
        "name_folder": "资源名称",
        "path_link": "网址",
        "path_folder": "本地路径",
        "category": "分类",
        "notes": "备注",
        "added_at": "加入时间",
        "added_auto": "保存后自动记录",
        "browse": "选择",
        "browse_folder": "选文件夹",
        "browse_file": "选文件",
        "collection_links": "已保存链接",
        "collection_links_subtitle": "搜索、筛选并打开你的网站",
        "collection_folders": "已保存资源",
        "collection_folders_subtitle": "搜索、筛选并打开你的文件或文件夹",
        "summary_all": "当前显示 {0} / {1}",
        "summary_filtered": "当前显示 {0} / {1} · 分类：{2}",
        "summary_search": "当前显示 {0} / {1} · 搜索：{2}",
        "summary_search_filtered": "当前显示 {0} / {1} · 分类：{2} · 搜索：{3}",
        "empty_links": "还没有可显示的网站链接",
        "empty_folders": "还没有可显示的本地资源",
        "search": "搜索",
        "search_links_hint": "搜索名称、网址、分类、备注...",
        "search_folders_hint": "搜索名称、路径、类型、分类、备注...",
        "filter": "分类筛选",
        "all_categories": "全部分类",
        "uncategorized": "未分类",
        "favorite": "收藏",
        "unfavorite": "取消收藏",
        "favorite_mark": "收藏",
        "favorited": "已收藏，已置顶显示。",
        "unfavorited": "已取消收藏。",
        "check_paths": "检测路径",
        "path_ok": "正常",
        "path_missing": "路径失效",
        "paths_checked_all_ok": "路径检测完成，全部正常。",
        "paths_checked_missing": "路径检测完成，有 {0} 条资源路径失效。",
        "kind_folder": "文件夹",
        "kind_file": "文件",
        "open": "打开",
        "open_location": "打开所在位置",
        "edit": "编辑",
        "delete": "删除",
        "export": "导出",
        "import": "导入",
        "data_note_links": "数据保存在本文件夹的 sites.json 中。",
        "data_note_folders": "数据保存在本文件夹的 folders.json 中，可同时保存文件和文件夹。",
        "no_notes": "暂无备注",
        "select_first_link": "请先在右侧选中一条链接。",
        "select_first_folder": "请先在右侧选中一个资源。",
        "enter_link_name": "请先填写网站名称。",
        "enter_link_path": "请先填写网址。",
        "invalid_link_path": "网址格式不正确。",
        "link_saved": "链接已保存。",
        "link_updated": "链接已更新。",
        "link_deleted": "链接已删除。",
        "editing_link": "正在编辑链接：{0}",
        "enter_folder_name": "请先填写资源名称。",
        "enter_folder_path": "请先填写文件或文件夹路径。",
        "invalid_folder_path": "文件或文件夹路径不存在。",
        "folder_saved": "资源已保存。",
        "folder_updated": "资源已更新。",
        "folder_deleted": "资源已删除。",
        "editing_folder": "正在编辑资源：{0}",
        "confirm_delete_title": "删除确认",
        "confirm_delete_body": "确定删除“{0}”吗？",
        "import_failed": "导入失败，请检查 JSON 文件。",
        "backup_exported": "备份文件已导出。",
        "backup_imported": "备份导入成功。",
        "open_folder_failed": "文件或文件夹路径不存在。",
        "favorite_failed": "请先在右侧选中一条记录。",
        "path_check_links_disabled": "路径检测仅适用于本地资源。",
        "drop_ready": "可将文件或文件夹直接拖到窗口中，自动加入本地资源。",
        "drop_added": "已添加 {0} 个资源。",
        "drop_added_skipped": "已添加 {0} 个资源，跳过 {1} 个重复项。",
        "drop_switched": "已切换到本地资源并添加拖入内容。",
        "drop_invalid": "拖入内容里没有可用的文件或文件夹。",
        "col_name": "名称",
        "col_favorite": "收藏",
        "col_kind": "类型",
        "col_state": "状态",
        "col_category": "分类",
        "col_added_at": "加入时间",
        "col_url": "网址",
        "col_path": "本地路径",
        "col_notes": "备注",
    },
    "en": {
        "window_title": "Resource Hub Desktop",
        "current_mode": "Current Mode",
        "mode_links_label": "Website Manager",
        "mode_folders_label": "Resource Manager",
        "subtitle_links": "Save your common websites in one desktop tool. The list shows when each link was added.",
        "subtitle_folders": "Save your common files and folders in one desktop tool. The list shows when each item was added.",
        "language_button": "中文",
        "switch_to_links": "Websites",
        "switch_to_folders": "Resources",
        "total_links": "Total Links",
        "total_folders": "Total Resources",
        "categories": "Categories",
        "visible_now": "Visible Now",
        "form_add_link": "Add Link",
        "form_edit_link": "Edit Link",
        "form_add_folder": "Add Resource",
        "form_edit_folder": "Edit Resource",
        "save_link": "Save Link",
        "save_folder": "Save Resource",
        "save_changes": "Save Changes",
        "clear_form": "Clear Form",
        "name_link": "Link Name",
        "name_folder": "Resource Name",
        "path_link": "URL",
        "path_folder": "Local Path",
        "category": "Category",
        "notes": "Notes",
        "added_at": "Added At",
        "added_auto": "Auto-filled after saving",
        "browse": "Browse",
        "browse_folder": "Folder",
        "browse_file": "File",
        "collection_links": "Saved Links",
        "collection_links_subtitle": "Search, filter, and open your websites",
        "collection_folders": "Saved Resources",
        "collection_folders_subtitle": "Search, filter, and open your files and folders",
        "summary_all": "Showing {0} of {1}",
        "summary_filtered": "Showing {0} of {1} · Category: {2}",
        "summary_search": "Showing {0} of {1} · Search: {2}",
        "summary_search_filtered": "Showing {0} of {1} · Category: {2} · Search: {3}",
        "empty_links": "No website links to display yet",
        "empty_folders": "No local resources to display yet",
        "search": "Search",
        "search_links_hint": "Search name, URL, category, notes...",
        "search_folders_hint": "Search name, path, type, category, notes...",
        "filter": "Category",
        "all_categories": "All Categories",
        "uncategorized": "Uncategorized",
        "favorite": "Favorite",
        "unfavorite": "Unfavorite",
        "favorite_mark": "Favorite",
        "favorited": "Marked as favorite and moved to the top.",
        "unfavorited": "Removed from favorites.",
        "check_paths": "Check Paths",
        "path_ok": "OK",
        "path_missing": "Missing",
        "paths_checked_all_ok": "Path check finished. Everything looks good.",
        "paths_checked_missing": "Path check finished. {0} resources are missing.",
        "kind_folder": "Folder",
        "kind_file": "File",
        "open": "Open",
        "open_location": "Open Location",
        "edit": "Edit",
        "delete": "Delete",
        "export": "Export",
        "import": "Import",
        "data_note_links": "Data is saved to sites.json in this folder.",
        "data_note_folders": "Data is saved to folders.json in this folder and can include both files and folders.",
        "no_notes": "No notes",
        "select_first_link": "Select a link on the right first.",
        "select_first_folder": "Select a resource on the right first.",
        "enter_link_name": "Please enter a link name.",
        "enter_link_path": "Please enter a URL.",
        "invalid_link_path": "The URL format is invalid.",
        "link_saved": "Link saved.",
        "link_updated": "Link updated.",
        "link_deleted": "Link deleted.",
        "editing_link": "Editing link: {0}",
        "enter_folder_name": "Please enter a resource name.",
        "enter_folder_path": "Please enter a file or folder path.",
        "invalid_folder_path": "The file or folder path does not exist.",
        "folder_saved": "Resource saved.",
        "folder_updated": "Resource updated.",
        "folder_deleted": "Resource deleted.",
        "editing_folder": "Editing resource: {0}",
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_body": "Delete '{0}'?",
        "import_failed": "Import failed. Please check the JSON file.",
        "backup_exported": "Backup exported.",
        "backup_imported": "Backup imported.",
        "open_folder_failed": "The file or folder path does not exist.",
        "favorite_failed": "Select an item on the right first.",
        "path_check_links_disabled": "Path checking only applies to local resources.",
        "drop_ready": "You can drag files or folders into the window to add them as local resources.",
        "drop_added": "Added {0} resources.",
        "drop_added_skipped": "Added {0} resources and skipped {1} duplicates.",
        "drop_switched": "Switched to local resources and added the dropped items.",
        "drop_invalid": "No usable files or folders were found in the dropped items.",
        "col_name": "Name",
        "col_favorite": "Favorite",
        "col_kind": "Type",
        "col_state": "Status",
        "col_category": "Category",
        "col_added_at": "Added At",
        "col_url": "URL",
        "col_path": "Local Path",
        "col_notes": "Notes",
    },
}


class ResourceHubApp(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        if getattr(sys, "frozen", False):
            self.bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.bundle_dir = Path(__file__).resolve().parent
            self.base_dir = self.bundle_dir
        self.site_path = self.base_dir / "sites.json"
        self.folder_path = self.base_dir / "folders.json"
        self.icon_path = self.base_dir / "DesktopShortcut.ico"
        if not self.icon_path.exists():
            self.icon_path = self.base_dir / "LinkHub.ico"
        if not self.icon_path.exists():
            self.icon_path = self.bundle_dir / "DesktopShortcut.ico"
        if not self.icon_path.exists():
            self.icon_path = self.bundle_dir / "LinkHub.ico"
        self.app_id = "Mytools.ResourceHub.Python"
        self.language = "zh"
        self.mode = "links"
        self.editing_id = None
        self.link_filter_value = "__all__"
        self.folder_filter_value = "__all__"
        self.link_search_value = ""
        self.folder_search_value = ""
        self.sites = []
        self.folders = []
        self._build_window()
        self._build_styles()
        self._build_ui()
        self._setup_drop_targets()
        self._load_all_data()
        self.apply_language()
        self.refresh_view()

    def t(self, key: str) -> str:
        return STRINGS[self.language].get(key, key)

    def _build_window(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)
        except Exception:
            pass
        self.title(self.t("window_title"))
        self.geometry("1280x820")
        self.minsize(1180, 760)
        self.configure(bg=THEME["bg"])
        try:
            self.iconbitmap(self.icon_path)
        except Exception:
            pass

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Hub.Treeview", background=THEME["panel_strong"], fieldbackground=THEME["panel_strong"], foreground=THEME["ink"], rowheight=30)
        style.configure("Hub.Treeview.Heading", background=THEME["accent_soft"], foreground=THEME["ink"], relief="flat")
        style.map("Hub.Treeview", background=[("selected", "#e7d6c2")], foreground=[("selected", THEME["ink"])])
        style.configure("Hub.TCombobox", fieldbackground=THEME["panel_strong"], background=THEME["panel_strong"])

    def _panel(self, parent: tk.Widget, **grid_kwargs) -> tk.Frame:
        frame = tk.Frame(parent, bg=THEME["panel"], bd=1, relief="solid", highlightthickness=0)
        if grid_kwargs:
            frame.grid(**grid_kwargs)
        return frame

    def _make_stat(self, parent: tk.Widget, column: int):
        card = tk.Frame(parent, bg=THEME["panel_strong"], bd=1, relief="solid", width=160, height=90)
        card.grid(row=0, column=column, padx=(0 if column == 0 else 14, 0), sticky="ne")
        card.grid_propagate(False)
        value = tk.Label(card, bg=THEME["panel_strong"], fg=THEME["ink"], font=("Georgia", 20, "bold"))
        value.place(x=14, y=10)
        caption = tk.Label(card, bg=THEME["panel_strong"], fg=THEME["muted"], font=("Microsoft YaHei UI", 10))
        caption.place(x=14, y=52)
        return value, caption

    def _form_label(self, parent: tk.Widget, row: int) -> tk.Label:
        label = tk.Label(parent, bg=THEME["panel"], fg=THEME["ink"], font=("Microsoft YaHei UI", 9, "bold"))
        label.grid(row=row, column=0, padx=20, pady=(0, 6), sticky="w")
        return label

    def _entry(self, parent: tk.Widget, row: int) -> tk.Entry:
        entry = tk.Entry(parent, bg=THEME["panel_strong"], relief="solid", bd=1, font=("Microsoft YaHei UI", 10))
        entry.grid(row=row, column=0, padx=20, pady=(0, 12), sticky="ew")
        return entry

    def _action_button(self, parent: tk.Widget, column: int, bg: str, fg: str, command) -> tk.Button:
        button = tk.Button(parent, bg=bg, fg=fg, relief="flat", width=8, command=command, cursor="hand2")
        button.grid(row=0, column=column, padx=(12 if column else 0, 0))
        self._style_button(button, bg, fg)
        return button

    def _style_button(self, button: tk.Button, bg: str, fg: str) -> None:
        button.config(
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=12,
            pady=8,
            activebackground=bg,
            activeforeground=fg,
            highlightthickness=0,
            bd=0,
        )

    def _load_json(self, path: Path):
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_json(self, path: Path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _setup_drop_targets(self) -> None:
        targets = [self, self.header, self.left_panel, self.right_panel, self.tree]
        for widget in targets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop_files)
            except Exception:
                pass

    def _on_drop_files(self, event) -> str:
        try:
            paths = [path for path in self.tk.splitlist(event.data) if path]
            self.add_dropped_resources(paths)
        except Exception as exc:
            self.set_status(text=str(exc), color=THEME["danger"])
        return "break"

    def _default_sites(self):
        now = datetime.now().astimezone().isoformat()
        return [
            {"id": str(uuid.uuid4()), "name": "OpenAI", "url": "https://openai.com/", "category": "AI", "note": "Official website", "favorite": False, "createdAt": now},
            {"id": str(uuid.uuid4()), "name": "GitHub", "url": "https://github.com/", "category": "Development", "note": "Code hosting and collaboration", "favorite": False, "createdAt": now},
        ]

    def _default_folders(self):
        home = Path.home()
        candidates = [("Desktop", home / "Desktop"), ("Documents", home / "Documents"), ("Downloads", home / "Downloads")]
        now = datetime.now().astimezone().isoformat()
        items = []
        for name, folder in candidates:
            if folder.exists():
                items.append({"id": str(uuid.uuid4()), "name": name, "path": str(folder), "kind": "folder", "category": "System", "note": "Quick access", "favorite": False, "createdAt": now})
        if not items:
            items.append({"id": str(uuid.uuid4()), "name": "App Folder", "path": str(self.base_dir), "kind": "folder", "category": "System", "note": "", "favorite": False, "createdAt": now})
        return items

    def _normalize_url(self, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if "://" in value:
            return value
        return f"https://{value}"

    def _normalize_folder_path(self, value: str) -> str:
        if not value.strip():
            return ""
        return str(Path(os.path.expandvars(value.strip())).expanduser())

    def _normalize_site(self, item):
        category = item.get("category") or "__uncategorized__"
        if category in {"Uncategorized", "未分类"}:
            category = "__uncategorized__"
        return {
            "id": str(item.get("id") or uuid.uuid4()),
            "name": str(item.get("name") or ""),
            "url": self._normalize_url(str(item.get("url") or "")),
            "category": category,
            "note": str(item.get("note") or ""),
            "favorite": bool(item.get("favorite")),
            "createdAt": str(item.get("createdAt") or datetime.now().astimezone().isoformat()),
        }

    def _normalize_folder(self, item):
        category = item.get("category") or "__uncategorized__"
        if category in {"Uncategorized", "未分类"}:
            category = "__uncategorized__"
        raw_path = item.get("path") or item.get("url") or ""
        normalized_path = self._normalize_folder_path(str(raw_path))
        kind = str(item.get("kind") or "").lower()
        if kind not in {"file", "folder"}:
            kind = "folder" if Path(normalized_path).suffix == "" and Path(normalized_path).exists() and Path(normalized_path).is_dir() else "file"
            if Path(normalized_path).exists() and Path(normalized_path).is_dir():
                kind = "folder"
        return {
            "id": str(item.get("id") or uuid.uuid4()),
            "name": str(item.get("name") or ""),
            "path": normalized_path,
            "kind": kind,
            "category": category,
            "note": str(item.get("note") or ""),
            "favorite": bool(item.get("favorite")),
            "createdAt": str(item.get("createdAt") or datetime.now().astimezone().isoformat()),
        }

    def _load_all_data(self):
        self.sites = [self._normalize_site(item) for item in self._load_json(self.site_path) if item.get("name") and item.get("url")]
        self.folders = [self._normalize_folder(item) for item in self._load_json(self.folder_path) if item.get("name") and (item.get("path") or item.get("url"))]
        if not self.sites:
            self.sites = self._default_sites()
            self._write_json(self.site_path, self.sites)
        if not self.folders:
            self.folders = self._default_folders()
            self._write_json(self.folder_path, self.folders)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = self._panel(self)
        self.header.grid(row=0, column=0, padx=16, pady=(16, 12), sticky="nsew")
        self.header.grid_columnconfigure(0, weight=1)

        title_wrap = tk.Frame(self.header, bg=THEME["panel"])
        title_wrap.grid(row=0, column=0, padx=24, pady=20, sticky="nw")
        self.title_label = tk.Label(title_wrap, bg=THEME["panel"], fg=THEME["ink"], font=("Microsoft YaHei UI", 22, "bold"), anchor="w")
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(title_wrap, bg=THEME["panel"], fg=THEME["muted"], font=("Microsoft YaHei UI", 10), anchor="w", justify="left")
        self.subtitle_label.pack(anchor="w", pady=(8, 0))
        self.mode_badge = tk.Label(
            title_wrap,
            bg=THEME["accent_soft"],
            fg=THEME["ink"],
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.mode_badge.pack(anchor="w", pady=(12, 0))

        action_wrap = tk.Frame(self.header, bg=THEME["panel"])
        action_wrap.grid(row=0, column=1, padx=(0, 20), pady=18, sticky="ne")
        self.language_button = tk.Button(action_wrap, width=7, bg=THEME["panel_strong"], fg=THEME["ink"], relief="solid", bd=1, command=self.toggle_language, cursor="hand2")
        self.language_button.grid(row=0, column=0, padx=(0, 10))
        self.mode_button = tk.Button(action_wrap, width=9, bg=THEME["accent_soft"], fg=THEME["ink"], relief="flat", command=self.switch_mode, cursor="hand2")
        self.mode_button.grid(row=0, column=1)
        self._style_button(self.language_button, THEME["panel_strong"], THEME["ink"])
        self.language_button.config(relief="solid", bd=1, padx=10, pady=7)
        self._style_button(self.mode_button, THEME["accent_soft"], THEME["ink"])

        stats_wrap = tk.Frame(self.header, bg=THEME["panel"])
        stats_wrap.grid(row=0, column=2, padx=(0, 16), pady=18, sticky="ne")
        self.total_value, self.total_caption = self._make_stat(stats_wrap, 0)
        self.category_value, self.category_caption = self._make_stat(stats_wrap, 1)
        self.visible_value, self.visible_caption = self._make_stat(stats_wrap, 2)

        body = tk.Frame(self, bg=THEME["bg"])
        body.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.left_panel = self._panel(body, row=0, column=0, sticky="nsw")
        self.left_panel.config(width=340, height=600)
        self.left_panel.grid_propagate(False)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.form_title_label = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["ink"], font=("Microsoft YaHei UI", 16, "bold"))
        self.form_title_label.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="w")
        self.name_label = self._form_label(self.left_panel, 1)
        self.name_entry = self._entry(self.left_panel, 2)
        self.path_label = self._form_label(self.left_panel, 3)

        path_row = tk.Frame(self.left_panel, bg=THEME["panel"])
        path_row.grid(row=4, column=0, padx=20, pady=(0, 12), sticky="ew")
        path_row.grid_columnconfigure(0, weight=1)
        self.path_entry = tk.Entry(path_row, bg=THEME["panel_strong"], relief="solid", bd=1, font=("Microsoft YaHei UI", 10))
        self.path_entry.grid(row=0, column=0, sticky="ew")
        self.browse_folder_button = tk.Button(path_row, bg=THEME["accent_soft"], fg=THEME["ink"], relief="flat", width=8, command=self.browse_folder, cursor="hand2")
        self.browse_folder_button.grid(row=0, column=1, padx=(10, 0))
        self._style_button(self.browse_folder_button, THEME["accent_soft"], THEME["ink"])
        self.browse_file_button = tk.Button(path_row, bg=THEME["accent_muted"], fg=THEME["ink"], relief="flat", width=8, command=self.browse_file, cursor="hand2")
        self.browse_file_button.grid(row=0, column=2, padx=(10, 0))
        self._style_button(self.browse_file_button, THEME["accent_muted"], THEME["ink"])

        self.category_label = self._form_label(self.left_panel, 5)
        self.category_entry = self._entry(self.left_panel, 6)
        self.notes_label = self._form_label(self.left_panel, 7)
        self.notes_text = tk.Text(self.left_panel, height=6, bg=THEME["panel_strong"], relief="solid", bd=1, font=("Microsoft YaHei UI", 10))
        self.notes_text.grid(row=8, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.added_label = self._form_label(self.left_panel, 9)
        self.added_value = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["muted"], font=("Microsoft YaHei UI", 10))
        self.added_value.grid(row=10, column=0, padx=20, pady=(0, 8), sticky="w")
        self.data_note_label = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["muted"], font=("Microsoft YaHei UI", 10), wraplength=280, justify="left")
        self.data_note_label.grid(row=11, column=0, padx=20, pady=(0, 12), sticky="w")

        button_row = tk.Frame(self.left_panel, bg=THEME["panel"])
        button_row.grid(row=12, column=0, padx=20, pady=(0, 10), sticky="w")
        self.save_button = tk.Button(button_row, bg=THEME["accent"], fg="white", relief="flat", width=12, command=self.save_current, cursor="hand2")
        self.save_button.grid(row=0, column=0, padx=(0, 12))
        self.clear_button = tk.Button(button_row, bg=THEME["accent_soft"], fg=THEME["ink"], relief="flat", width=10, command=self.clear_form, cursor="hand2")
        self.clear_button.grid(row=0, column=1)
        self._style_button(self.save_button, THEME["accent"], "white")
        self._style_button(self.clear_button, THEME["accent_soft"], THEME["ink"])
        self.status_label = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["success"], font=("Microsoft YaHei UI", 10), wraplength=280, justify="left")
        self.status_label.grid(row=13, column=0, padx=20, pady=(0, 12), sticky="w")

        self.right_panel = self._panel(body, row=0, column=1, padx=(16, 0), sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=1)

        self.collection_title_label = tk.Label(self.right_panel, bg=THEME["panel"], fg=THEME["ink"], font=("Microsoft YaHei UI", 16, "bold"))
        self.collection_title_label.grid(row=0, column=0, padx=20, pady=(18, 4), sticky="w")
        self.collection_subtitle_label = tk.Label(self.right_panel, bg=THEME["panel"], fg=THEME["muted"], font=("Microsoft YaHei UI", 10))
        self.collection_subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")
        self.collection_meta_label = tk.Label(self.right_panel, bg=THEME["panel"], fg=THEME["muted"], font=("Microsoft YaHei UI", 9, "bold"))
        self.collection_meta_label.grid(row=1, column=0, padx=20, pady=(18, 12), sticky="e")

        toolbar = tk.Frame(self.right_panel, bg=THEME["panel"])
        toolbar.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="e")
        self.open_button = self._action_button(toolbar, 0, THEME["accent"], "white", self.open_selected)
        self.favorite_button = self._action_button(toolbar, 1, THEME["panel_strong"], THEME["ink"], self.toggle_favorite_selected)
        self.check_paths_button = self._action_button(toolbar, 2, THEME["accent_muted"], THEME["ink"], self.check_paths)
        self.edit_button = self._action_button(toolbar, 3, THEME["accent_soft"], THEME["ink"], self.start_edit_selected)
        self.delete_button = self._action_button(toolbar, 4, THEME["danger"], "white", self.delete_selected)
        self.export_button = self._action_button(toolbar, 5, THEME["accent_muted"], THEME["ink"], self.export_current)
        self.import_button = self._action_button(toolbar, 6, THEME["accent_soft"], THEME["ink"], self.import_current)

        filter_row = tk.Frame(self.right_panel, bg=THEME["panel"])
        filter_row.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")
        filter_row.grid_columnconfigure(1, weight=1)
        self.search_label = tk.Label(filter_row, bg=THEME["panel"], fg=THEME["ink"], font=("Microsoft YaHei UI", 9, "bold"))
        self.search_label.grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search_change)
        self.search_entry = tk.Entry(filter_row, textvariable=self.search_var, bg=THEME["panel_strong"], relief="solid", bd=1, font=("Microsoft YaHei UI", 10))
        self.search_entry.grid(row=1, column=0, columnspan=2, pady=(8, 0), sticky="ew")
        self.search_hint_label = tk.Label(filter_row, bg=THEME["panel"], fg=THEME["muted"], font=("Microsoft YaHei UI", 10))
        self.search_hint_label.grid(row=1, column=2, padx=(14, 0), sticky="w")
        self.filter_label = tk.Label(filter_row, bg=THEME["panel"], fg=THEME["ink"], font=("Microsoft YaHei UI", 9, "bold"))
        self.filter_label.grid(row=0, column=3, padx=(20, 0), sticky="w")
        self.filter_var = tk.StringVar()
        self.filter_combo = ttk.Combobox(filter_row, textvariable=self.filter_var, state="readonly", style="Hub.TCombobox")
        self.filter_combo.grid(row=1, column=3, padx=(20, 0), pady=(8, 0), sticky="e")
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_view())

        table_wrap = tk.Frame(self.right_panel, bg=THEME["panel"])
        table_wrap.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_wrap, columns=("favorite", "name", "kind", "state", "category", "added", "path", "notes"), show="headings", style="Hub.Treeview")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.on_select())
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())
        self.tree.bind("<Configure>", lambda _event: self._resize_columns())
        self.tree.tag_configure("missing", foreground=THEME["danger"])
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.empty_label = tk.Label(
            table_wrap,
            bg=THEME["panel_strong"],
            fg=THEME["muted"],
            font=("Microsoft YaHei UI", 11, "bold"),
            padx=18,
            pady=12,
        )

    def current_items(self):
        return self.sites if self.mode == "links" else self.folders

    def current_filter_value(self) -> str:
        return self.link_filter_value if self.mode == "links" else self.folder_filter_value

    def set_current_filter_value(self, value: str) -> None:
        if self.mode == "links":
            self.link_filter_value = value
        else:
            self.folder_filter_value = value

    def current_search_value(self) -> str:
        return self.link_search_value if self.mode == "links" else self.folder_search_value

    def set_current_search_value(self, value: str) -> None:
        if self.mode == "links":
            self.link_search_value = value
        else:
            self.folder_search_value = value

    def current_path_key(self) -> str:
        return "url" if self.mode == "links" else "path"

    def current_data_path(self) -> Path:
        return self.site_path if self.mode == "links" else self.folder_path

    def save_current_collection(self) -> None:
        path = self.current_data_path()
        if self.mode == "links":
            self._write_json(path, self.sites)
        else:
            self._write_json(path, self.folders)

    def format_added(self, value: str) -> str:
        if not value:
            return ""
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return value

    def display_category(self, value: str) -> str:
        return self.t("uncategorized") if value == "__uncategorized__" else value

    def display_kind(self, value: str) -> str:
        if value == "folder":
            return self.t("kind_folder")
        if value == "file":
            return self.t("kind_file")
        return value

    def display_favorite(self, value: bool) -> str:
        return "★" if value else ""

    def resource_path_exists(self, item) -> bool:
        path = item.get("path", "")
        return bool(path) and Path(path).exists()

    def display_resource_state(self, item) -> str:
        return self.t("path_ok") if self.resource_path_exists(item) else self.t("path_missing")

    def _make_resource_name(self, path: Path) -> str:
        return path.name or str(path)

    def add_dropped_resources(self, raw_paths) -> None:
        valid_paths = []
        for raw_path in raw_paths:
            normalized = self._normalize_folder_path(str(raw_path))
            if not normalized:
                continue
            candidate = Path(normalized)
            if candidate.exists():
                valid_paths.append(candidate)

        if not valid_paths:
            self.set_status("drop_invalid", color=THEME["danger"])
            return

        switched = False
        if self.mode == "links":
            self.mode = "folders"
            self.editing_id = None
            switched = True
            self.apply_language()

        existing_paths = {item.get("path", "").lower() for item in self.folders}
        added = 0
        skipped = 0
        now = datetime.now().astimezone
        for candidate in valid_paths:
            normalized_path = str(candidate)
            key = normalized_path.lower()
            if key in existing_paths:
                skipped += 1
                continue
            self.folders.insert(
                0,
                {
                    "id": str(uuid.uuid4()),
                    "name": self._make_resource_name(candidate),
                    "path": normalized_path,
                    "kind": "folder" if candidate.is_dir() else "file",
                    "category": "__uncategorized__",
                    "note": "",
                    "favorite": False,
                    "createdAt": now().isoformat(),
                },
            )
            existing_paths.add(key)
            added += 1

        if added:
            self.save_current_collection()
            self.clear_form()
            if skipped:
                self.set_status("drop_added_skipped", args=[added, skipped])
            elif switched:
                self.set_status("drop_switched")
            else:
                self.set_status("drop_added", args=[added])
            self.refresh_view()
            return

        if skipped:
            self.set_status("drop_added_skipped", args=[0, skipped], color=THEME["muted"])
        else:
            self.set_status("drop_invalid", color=THEME["danger"])

    def set_status(self, key: str = "", color: str | None = None, args=None, text: str | None = None) -> None:
        if text is None:
            template = self.t(key) if key else ""
            text = template.format(*(args or [])) if template else ""
        self.status_label.config(text=text, fg=color or THEME["success"])

    def current_filter_resolved(self) -> str:
        display_value = self.filter_var.get().strip()
        if not display_value or display_value == self.t("all_categories"):
            return "__all__"
        for item in self.current_items():
            if self.display_category(item["category"]) == display_value:
                return item["category"]
        return "__all__"

    def selected_item(self):
        selection = self.tree.selection()
        if not selection:
            return None
        selected_id = selection[0]
        for item in self.current_items():
            if item["id"] == selected_id:
                return item
        return None

    def clear_form(self) -> None:
        self.editing_id = None
        self.name_entry.delete(0, tk.END)
        self.path_entry.delete(0, tk.END)
        self.category_entry.delete(0, tk.END)
        self.notes_text.delete("1.0", tk.END)
        self.added_value.config(text=self.t("added_auto"))
        self.set_status(text="")
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection())
        self.update_mode_ui()

    def on_search_change(self, *_args) -> None:
        self.set_current_search_value(self.search_var.get())
        self.refresh_view()

    def toggle_language(self) -> None:
        self.language = "en" if self.language == "zh" else "zh"
        self.apply_language()
        self.refresh_view()

    def switch_mode(self) -> None:
        self.mode = "folders" if self.mode == "links" else "links"
        self.editing_id = None
        self.search_var.set(self.current_search_value())
        self.apply_language()
        self.refresh_view()

    def browse_folder(self) -> None:
        if self.mode == "links":
            return
        path = filedialog.askdirectory(initialdir=self.base_dir)
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def browse_file(self) -> None:
        if self.mode == "links":
            return
        path = filedialog.askopenfilename(initialdir=self.base_dir)
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def apply_language(self) -> None:
        self.title(self.t("window_title"))
        self.title_label.config(text=self.t("window_title"))
        self.subtitle_label.config(text=self.t("subtitle_links" if self.mode == "links" else "subtitle_folders"))
        self.mode_badge.config(
            text=f"{self.t('current_mode')} · {self.t('mode_links_label' if self.mode == 'links' else 'mode_folders_label')}"
        )
        self.language_button.config(text=self.t("language_button"))
        self.total_caption.config(text=self.t("total_links" if self.mode == "links" else "total_folders"))
        self.category_caption.config(text=self.t("categories"))
        self.visible_caption.config(text=self.t("visible_now"))
        self.name_label.config(text=self.t("name_link" if self.mode == "links" else "name_folder"))
        self.path_label.config(text=self.t("path_link" if self.mode == "links" else "path_folder"))
        self.category_label.config(text=self.t("category"))
        self.notes_label.config(text=self.t("notes"))
        self.added_label.config(text=self.t("added_at"))
        self.search_label.config(text=self.t("search"))
        self.search_hint_label.config(text=self.t("search_links_hint" if self.mode == "links" else "search_folders_hint"))
        self.filter_label.config(text=self.t("filter"))
        self.open_button.config(text=self.t("open"))
        self.favorite_button.config(text=self.t("favorite"))
        self.check_paths_button.config(text=self.t("check_paths"))
        self.edit_button.config(text=self.t("edit"))
        self.delete_button.config(text=self.t("delete"))
        self.export_button.config(text=self.t("export"))
        self.import_button.config(text=self.t("import"))
        self.browse_folder_button.config(text=self.t("browse_folder"))
        self.browse_file_button.config(text=self.t("browse_file"))
        self.clear_button.config(text=self.t("clear_form"))
        data_note = self.t("data_note_links") if self.mode == "links" else f"{self.t('data_note_folders')}\n{self.t('drop_ready')}"
        self.data_note_label.config(text=data_note)
        self.tree.heading("favorite", text=self.t("col_favorite"))
        self.tree.heading("name", text=self.t("col_name"))
        self.tree.heading("kind", text=self.t("col_kind"))
        self.tree.heading("state", text=self.t("col_state"))
        self.tree.heading("category", text=self.t("col_category"))
        self.tree.heading("added", text=self.t("col_added_at"))
        self.tree.heading("path", text=self.t("col_url" if self.mode == "links" else "col_path"))
        self.tree.heading("notes", text=self.t("col_notes"))
        self.empty_label.config(text=self.t("empty_links" if self.mode == "links" else "empty_folders"))
        if self.search_var.get() != self.current_search_value():
            self.search_var.set(self.current_search_value())
        self.update_mode_ui()
        self.refresh_categories()

    def update_mode_ui(self) -> None:
        is_links = self.mode == "links"
        selected = self.selected_item()
        self.mode_button.config(text=self.t("switch_to_folders" if is_links else "switch_to_links"))
        self.form_title_label.config(text=self.t("form_edit_link" if is_links and self.editing_id else "form_add_link" if is_links else "form_edit_folder" if self.editing_id else "form_add_folder"))
        self.collection_title_label.config(text=self.t("collection_links" if is_links else "collection_folders"))
        self.collection_subtitle_label.config(text=self.t("collection_links_subtitle" if is_links else "collection_folders_subtitle"))
        self.save_button.config(text=self.t("save_changes" if self.editing_id else "save_link" if is_links else "save_folder"))
        self.favorite_button.config(text=self.t("unfavorite" if selected and selected.get("favorite") else "favorite"))
        self.check_paths_button.config(state=("disabled" if is_links else "normal"))
        self.browse_folder_button.config(state=("disabled" if is_links else "normal"))
        self.browse_file_button.config(state=("disabled" if is_links else "normal"))
        self.tree["displaycolumns"] = ("favorite", "name", "category", "added", "path", "notes") if is_links else ("favorite", "name", "kind", "state", "category", "added", "path", "notes")
        if not self.editing_id:
            self.added_value.config(text=self.t("added_auto"))

    def refresh_categories(self) -> None:
        categories = sorted({self.display_category(item["category"]) for item in self.current_items()}, key=str.casefold)
        values = [self.t("all_categories"), *categories]
        current = self.current_filter_value()
        if current == "__all__":
            display = self.t("all_categories")
        else:
            display = self.display_category(current)
        if display not in values:
            display = self.t("all_categories")
            self.set_current_filter_value("__all__")
        self.filter_combo["values"] = values
        self.filter_var.set(display)

    def refresh_view(self) -> None:
        self.set_current_filter_value(self.current_filter_resolved())
        self.refresh_categories()

        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        query = self.search_var.get().strip().lower()
        current_filter = self.current_filter_value()
        visible = []
        path_key = self.current_path_key()

        for item in self.current_items():
            if current_filter != "__all__" and item["category"] != current_filter:
                continue
            haystack = " ".join(
                [
                    self.t("favorite_mark") if item.get("favorite") else "",
                    item.get("name", ""),
                    item.get("kind", ""),
                    self.display_resource_state(item) if self.mode != "links" else "",
                    item.get(path_key, ""),
                    item.get("category", ""),
                    item.get("note", ""),
                    self.display_kind(item.get("kind", "")),
                    self.display_category(item.get("category", "")),
                ]
            ).lower()
            if query and query not in haystack:
                continue
            visible.append(item)

        visible = [item for _index, item in sorted(enumerate(visible), key=lambda pair: (0 if pair[1].get("favorite") else 1, pair[0]))]

        for item in visible:
            notes = item["note"].strip() if item["note"].strip() else self.t("no_notes")
            state = "" if self.mode == "links" else self.display_resource_state(item)
            tags = ("missing",) if self.mode != "links" and state == self.t("path_missing") else ()
            self.tree.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    self.display_favorite(bool(item.get("favorite"))),
                    item["name"],
                    "" if self.mode == "links" else self.display_kind(item.get("kind", "")),
                    state,
                    self.display_category(item["category"]),
                    self.format_added(item["createdAt"]),
                    item.get(path_key, ""),
                    notes,
                ),
                tags=tags,
            )

        total = len(self.current_items())
        categories = len({item["category"] for item in self.current_items()})
        self.total_value.config(text=str(total))
        self.category_value.config(text=str(categories))
        self.visible_value.config(text=str(len(visible)))
        filter_text = self.display_category(current_filter) if current_filter != "__all__" else ""
        if query and filter_text:
            summary = self.t("summary_search_filtered").format(len(visible), total, filter_text, query)
        elif query:
            summary = self.t("summary_search").format(len(visible), total, query)
        elif filter_text:
            summary = self.t("summary_filtered").format(len(visible), total, filter_text)
        else:
            summary = self.t("summary_all").format(len(visible), total)
        self.collection_meta_label.config(text=summary)
        if visible:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.45, anchor="center")
        self._resize_columns()
        self.update_mode_ui()

    def _resize_columns(self) -> None:
        width = max(self.tree.winfo_width(), 720)
        if self.mode == "links":
            widths = {
                "favorite": int(width * 0.07),
                "name": int(width * 0.16),
                "kind": 0,
                "state": 0,
                "category": int(width * 0.14),
                "added": int(width * 0.17),
                "path": int(width * 0.29),
                "notes": int(width * 0.17),
            }
        else:
            widths = {
                "favorite": int(width * 0.07),
                "name": int(width * 0.13),
                "kind": int(width * 0.08),
                "state": int(width * 0.12),
                "category": int(width * 0.11),
                "added": int(width * 0.14),
                "path": int(width * 0.21),
                "notes": int(width * 0.14),
            }
        for column, column_width in widths.items():
            min_width = 0 if column in {"kind", "state"} and self.mode == "links" else (56 if column == "favorite" else 90)
            stretch = False if column in {"kind", "state"} and self.mode == "links" else (False if column == "favorite" else True)
            self.tree.column(column, width=column_width, minwidth=min_width, stretch=stretch)

    def on_select(self) -> None:
        item = self.selected_item()
        if item and self.editing_id is None:
            self.added_value.config(text=self.format_added(item["createdAt"]))
        elif self.editing_id is None:
            self.added_value.config(text=self.t("added_auto"))
        self.update_mode_ui()

    def start_edit_selected(self) -> None:
        item = self.selected_item()
        if not item:
            self.set_status("select_first_link" if self.mode == "links" else "select_first_folder", color=THEME["danger"])
            return
        self.editing_id = item["id"]
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, item["name"])
        self.path_entry.delete(0, tk.END)
        self.path_entry.insert(0, item.get(self.current_path_key(), ""))
        self.category_entry.delete(0, tk.END)
        self.category_entry.insert(0, "" if item["category"] == "__uncategorized__" else item["category"])
        self.notes_text.delete("1.0", tk.END)
        if item["note"]:
            self.notes_text.insert("1.0", item["note"])
        self.added_value.config(text=self.format_added(item["createdAt"]))
        self.set_status("editing_link" if self.mode == "links" else "editing_folder", args=[item["name"]], color=THEME["muted"])
        self.update_mode_ui()

    def toggle_favorite_selected(self) -> None:
        item = self.selected_item()
        if not item:
            self.set_status("favorite_failed", color=THEME["danger"])
            return
        item["favorite"] = not bool(item.get("favorite"))
        self.save_current_collection()
        self.set_status("favorited" if item["favorite"] else "unfavorited")
        self.refresh_view()
        self.tree.selection_set(item["id"])
        self.tree.focus(item["id"])
        self.on_select()

    def check_paths(self) -> None:
        if self.mode == "links":
            self.set_status("path_check_links_disabled", color=THEME["muted"])
            return
        missing = sum(1 for item in self.folders if not self.resource_path_exists(item))
        self.refresh_view()
        if missing:
            self.set_status("paths_checked_missing", args=[missing], color=THEME["danger"])
        else:
            self.set_status("paths_checked_all_ok")

    def delete_selected(self) -> None:
        item = self.selected_item()
        if not item:
            self.set_status("select_first_link" if self.mode == "links" else "select_first_folder", color=THEME["danger"])
            return
        confirmed = messagebox.askyesno(self.t("confirm_delete_title"), self.t("confirm_delete_body").format(item["name"]), parent=self)
        if not confirmed:
            return
        collection = self.current_items()
        collection[:] = [entry for entry in collection if entry["id"] != item["id"]]
        self.save_current_collection()
        self.clear_form()
        self.set_status("link_deleted" if self.mode == "links" else "folder_deleted")
        self.refresh_view()

    def open_selected(self) -> None:
        item = self.selected_item()
        if not item:
            self.set_status("select_first_link" if self.mode == "links" else "select_first_folder", color=THEME["danger"])
            return
        if self.mode == "links":
            webbrowser.open(item["url"])
            return
        path = item["path"]
        if not path or not Path(path).exists():
            self.set_status("open_folder_failed", color=THEME["danger"])
            return
        os.startfile(path)

    def open_location_selected(self) -> None:
        item = self.selected_item()
        if not item:
            self.set_status("select_first_folder", color=THEME["danger"])
            return
        if self.mode == "links":
            return
        path = item["path"]
        if not path or not Path(path).exists():
            self.set_status("open_folder_failed", color=THEME["danger"])
            return
        subprocess.Popen(["explorer", f'/select,{path}'])

    def save_current(self) -> None:
        name = self.name_entry.get().strip()
        raw_path = self.path_entry.get().strip()
        category = self.category_entry.get().strip() or "__uncategorized__"
        note = self.notes_text.get("1.0", tk.END).strip()

        if self.mode == "links":
            if not name:
                self.set_status("enter_link_name", color=THEME["danger"])
                return
            if not raw_path:
                self.set_status("enter_link_path", color=THEME["danger"])
                return
            normalized_path = self._normalize_url(raw_path)
            if not normalized_path.startswith(("http://", "https://")):
                self.set_status("invalid_link_path", color=THEME["danger"])
                return
        else:
            if not name:
                self.set_status("enter_folder_name", color=THEME["danger"])
                return
            if not raw_path:
                self.set_status("enter_folder_path", color=THEME["danger"])
                return
            normalized_path = self._normalize_folder_path(raw_path)
            resource_path = Path(normalized_path)
            if not resource_path.exists():
                self.set_status("invalid_folder_path", color=THEME["danger"])
                return
            resource_kind = "folder" if resource_path.is_dir() else "file"

        collection = self.current_items()
        path_key = self.current_path_key()
        normalized = {
            "id": self.editing_id or str(uuid.uuid4()),
            "name": name,
            path_key: normalized_path,
            "category": category,
            "note": note,
            "favorite": False,
            "createdAt": datetime.now().astimezone().isoformat(),
        }
        if self.mode != "links":
            normalized["kind"] = resource_kind

        if self.editing_id:
            for index, item in enumerate(collection):
                if item["id"] == self.editing_id:
                    normalized["createdAt"] = item.get("createdAt") or normalized["createdAt"]
                    normalized["favorite"] = bool(item.get("favorite"))
                    collection[index] = normalized
                    break
            self.save_current_collection()
            self.clear_form()
            self.set_status("link_updated" if self.mode == "links" else "folder_updated")
        else:
            collection.insert(0, normalized)
            self.save_current_collection()
            self.clear_form()
            self.set_status("link_saved" if self.mode == "links" else "folder_saved")
        self.refresh_view()

    def export_current(self) -> None:
        default_name = "sites-backup.json" if self.mode == "links" else "folders-backup.json"
        path = filedialog.asksaveasfilename(
            parent=self,
            title=self.t("export"),
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        Path(path).write_text(json.dumps(self.current_items(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.set_status("backup_exported")

    def import_current(self) -> None:
        path = filedialog.askopenfilename(parent=self, title=self.t("import"), filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("Expected a list")
            normalized = [self._normalize_site(item) for item in raw] if self.mode == "links" else [self._normalize_folder(item) for item in raw]
            normalized = [item for item in normalized if item.get("name") and item.get(self.current_path_key())]
        except Exception:
            self.set_status("import_failed", color=THEME["danger"])
            return

        if self.mode == "links":
            self.sites = normalized
        else:
            self.folders = normalized
        self.save_current_collection()
        self.clear_form()
        self.set_status("backup_imported")
        self.refresh_view()


if __name__ == "__main__":
    try:
        app = ResourceHubApp()
        app.mainloop()
    except Exception:
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent
        log_path = base_dir / "resource_hub_error.log"
        details = traceback.format_exc()
        log_path.write_text(details, encoding="utf-8")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Resource Hub Error",
                "Python version failed to start.\n\n"
                f"Log file:\n{log_path}\n\n"
                f"{details[-1200:]}",
            )
            root.destroy()
        except Exception:
            pass
        raise SystemExit(1)
