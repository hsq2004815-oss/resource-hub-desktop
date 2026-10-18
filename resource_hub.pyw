import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageTk


def _enable_high_dpi_mode() -> None:
    if os.name != "nt":
        return
    try:
        per_monitor_v2 = ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(per_monitor_v2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_high_dpi_mode()

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    import pystray
    from pystray import Menu as TrayMenu
    from pystray import MenuItem as TrayMenuItem
except Exception as exc:
    base_dir = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    log_path = base_dir / "resource_hub_error.log"
    details = f"Failed to import tkinterdnd2 or pystray.\n\n{exc}\n"
    try:
        log_path.write_text(details, encoding="utf-8")
    except Exception:
        pass
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Resource Hub Error",
            "A required Python package is missing: tkinterdnd2 or pystray.\n\n"
            "Please run this app with the Python environment that already has dependencies installed.\n\n"
            f"Log file:\n{log_path}",
        )
        root.destroy()
    except Exception:
        pass
    raise SystemExit(1)


APP_MUTEX_NAME = "Local\\Mytools.ResourceHub.SingleInstance"
APP_WAKE_EVENT_NAME = "Local\\Mytools.ResourceHub.WakeEvent"
APP_HOTKEY_ID = 0xB123
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SPACE = 0x20
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
PM_NOREMOVE = 0x0000
WM_APP = 0x8000
APP_HOTKEY_STOP = WM_APP + 77
HOTKEY_MODIFIERS = (
    ("Ctrl", MOD_CONTROL),
    ("Alt", MOD_ALT),
    ("Shift", MOD_SHIFT),
    ("Win", MOD_WIN),
)
HOTKEY_MODIFIER_ALIASES = {
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "WIN": "Win",
    "WINDOWS": "Win",
    "SUPER": "Win",
}
HOTKEY_DISPLAY_TO_VK = {
    "Space": VK_SPACE,
    "Tab": 0x09,
    "Enter": 0x0D,
    "Esc": 0x1B,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "Minus": 0xBD,
    "Equals": 0xBB,
    "Comma": 0xBC,
    "Period": 0xBE,
    "Slash": 0xBF,
    "Semicolon": 0xBA,
    "Apostrophe": 0xDE,
    "LeftBracket": 0xDB,
    "RightBracket": 0xDD,
    "Backslash": 0xDC,
    "Backtick": 0xC0,
}
HOTKEY_KEY_ALIASES = {
    "SPACE": "Space",
    "TAB": "Tab",
    "RETURN": "Enter",
    "ENTER": "Enter",
    "ESC": "Esc",
    "ESCAPE": "Esc",
    "BACKSPACE": "Backspace",
    "BACKSPACEKEY": "Backspace",
    "DELETE": "Delete",
    "DEL": "Delete",
    "INSERT": "Insert",
    "INS": "Insert",
    "HOME": "Home",
    "END": "End",
    "PRIOR": "PageUp",
    "PAGEUP": "PageUp",
    "NEXT": "PageDown",
    "PAGEDOWN": "PageDown",
    "LEFT": "Left",
    "UP": "Up",
    "RIGHT": "Right",
    "DOWN": "Down",
    "MINUS": "Minus",
    "OEM_MINUS": "Minus",
    "EQUAL": "Equals",
    "EQUALS": "Equals",
    "OEM_PLUS": "Equals",
    "COMMA": "Comma",
    "OEM_COMMA": "Comma",
    "PERIOD": "Period",
    "OEM_PERIOD": "Period",
    "SLASH": "Slash",
    "QUESTION": "Slash",
    "OEM_2": "Slash",
    "SEMICOLON": "Semicolon",
    "OEM_1": "Semicolon",
    "APOSTROPHE": "Apostrophe",
    "QUOTERIGHT": "Apostrophe",
    "OEM_7": "Apostrophe",
    "BRACKETLEFT": "LeftBracket",
    "LEFTBRACKET": "LeftBracket",
    "OEM_4": "LeftBracket",
    "BRACKETRIGHT": "RightBracket",
    "RIGHTBRACKET": "RightBracket",
    "OEM_6": "RightBracket",
    "BACKSLASH": "Backslash",
    "OEM_5": "Backslash",
    "GRAVE": "Backtick",
    "ASCIITILDE": "Backtick",
    "QUOTELEFT": "Backtick",
    "OEM_3": "Backtick",
}
HOTKEY_MODIFIER_KEYSYMS = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Win_L", "Win_R", "Super_L", "Super_R"}
SETTINGS_WINDOW_ICON_FILE = "settings_icon.png"
APP_ICON_PNG_FILE = "DesktopShortcut.png"
APP_ICON_ICO_FILE = "DesktopShortcut.ico"
FALLBACK_ICON_ICO_FILE = "LinkHub.ico"
LANGUAGE_DISPLAY = {"zh": "简体中文", "en": "English"}
LANGUAGE_BY_DISPLAY = {value: key for key, value in LANGUAGE_DISPLAY.items()}
SETTINGS_DEFAULTS = {
    "language": "zh",
    "globalHotkeyEnabled": True,
    "globalHotkeyId": "Ctrl + Alt + Space",
    "launchAtStartup": False,
}
STARTUP_HIDDEN_ARG = "--startup-hidden"
WINDOW_FADE_DURATION_MS = 140
WINDOW_FADE_INTERVAL_MS = 16


def _normalize_hotkey_key_name(token: str) -> str | None:
    cleaned = str(token).strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in HOTKEY_MODIFIER_ALIASES:
        return None
    if upper.startswith("F") and upper[1:].isdigit():
        value = int(upper[1:])
        if 1 <= value <= 24:
            return f"F{value}"
    if len(cleaned) == 1:
        char = cleaned.upper()
        if char.isalpha() or char.isdigit():
            return char
    return HOTKEY_KEY_ALIASES.get(upper)


def parse_hotkey_id(hotkey_id: str) -> tuple[str, int, int] | None:
    modifiers = 0
    key_name = None
    for raw_token in str(hotkey_id).split("+"):
        token = raw_token.strip()
        if not token:
            continue
        modifier_name = HOTKEY_MODIFIER_ALIASES.get(token.upper())
        if modifier_name:
            for label, mask in HOTKEY_MODIFIERS:
                if label == modifier_name:
                    modifiers |= mask
                    break
            continue
        normalized_key = _normalize_hotkey_key_name(token)
        if not normalized_key or key_name is not None:
            return None
        key_name = normalized_key
    if not modifiers or not key_name:
        return None
    if key_name in HOTKEY_DISPLAY_TO_VK:
        vk = HOTKEY_DISPLAY_TO_VK[key_name]
    elif len(key_name) == 1 and key_name.isalpha():
        vk = ord(key_name)
    elif len(key_name) == 1 and key_name.isdigit():
        vk = ord(key_name)
    elif key_name.startswith("F") and key_name[1:].isdigit():
        vk = 0x70 + int(key_name[1:]) - 1
    else:
        return None
    labels = [label for label, mask in HOTKEY_MODIFIERS if modifiers & mask]
    return (" + ".join([*labels, key_name]), modifiers, vk)


def first_existing_path(*candidates) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None

if os.name == "nt":
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetKeyState.argtypes = [ctypes.c_int]
    user32.GetKeyState.restype = ctypes.c_short
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, ctypes.c_wchar_p]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, ctypes.c_wchar_p]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
else:
    user32 = None
    kernel32 = None


THEME = {
    "bg": "#eef2f7",
    "panel": "#f8fbff",
    "panel_strong": "#ffffff",
    "panel_alt": "#f2f6fc",
    "hero": "#e9f1ff",
    "border": "#d9e2ef",
    "accent": "#2f6fed",
    "accent_soft": "#e5efff",
    "accent_muted": "#f0f5ff",
    "ink": "#162033",
    "muted": "#5f6b7d",
    "success": "#23724f",
    "danger": "#c14943",
}

FONTS = {
    "title": ("Microsoft YaHei UI", 24, "bold"),
    "section": ("Microsoft YaHei UI", 16, "bold"),
    "body": ("Microsoft YaHei UI", 10),
    "body_bold": ("Microsoft YaHei UI", 10, "bold"),
    "small": ("Microsoft YaHei UI", 9),
    "small_bold": ("Microsoft YaHei UI", 9, "bold"),
    "stat": ("Microsoft YaHei UI", 22, "bold"),
}


STRINGS = {
    "zh": {
        "window_title": "常用资源工具",
        "current_mode": "当前模块",
        "mode_links_label": "网站管理",
        "mode_folders_label": "资源管理",
        "subtitle_links": "把常用网站放在同一个桌面工具里统一管理，列表会直接显示加入时间。",
        "subtitle_folders": "把常用文件和文件夹放在同一个桌面工具里统一管理，列表会直接显示加入时间。",
        "kicker": "轻量桌面资源中枢",
        "chip_launch": "快速启动",
        "chip_favorite": "收藏置顶",
        "chip_drag": "拖拽收集",
        "chip_health": "路径检测",
        "settings_button": "设置",
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
        "form_tip_links": "适合放工作站点、参考链接和常用网页入口。",
        "form_tip_folders": "适合放常用文件、文件夹和本地资料入口。",
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
        "favorites_only": "只看收藏",
        "show_all_items": "显示全部",
        "favorites_only_suffix": "仅收藏",
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
        "copy_url": "复制网址",
        "copy_path": "复制路径",
        "copied_url": "网址已复制到剪贴板。",
        "copied_path": "路径已复制到剪贴板。",
        "tray_toggle": "显示 / 隐藏",
        "tray_exit": "退出程序",
        "settings_title": "设置",
        "settings_language": "界面语言",
        "settings_hotkey_enabled": "启用全局快捷键",
        "settings_hotkey": "快捷键组合",
        "settings_hotkey_record": "录制快捷键",
        "settings_hotkey_recording": "请按下新的快捷键组合，按 Esc 取消。",
        "settings_hotkey_hint": "支持 Ctrl / Alt / Shift / Win 加任意常用按键。",
        "settings_startup": "开机启动",
        "settings_startup_note": "启动后进入托盘",
        "settings_save": "保存",
        "settings_cancel": "取消",
        "settings_saved": "设置已保存。",
        "hotkey_in_use": "快捷键 {0} 已被其他程序占用。",
        "hotkey_invalid": "快捷键必须至少包含一个修饰键和一个普通按键。",
        "hotkey_runtime_unavailable": "快捷键 {0} 当前不可用，可能已被其他程序占用。",
        "startup_sync_failed": "开机启动设置失败，请检查系统权限。",
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
        "duplicate_link_path": "这个网址已经保存过了。",
        "link_saved": "链接已保存。",
        "link_updated": "链接已更新。",
        "link_deleted": "链接已删除。",
        "editing_link": "正在编辑链接：{0}",
        "enter_folder_name": "请先填写资源名称。",
        "enter_folder_path": "请先填写文件或文件夹路径。",
        "invalid_folder_path": "文件或文件夹路径不存在。",
        "duplicate_folder_path": "这个文件或文件夹路径已经保存过了。",
        "folder_saved": "资源已保存。",
        "folder_updated": "资源已更新。",
        "folder_deleted": "资源已删除。",
        "editing_folder": "正在编辑资源：{0}",
        "confirm_delete_title": "删除确认",
        "confirm_delete_body": "确定删除“{0}”吗？",
        "import_failed": "导入失败，请检查 JSON 文件。",
        "backup_exported": "备份文件已导出。",
        "backup_imported": "备份导入成功。",
        "backup_imported_skipped": "备份导入成功，保留 {0} 条记录，跳过 {1} 条重复项。",
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
        "kicker": "Lightweight desktop launchpad",
        "chip_launch": "Quick Launch",
        "chip_favorite": "Favorites First",
        "chip_drag": "Drag and Drop",
        "chip_health": "Path Check",
        "settings_button": "Settings",
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
        "form_tip_links": "Best for daily shortcuts, work portals, and reference links.",
        "form_tip_folders": "Best for your active files, folders, and local workspaces.",
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
        "favorites_only": "Favorites Only",
        "show_all_items": "Show All",
        "favorites_only_suffix": "Favorites only",
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
        "copy_url": "Copy URL",
        "copy_path": "Copy Path",
        "copied_url": "URL copied to the clipboard.",
        "copied_path": "Path copied to the clipboard.",
        "tray_toggle": "Show / Hide",
        "tray_exit": "Exit",
        "settings_title": "Settings",
        "settings_language": "Language",
        "settings_hotkey_enabled": "Enable global hotkey",
        "settings_hotkey": "Hotkey",
        "settings_hotkey_record": "Record hotkey",
        "settings_hotkey_recording": "Press a new hotkey combination. Press Esc to cancel.",
        "settings_hotkey_hint": "Supports Ctrl / Alt / Shift / Win plus a standard key.",
        "settings_startup": "Launch at Windows startup",
        "settings_startup_note": "Start in tray after sign-in",
        "settings_save": "Save",
        "settings_cancel": "Cancel",
        "settings_saved": "Settings saved.",
        "hotkey_in_use": "The hotkey {0} is already in use.",
        "hotkey_invalid": "The hotkey must include at least one modifier and one standard key.",
        "hotkey_runtime_unavailable": "The hotkey {0} is currently unavailable because another app is using it.",
        "startup_sync_failed": "Could not update the Windows startup shortcut.",
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
        "duplicate_link_path": "This URL is already saved.",
        "link_saved": "Link saved.",
        "link_updated": "Link updated.",
        "link_deleted": "Link deleted.",
        "editing_link": "Editing link: {0}",
        "enter_folder_name": "Please enter a resource name.",
        "enter_folder_path": "Please enter a file or folder path.",
        "invalid_folder_path": "The file or folder path does not exist.",
        "duplicate_folder_path": "This file or folder path is already saved.",
        "folder_saved": "Resource saved.",
        "folder_updated": "Resource updated.",
        "folder_deleted": "Resource deleted.",
        "editing_folder": "Editing resource: {0}",
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_body": "Delete '{0}'?",
        "import_failed": "Import failed. Please check the JSON file.",
        "backup_exported": "Backup exported.",
        "backup_imported": "Backup imported.",
        "backup_imported_skipped": "Backup imported. Kept {0} items and skipped {1} duplicates.",
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


class SingleInstanceGuard:
    def __init__(self, mutex_name: str) -> None:
        self.mutex_name = mutex_name
        self.handle = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        self.handle = kernel32.CreateMutexW(None, False, self.mutex_name)
        if not self.handle:
            return True
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS

    def release(self) -> None:
        if os.name != "nt" or not self.handle:
            return
        try:
            kernel32.CloseHandle(self.handle)
        except Exception:
            pass
        self.handle = None


def signal_running_instance(timeout_seconds: float = 2.0) -> bool:
    if os.name != "nt":
        return False
    handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, APP_WAKE_EVENT_NAME)
    if not handle:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline and not handle:
            time.sleep(0.1)
            handle = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, APP_WAKE_EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)


class GlobalHotkeyListener:
    def __init__(self, hotkey_queue: "queue.SimpleQueue[str]", hotkey_id: str) -> None:
        self.hotkey_queue = hotkey_queue
        self.hotkey_id = hotkey_id
        self.ready_event = threading.Event()
        self.thread = None
        self.thread_id = None
        self.registered = False
        self.active_label = hotkey_id

    def start(self) -> bool:
        if os.name != "nt":
            return False
        self.thread = threading.Thread(target=self._run, name="ResourceHubHotkey", daemon=True)
        self.thread.start()
        self.ready_event.wait(2.0)
        return self.registered

    def _run(self) -> None:
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        self.thread_id = kernel32.GetCurrentThreadId()
        parsed = parse_hotkey_id(self.hotkey_id)
        if parsed:
            _label, modifiers, vk = parsed
            self.registered = bool(user32.RegisterHotKey(None, APP_HOTKEY_ID, modifiers, vk))
        self.ready_event.set()
        if not self.registered:
            return
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == APP_HOTKEY_ID:
                    self.hotkey_queue.put("toggle")
                elif msg.message == APP_HOTKEY_STOP:
                    break
        finally:
            try:
                user32.UnregisterHotKey(None, APP_HOTKEY_ID)
            except Exception:
                pass
            self.registered = False

    def stop(self) -> None:
        if os.name != "nt":
            return
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, APP_HOTKEY_STOP, 0, 0)
        if self.thread:
            self.thread.join(timeout=2.0)


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text="",
        command=None,
        bg="#ffffff",
        fg="#000000",
        hover_bg=None,
        hover_fg=None,
        disabled_bg="#e5e7eb",
        disabled_fg="#94a3b8",
        border_color=None,
        border_width=1,
        radius=16,
        width=112,
        height=40,
        font=None,
        cursor="hand2",
    ):
        self.parent_bg = parent.cget("bg")
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=self.parent_bg,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor=cursor,
        )
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg or bg
        self._hover_fg = hover_fg or fg
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        self._border_color = border_color or bg
        self._border_width = border_width
        self._radius = radius
        self._font = font or FONTS["body_bold"]
        self._state = "normal"
        self._hovered = False
        self._shape_id = None
        self._text_id = None
        self._image_ref = None
        self.bind("<Configure>", self._on_resize)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _hex_to_rgba(self, value: str, alpha: int = 255):
        rgb = self.winfo_rgb(value)
        return tuple(channel // 256 for channel in rgb) + (alpha,)

    def _build_button_image(self, width: int, height: int, fill: str, border: str, border_width: int, radius: int):
        scale = 4
        outer_w = max(width * scale, 8)
        outer_h = max(height * scale, 8)
        border_px = max(border_width * scale, 0)
        radius_px = max(1, min(radius * scale, outer_w // 2, outer_h // 2))
        image = Image.new("RGBA", (outer_w, outer_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        fill_rgba = self._hex_to_rgba(fill)
        border_rgba = self._hex_to_rgba(border) if border_width > 0 else fill_rgba

        draw.rounded_rectangle(
            (0, 0, outer_w - 1, outer_h - 1),
            radius=radius_px,
            fill=border_rgba,
        )

        inset = border_px
        if outer_w - inset * 2 > 2 and outer_h - inset * 2 > 2:
            draw.rounded_rectangle(
                (inset, inset, outer_w - inset - 1, outer_h - inset - 1),
                radius=max(radius_px - inset, 1),
                fill=fill_rgba,
            )

        return ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS))

    def _current_colors(self):
        if self._state == "disabled":
            return self._disabled_bg, self._disabled_fg, self._disabled_bg
        if self._hovered:
            return self._hover_bg, self._hover_fg, self._border_color
        return self._bg, self._fg, self._border_color

    def _draw(self):
        self.delete("all")
        width = max(int(self.winfo_width() or self.cget("width")), 10)
        height = max(int(self.winfo_height() or self.cget("height")), 10)
        fill, text_color, border = self._current_colors()
        self._image_ref = self._build_button_image(width, height, fill, border, self._border_width, self._radius)
        self.create_image(width / 2, height / 2, image=self._image_ref)
        self._text_id = self.create_text(
            width / 2,
            height / 2,
            text=self._text,
            fill=text_color,
            font=self._font,
        )

    def _on_resize(self, _event=None):
        self._draw()

    def _on_enter(self, _event=None):
        if self._state != "disabled":
            self._hovered = True
            self._draw()

    def _on_leave(self, _event=None):
        if self._hovered:
            self._hovered = False
            self._draw()

    def _on_click(self, _event=None):
        if self._state != "disabled" and self._command:
            self._command()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        width = kwargs.pop("width", None)
        height = kwargs.pop("height", None)
        text = kwargs.pop("text", None)
        command = kwargs.pop("command", None)
        bg = kwargs.pop("bg", None)
        fg = kwargs.pop("fg", None)
        hover_bg = kwargs.pop("activebackground", None)
        hover_fg = kwargs.pop("activeforeground", None)
        border_color = kwargs.pop("highlightbackground", None)
        border_width = kwargs.pop("bd", kwargs.pop("borderwidth", None))
        state = kwargs.pop("state", None)
        font = kwargs.pop("font", None)
        cursor = kwargs.pop("cursor", None)
        if width is not None:
            super().configure(width=width)
        if height is not None:
            super().configure(height=height)
        if text is not None:
            self._text = text
        if command is not None:
            self._command = command
        if bg is not None:
            self._bg = bg
        if fg is not None:
            self._fg = fg
        if hover_bg is not None:
            self._hover_bg = hover_bg
        if hover_fg is not None:
            self._hover_fg = hover_fg
        if border_color is not None:
            self._border_color = border_color
        if border_width is not None:
            self._border_width = max(int(border_width), 0)
        if state is not None:
            self._state = state
            super().configure(cursor="arrow" if state == "disabled" else (cursor or "hand2"))
        elif cursor is not None:
            super().configure(cursor=cursor)
        if font is not None:
            self._font = font
        if kwargs:
            super().configure(**kwargs)
        self._draw()

    config = configure


class ResourceHubApp(TkinterDnD.Tk):
    def __init__(self, instance_guard: SingleInstanceGuard | None = None) -> None:
        super().__init__()
        if getattr(sys, "frozen", False):
            self.bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.bundle_dir = Path(__file__).resolve().parent
            self.base_dir = self.bundle_dir
        self.site_path = self.base_dir / "sites.json"
        self.folder_path = self.base_dir / "folders.json"
        self.settings_path = self.base_dir / "settings.json"
        self.display_icon_path = first_existing_path(
            self.base_dir / APP_ICON_PNG_FILE,
            self.base_dir / APP_ICON_ICO_FILE,
            self.base_dir / FALLBACK_ICON_ICO_FILE,
            self.bundle_dir / APP_ICON_PNG_FILE,
            self.bundle_dir / APP_ICON_ICO_FILE,
            self.bundle_dir / FALLBACK_ICON_ICO_FILE,
        )
        self.icon_path = first_existing_path(
            self.base_dir / APP_ICON_ICO_FILE,
            self.base_dir / FALLBACK_ICON_ICO_FILE,
            self.bundle_dir / APP_ICON_ICO_FILE,
            self.bundle_dir / FALLBACK_ICON_ICO_FILE,
        )
        self.app_id = "Mytools.ResourceHub.Python"
        self.settings = self._load_settings()
        self.language = self.settings["language"]
        self.mode = "links"
        self.editing_id = None
        self.instance_guard = instance_guard
        self.window_handle = None
        self._wake_event_handle = None
        self._hotkey_queue = queue.SimpleQueue()
        self._hotkey_listener = None
        self._hotkey_registered = False
        self._message_poll_job = None
        self._tray_icon = None
        self._exiting = False
        self._restore_state = "normal"
        self._startup_hidden = STARTUP_HIDDEN_ARG in sys.argv[1:]
        self._window_alpha = 1.0
        self._window_alpha_supported = None
        self._window_animation_job = None
        self._window_animation_target = None
        self.window_icon_image = None
        self.settings_window_icon_path = first_existing_path(
            self.base_dir / SETTINGS_WINDOW_ICON_FILE,
            self.bundle_dir / SETTINGS_WINDOW_ICON_FILE,
        ) or (self.base_dir / SETTINGS_WINDOW_ICON_FILE)
        self.settings_window_icon_image = None
        self.settings_window = None
        self._settings_hotkey_capture_active = False
        self.settings_language_var = None
        self.settings_hotkey_var = None
        self.settings_hotkey_enabled_var = None
        self.settings_startup_var = None
        self.settings_header_label = None
        self.settings_hotkey_enabled_check = None
        self.settings_hotkey_label = None
        self.settings_hotkey_entry = None
        self.settings_hotkey_record_button = None
        self.settings_hotkey_hint_label = None
        self.settings_language_label = None
        self.settings_language_combo = None
        self.settings_startup_check = None
        self.settings_startup_note_label = None
        self.settings_save_button = None
        self.settings_cancel_button = None
        self.link_filter_value = "__all__"
        self.folder_filter_value = "__all__"
        self.link_search_value = ""
        self.folder_search_value = ""
        self.link_favorites_only = False
        self.folder_favorites_only = False
        self.sites = []
        self.folders = []
        self._build_window()
        self._build_styles()
        self._build_ui()
        self._setup_drop_targets()
        self._load_all_data()
        self.apply_language()
        self.refresh_view()
        self._setup_platform_features()
        if self._startup_hidden and self._tray_icon:
            self.hide_to_tray(animate=False)

    def t(self, key: str) -> str:
        return STRINGS[self.language].get(key, key)

    def _build_window(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)
        except Exception:
            pass
        self.title(self.t("window_title"))
        self._apply_tk_scaling()
        self.geometry("1280x820")
        self.minsize(1180, 760)
        self.configure(bg=THEME["bg"])
        self.option_add("*Font", FONTS["body"])
        self._apply_main_window_icon()

    def _apply_main_window_icon(self) -> None:
        if self.icon_path and self.icon_path.exists():
            try:
                self.iconbitmap(self.icon_path)
                return
            except Exception:
                pass
        if self.display_icon_path and self.display_icon_path.exists():
            try:
                image = Image.open(self.display_icon_path).convert("RGBA")
                self.window_icon_image = ImageTk.PhotoImage(image)
                self.iconphoto(False, self.window_icon_image)
            except Exception:
                pass

    def _apply_tk_scaling(self) -> None:
        try:
            dpi = 96
            if os.name == "nt":
                try:
                    dpi = ctypes.windll.user32.GetDpiForSystem()
                except Exception:
                    pass
            self.tk.call("tk", "scaling", max(dpi / 72.0, 1.0))
        except Exception:
            pass

    def _setup_platform_features(self) -> None:
        if os.name != "nt":
            return
        try:
            self.update_idletasks()
            self.window_handle = self.winfo_id()
            self._create_wake_event()
            self._create_tray_icon()
            self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
            self._start_hotkey_listener()
            self._start_message_polling()
        except Exception as exc:
            self._log_platform_error(exc)

    def _log_platform_error(self, exc: Exception) -> None:
        try:
            log_path = self.base_dir / "resource_hub_error.log"
            message = f"[platform] {datetime.now().isoformat()}\n{type(exc).__name__}: {exc}\n{traceback.format_exc()}\n\n"
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(message)
        except Exception:
            pass

    def _selected_hotkey_id(self) -> str:
        hotkey_id = self.settings.get("globalHotkeyId", SETTINGS_DEFAULTS["globalHotkeyId"])
        parsed = parse_hotkey_id(hotkey_id)
        return parsed[0] if parsed else SETTINGS_DEFAULTS["globalHotkeyId"]

    def _selected_hotkey_label(self) -> str:
        return self._selected_hotkey_id()

    def _start_hotkey_listener(self) -> None:
        if os.name != "nt" or self._hotkey_listener is not None:
            return
        if not self.settings.get("globalHotkeyEnabled", True):
            self._hotkey_registered = False
            return
        hotkey_id = self._selected_hotkey_id()
        self._hotkey_listener = GlobalHotkeyListener(self._hotkey_queue, hotkey_id)
        self._hotkey_registered = self._hotkey_listener.start()
        if not self._hotkey_registered:
            self.set_status("hotkey_runtime_unavailable", args=[hotkey_id], color=THEME["danger"])

    def _unregister_global_hotkey(self) -> None:
        if os.name != "nt":
            return
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        self._hotkey_registered = False

    def _is_hotkey_available(self, hotkey_id: str) -> bool:
        if os.name != "nt":
            return True
        parsed = parse_hotkey_id(hotkey_id)
        if not parsed:
            return False
        if self._hotkey_registered and self._hotkey_listener and self._hotkey_listener.active_label == hotkey_id:
            return True
        _label, modifiers, vk = parsed
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        test_id = APP_HOTKEY_ID + 91
        ok = bool(user32.RegisterHotKey(None, test_id, modifiers, vk))
        if ok:
            user32.UnregisterHotKey(None, test_id)
        return ok

    def _format_hotkey_from_parts(self, modifiers: int, key_name: str) -> str:
        labels = [label for label, mask in HOTKEY_MODIFIERS if modifiers & mask]
        return " + ".join([*labels, key_name])

    def _modifier_mask_from_keyboard(self) -> int:
        if os.name != "nt":
            return 0
        modifiers = 0
        if user32.GetKeyState(VK_CONTROL) & 0x8000:
            modifiers |= MOD_CONTROL
        if user32.GetKeyState(VK_MENU) & 0x8000:
            modifiers |= MOD_ALT
        if user32.GetKeyState(VK_SHIFT) & 0x8000:
            modifiers |= MOD_SHIFT
        if (user32.GetKeyState(VK_LWIN) & 0x8000) or (user32.GetKeyState(VK_RWIN) & 0x8000):
            modifiers |= MOD_WIN
        return modifiers

    def _hotkey_key_name_from_event(self, event) -> str | None:
        keysym = str(getattr(event, "keysym", "") or "")
        if not keysym or keysym in HOTKEY_MODIFIER_KEYSYMS:
            return None
        return _normalize_hotkey_key_name(keysym)

    def _apply_settings_window_icon(self, window: tk.Toplevel) -> None:
        if not self.settings_window_icon_path.exists():
            return
        try:
            if self.settings_window_icon_image is None:
                self.settings_window_icon_image = tk.PhotoImage(file=str(self.settings_window_icon_path))
            window.iconphoto(False, self.settings_window_icon_image)
        except Exception:
            pass

    def _update_hotkey_capture_ui(self) -> None:
        if self.settings_hotkey_record_button:
            text = self.t("settings_hotkey_recording") if self._settings_hotkey_capture_active else self.t("settings_hotkey_record")
            self.settings_hotkey_record_button.config(text=text)
        if self.settings_hotkey_hint_label:
            text = self.t("settings_hotkey_recording") if self._settings_hotkey_capture_active else self.t("settings_hotkey_hint")
            color = THEME["accent"] if self._settings_hotkey_capture_active else THEME["muted"]
            self.settings_hotkey_hint_label.config(text=text, fg=color)

    def _begin_hotkey_capture(self) -> None:
        if not self.settings_window or not self.settings_window.winfo_exists():
            return
        if not self.settings_hotkey_enabled_var or not self.settings_hotkey_enabled_var.get():
            return
        self._settings_hotkey_capture_active = True
        self.settings_window.bind("<KeyPress>", self._handle_settings_hotkey_capture)
        self._update_hotkey_capture_ui()
        self.settings_window.focus_force()

    def _end_hotkey_capture(self) -> None:
        self._settings_hotkey_capture_active = False
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.bind("<KeyPress>", "")
        self._update_hotkey_capture_ui()

    def _handle_settings_hotkey_capture(self, event):
        if not self._settings_hotkey_capture_active:
            return None
        keysym = str(getattr(event, "keysym", "") or "")
        if keysym == "Escape":
            self._end_hotkey_capture()
            return "break"
        key_name = self._hotkey_key_name_from_event(event)
        if not key_name:
            return "break"
        modifiers = self._modifier_mask_from_keyboard()
        if not modifiers:
            if self.settings_hotkey_hint_label:
                self.settings_hotkey_hint_label.config(text=self.t("hotkey_invalid"), fg=THEME["danger"])
            return "break"
        self.settings_hotkey_var.set(self._format_hotkey_from_parts(modifiers, key_name))
        self._end_hotkey_capture()
        return "break"

    def _apply_hotkey_settings(self) -> None:
        self._unregister_global_hotkey()
        if self.settings.get("globalHotkeyEnabled", True):
            self._start_hotkey_listener()

    def _startup_shortcut_path(self) -> Path:
        startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return startup_dir / "Resource Hub.lnk"

    def _escape_powershell_value(self, value: str) -> str:
        return str(value).replace("'", "''")

    def _startup_shortcut_command(self):
        fallback_icon = first_existing_path(
            self.base_dir / APP_ICON_ICO_FILE,
            self.base_dir / FALLBACK_ICON_ICO_FILE,
            self.bundle_dir / APP_ICON_ICO_FILE,
            self.bundle_dir / FALLBACK_ICON_ICO_FILE,
        )
        icon_path = str(fallback_icon or (self.base_dir / FALLBACK_ICON_ICO_FILE))
        if getattr(sys, "frozen", False):
            return {
                "target": str(Path(sys.executable).resolve()),
                "arguments": STARTUP_HIDDEN_ARG,
                "working_directory": str(Path(sys.executable).resolve().parent),
                "icon": icon_path,
                "description": "Resource Hub Desktop",
            }
        launcher_path = self.base_dir / "start-resource-hub-python.vbs"
        return {
            "target": str(launcher_path.resolve()),
            "arguments": STARTUP_HIDDEN_ARG,
            "working_directory": str(self.base_dir),
            "icon": icon_path,
            "description": "Resource Hub Desktop",
        }

    def _set_launch_at_startup(self, enabled: bool) -> bool:
        shortcut_path = self._startup_shortcut_path()
        if not enabled:
            try:
                if shortcut_path.exists():
                    shortcut_path.unlink()
                return True
            except Exception:
                return False
        shortcut_info = self._startup_shortcut_command()
        try:
            shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return False
        powershell_script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{self._escape_powershell_value(shortcut_path)}')
$shortcut.TargetPath = '{self._escape_powershell_value(shortcut_info["target"])}'
$shortcut.Arguments = '{self._escape_powershell_value(shortcut_info["arguments"])}'
$shortcut.WorkingDirectory = '{self._escape_powershell_value(shortcut_info["working_directory"])}'
$shortcut.IconLocation = '{self._escape_powershell_value(shortcut_info["icon"])},0'
$shortcut.WindowStyle = 1
$shortcut.Description = '{self._escape_powershell_value(shortcut_info["description"])}'
$shortcut.Save()
"""
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except Exception:
            return False

    def _create_wake_event(self) -> None:
        if os.name != "nt" or self._wake_event_handle:
            return
        self._wake_event_handle = kernel32.CreateEventW(None, False, False, APP_WAKE_EVENT_NAME)

    def _close_wake_event(self) -> None:
        if os.name != "nt" or not self._wake_event_handle:
            return
        try:
            kernel32.CloseHandle(self._wake_event_handle)
        except Exception:
            pass
        self._wake_event_handle = None

    def _start_message_polling(self) -> None:
        if os.name != "nt":
            return
        if self._message_poll_job:
            try:
                self.after_cancel(self._message_poll_job)
            except Exception:
                pass
        self._message_poll_job = self.after(80, self._poll_windows_messages)

    def _poll_windows_messages(self) -> None:
        self._message_poll_job = None
        if self._exiting or os.name != "nt":
            return
        try:
            while True:
                try:
                    action = self._hotkey_queue.get_nowait()
                except queue.Empty:
                    break
                if action == "toggle":
                    self.toggle_window_visibility()
            if self._wake_event_handle and kernel32.WaitForSingleObject(self._wake_event_handle, 0) == WAIT_OBJECT_0:
                self.show_window()
        except Exception as exc:
            self._log_platform_error(exc)
        finally:
            if not self._exiting:
                self._message_poll_job = self.after(80, self._poll_windows_messages)

    def _load_tray_icon_image(self) -> Image.Image:
        for candidate in (
            self.display_icon_path,
            self.base_dir / APP_ICON_PNG_FILE,
            self.base_dir / APP_ICON_ICO_FILE,
            self.base_dir / FALLBACK_ICON_ICO_FILE,
            self.bundle_dir / APP_ICON_PNG_FILE,
            self.bundle_dir / APP_ICON_ICO_FILE,
            self.bundle_dir / FALLBACK_ICON_ICO_FILE,
        ):
            try:
                if candidate and Path(candidate).exists():
                    return Image.open(candidate).convert("RGBA")
            except Exception:
                continue
        image = Image.new("RGBA", (64, 64), THEME["accent"])
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 63, 63), radius=16, fill=THEME["accent"])
        draw.text((18, 18), "R", fill="white")
        return image

    def _create_tray_menu(self):
        return TrayMenu(
            TrayMenuItem(self.t("tray_toggle"), self._handle_tray_toggle, default=True),
            TrayMenuItem(self.t("tray_exit"), self._handle_tray_exit),
        )

    def _create_tray_icon(self) -> None:
        if self._tray_icon is not None:
            return
        image = self._load_tray_icon_image()
        self._tray_icon = pystray.Icon(
            "ResourceHubDesktop",
            image,
            self.t("window_title"),
            self._create_tray_menu(),
        )
        self._tray_icon.run_detached()

    def _refresh_tray_icon(self) -> None:
        if not self._tray_icon:
            return
        try:
            self._tray_icon.title = self.t("window_title")
            self._tray_icon.menu = self._create_tray_menu()
            self._tray_icon.update_menu()
        except Exception:
            pass

    def _handle_tray_toggle(self, _icon=None, _item=None) -> None:
        self.after(0, self.toggle_window_visibility)

    def _handle_tray_exit(self, _icon=None, _item=None) -> None:
        self.after(0, self.exit_application)

    def _remember_restore_state(self) -> None:
        current_state = str(self.state())
        if current_state in {"normal", "zoomed"}:
            self._restore_state = current_state

    def _is_window_open(self) -> bool:
        return str(self.state()) not in {"withdrawn", "iconic"}

    def _set_window_alpha(self, value: float) -> bool:
        if self._window_alpha_supported is False:
            self._window_alpha = 1.0
            return False
        clipped = max(0.0, min(float(value), 1.0))
        try:
            self.attributes("-alpha", clipped)
            self._window_alpha = clipped
            self._window_alpha_supported = True
            return True
        except Exception:
            self._window_alpha_supported = False
            self._window_alpha = 1.0
            return False

    def _cancel_window_animation(self, reset_target: bool = True) -> None:
        if self._window_animation_job:
            try:
                self.after_cancel(self._window_animation_job)
            except Exception:
                pass
            self._window_animation_job = None
        if reset_target:
            self._window_animation_target = None

    def _animate_window_alpha(self, end_alpha: float, on_complete=None) -> bool:
        if self._window_alpha_supported is False:
            if on_complete:
                on_complete()
            return False
        self._cancel_window_animation(reset_target=False)
        start_alpha = self._window_alpha
        target_alpha = max(0.0, min(float(end_alpha), 1.0))
        if abs(start_alpha - target_alpha) < 0.02:
            self._set_window_alpha(target_alpha)
            if on_complete:
                on_complete()
            return True

        started_at = time.perf_counter()
        duration_seconds = WINDOW_FADE_DURATION_MS / 1000.0

        def step() -> None:
            elapsed = time.perf_counter() - started_at
            progress = min(elapsed / duration_seconds, 1.0)
            eased = 1.0 - ((1.0 - progress) ** 3)
            current_alpha = start_alpha + ((target_alpha - start_alpha) * eased)
            if not self._set_window_alpha(current_alpha):
                self._window_animation_job = None
                if on_complete:
                    on_complete()
                return
            if progress >= 1.0:
                self._window_animation_job = None
                self._set_window_alpha(target_alpha)
                if on_complete:
                    on_complete()
                return
            self._window_animation_job = self.after(WINDOW_FADE_INTERVAL_MS, step)

        step()
        return True

    def toggle_window_visibility(self) -> None:
        if self._window_animation_target == "hide":
            self.show_window()
            return
        if self._window_animation_target == "show":
            self.hide_to_tray()
            return
        if str(self.state()) in {"withdrawn", "iconic"}:
            self.show_window()
        else:
            self.hide_to_tray()

    def hide_to_tray(self, animate: bool = True) -> None:
        if self._exiting:
            return
        if not self._tray_icon:
            self.destroy()
            return
        self._remember_restore_state()
        self._cancel_window_animation(reset_target=False)

        def finish_hide() -> None:
            self._window_animation_target = None
            self.withdraw()
            self._refresh_tray_icon()

        self._window_animation_target = "hide"
        if animate and str(self.state()) not in {"withdrawn", "iconic"} and self._set_window_alpha(self._window_alpha):
            self._animate_window_alpha(0.0, on_complete=finish_hide)
            return
        finish_hide()

    def show_window(self) -> None:
        if self._exiting:
            return
        self._cancel_window_animation(reset_target=False)
        self._window_animation_target = "show"
        try:
            current_state = str(self.state())
            if current_state in {"withdrawn", "iconic"}:
                self._set_window_alpha(0.0)
            else:
                self._set_window_alpha(max(self._window_alpha, 0.12))
            if current_state == "withdrawn":
                self.deiconify()
            elif current_state == "iconic":
                self.deiconify()
            if self._restore_state == "zoomed":
                try:
                    self.state("zoomed")
                except Exception:
                    self.state("normal")
            else:
                self.state("normal")
            self.update_idletasks()
            try:
                self.update()
            except Exception:
                pass
            self.lift()
            try:
                self.attributes("-topmost", True)
                self.after(150, lambda: self.attributes("-topmost", False))
            except Exception:
                pass
            if os.name == "nt" and self.window_handle:
                try:
                    user32.ShowWindow(self.window_handle, SW_RESTORE)
                    user32.SetForegroundWindow(self.window_handle)
                except Exception:
                    pass
            if not self._animate_window_alpha(1.0, on_complete=lambda: setattr(self, "_window_animation_target", None)):
                self._window_animation_target = None
            self.after(120, lambda: self.search_entry.focus_set())
        finally:
            self._refresh_tray_icon()

    def exit_application(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        self._cancel_window_animation()
        if self._message_poll_job:
            try:
                self.after_cancel(self._message_poll_job)
            except Exception:
                pass
            self._message_poll_job = None
        self._unregister_global_hotkey()
        self._close_wake_event()
        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass
        self._tray_icon = None
        try:
            if self.instance_guard:
                self.instance_guard.release()
        except Exception:
            pass
        self.destroy()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Hub.Treeview",
            background=THEME["panel_strong"],
            fieldbackground=THEME["panel_strong"],
            foreground=THEME["ink"],
            rowheight=34,
            borderwidth=0,
        )
        style.configure(
            "Hub.Treeview.Heading",
            background=THEME["panel_alt"],
            foreground=THEME["ink"],
            relief="flat",
            font=FONTS["small_bold"],
            padding=(10, 10),
        )
        style.map("Hub.Treeview", background=[("selected", THEME["accent_soft"])], foreground=[("selected", THEME["ink"])])
        style.configure("Hub.TCombobox", fieldbackground=THEME["panel_strong"], background=THEME["panel_strong"], bordercolor=THEME["border"])

    def open_settings_window(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self)
        window.title(self.t("settings_title"))
        window.transient(self)
        window.grab_set()
        window.resizable(False, False)
        window.configure(bg=THEME["bg"])
        window.geometry("500x500")
        window.minsize(500, 500)
        self.settings_window = window
        window.protocol("WM_DELETE_WINDOW", self.close_settings_window)
        self._apply_settings_window_icon(window)

        footer_shell = self._panel(window)
        footer_shell.pack(side="bottom", fill="x", padx=16, pady=(0, 16))

        shell = self._panel(window)
        shell.pack(side="top", fill="both", expand=True, padx=16, pady=(16, 8))
        shell.grid_columnconfigure(0, weight=1)

        self.settings_header_label = tk.Label(shell, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["section"], anchor="w")
        self.settings_header_label.grid(row=0, column=0, padx=20, pady=(18, 14), sticky="w")

        self.settings_hotkey_enabled_var = tk.BooleanVar(value=bool(self.settings.get("globalHotkeyEnabled", True)))
        self.settings_hotkey_var = tk.StringVar(value=self._selected_hotkey_id())
        self.settings_language_var = tk.StringVar(value=LANGUAGE_DISPLAY.get(self.settings.get("language", "zh"), "简体中文"))
        self.settings_startup_var = tk.BooleanVar(value=bool(self.settings.get("launchAtStartup", False)))

        self.settings_hotkey_enabled_check = tk.Checkbutton(
            shell,
            bg=THEME["panel"],
            fg=THEME["ink"],
            selectcolor=THEME["panel_strong"],
            activebackground=THEME["panel"],
            activeforeground=THEME["ink"],
            font=FONTS["body_bold"],
            variable=self.settings_hotkey_enabled_var,
            command=self._sync_settings_hotkey_state,
            anchor="w",
        )
        self.settings_hotkey_enabled_check.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="w")

        self.settings_hotkey_label = tk.Label(shell, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["small_bold"], anchor="w")
        self.settings_hotkey_label.grid(row=2, column=0, padx=20, pady=(0, 6), sticky="w")

        hotkey_row = tk.Frame(shell, bg=THEME["panel"])
        hotkey_row.grid(row=3, column=0, padx=20, pady=(0, 6), sticky="ew")
        hotkey_row.grid_columnconfigure(0, weight=1)
        self.settings_hotkey_entry = tk.Entry(
            hotkey_row,
            textvariable=self.settings_hotkey_var,
            bg=THEME["panel_strong"],
            relief="solid",
            bd=1,
            font=FONTS["body"],
            insertbackground=THEME["ink"],
            readonlybackground=THEME["panel_strong"],
            disabledbackground=THEME["panel_alt"],
            disabledforeground=THEME["muted"],
        )
        self.settings_hotkey_entry.grid(row=0, column=0, sticky="ew")
        self.settings_hotkey_entry.configure(state="readonly")
        self.settings_hotkey_record_button = RoundedButton(
            hotkey_row,
            bg=THEME["accent_soft"],
            fg=THEME["ink"],
            command=self._begin_hotkey_capture,
            width=150,
            height=38,
            radius=16,
            border_color=THEME["accent_soft"],
            border_width=1,
        )
        self.settings_hotkey_record_button.grid(row=0, column=1, padx=(10, 0))
        self._style_button(self.settings_hotkey_record_button, THEME["accent_soft"], THEME["ink"])

        self.settings_hotkey_hint_label = tk.Label(shell, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["small"], justify="left", wraplength=390, anchor="w")
        self.settings_hotkey_hint_label.grid(row=4, column=0, padx=20, pady=(0, 14), sticky="w")

        self.settings_language_label = tk.Label(shell, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["small_bold"], anchor="w")
        self.settings_language_label.grid(row=5, column=0, padx=20, pady=(0, 6), sticky="w")
        self.settings_language_combo = ttk.Combobox(shell, textvariable=self.settings_language_var, values=list(LANGUAGE_DISPLAY.values()), state="readonly", style="Hub.TCombobox")
        self.settings_language_combo.grid(row=6, column=0, padx=20, pady=(0, 14), sticky="ew")

        self.settings_startup_check = tk.Checkbutton(
            shell,
            bg=THEME["panel"],
            fg=THEME["ink"],
            selectcolor=THEME["panel_strong"],
            activebackground=THEME["panel"],
            activeforeground=THEME["ink"],
            font=FONTS["body_bold"],
            variable=self.settings_startup_var,
            anchor="w",
        )
        self.settings_startup_check.grid(row=7, column=0, padx=20, pady=(0, 4), sticky="w")

        self.settings_startup_note_label = tk.Label(shell, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["small"], justify="left", wraplength=360, anchor="w")
        self.settings_startup_note_label.grid(row=8, column=0, padx=20, pady=(0, 16), sticky="w")

        button_row = tk.Frame(footer_shell, bg=THEME["panel"])
        button_row.pack(anchor="e", padx=20, pady=18)
        self.settings_save_button = RoundedButton(
            button_row,
            bg=THEME["accent"],
            fg="white",
            command=self.save_settings_dialog,
            width=110,
            height=42,
            radius=18,
            border_color=THEME["accent"],
            border_width=1,
        )
        self.settings_save_button.grid(row=0, column=0, padx=(0, 10))
        self.settings_cancel_button = RoundedButton(
            button_row,
            bg=THEME["accent_soft"],
            fg=THEME["ink"],
            command=self.close_settings_window,
            width=110,
            height=42,
            radius=18,
            border_color=THEME["accent_soft"],
            border_width=1,
        )
        self.settings_cancel_button.grid(row=0, column=1)
        self._style_button(self.settings_save_button, THEME["accent"], "white")
        self._style_button(self.settings_cancel_button, THEME["accent_soft"], THEME["ink"])

        self._refresh_settings_window_text()
        self._sync_settings_hotkey_state()
        self._update_hotkey_capture_ui()
        window.focus_force()

    def close_settings_window(self) -> None:
        self._end_hotkey_capture()
        if self.settings_window and self.settings_window.winfo_exists():
            try:
                self.settings_window.grab_release()
            except Exception:
                pass
            self.settings_window.destroy()
        self.settings_window = None
        self.settings_language_var = None
        self.settings_hotkey_var = None
        self.settings_hotkey_enabled_var = None
        self.settings_startup_var = None
        self.settings_header_label = None
        self.settings_hotkey_enabled_check = None
        self.settings_hotkey_label = None
        self.settings_hotkey_entry = None
        self.settings_hotkey_record_button = None
        self.settings_hotkey_hint_label = None
        self.settings_language_label = None
        self.settings_language_combo = None
        self.settings_startup_check = None
        self.settings_startup_note_label = None
        self.settings_save_button = None
        self.settings_cancel_button = None

    def _sync_settings_hotkey_state(self) -> None:
        if not self.settings_hotkey_entry:
            return
        enabled = bool(self.settings_hotkey_enabled_var and self.settings_hotkey_enabled_var.get())
        self.settings_hotkey_entry.configure(state=("readonly" if enabled else "disabled"))
        if self.settings_hotkey_record_button:
            self.settings_hotkey_record_button.config(state=("normal" if enabled else "disabled"))
        if not enabled:
            self._end_hotkey_capture()

    def _refresh_settings_window_text(self) -> None:
        if not self.settings_window or not self.settings_window.winfo_exists():
            return
        self.settings_window.title(self.t("settings_title"))
        self.settings_header_label.config(text=self.t("settings_title"))
        self.settings_hotkey_enabled_check.config(text=self.t("settings_hotkey_enabled"))
        self.settings_hotkey_label.config(text=self.t("settings_hotkey"))
        self._update_hotkey_capture_ui()
        self.settings_language_label.config(text=self.t("settings_language"))
        self.settings_startup_check.config(text=self.t("settings_startup"))
        self.settings_startup_note_label.config(text=self.t("settings_startup_note"))
        self.settings_save_button.config(text=self.t("settings_save"))
        self.settings_cancel_button.config(text=self.t("settings_cancel"))

    def save_settings_dialog(self) -> None:
        language_display = self.settings_language_var.get().strip()
        new_language = LANGUAGE_BY_DISPLAY.get(language_display, self.settings.get("language", "zh"))
        new_hotkey_enabled = bool(self.settings_hotkey_enabled_var.get())
        new_hotkey_id = self.settings_hotkey_var.get().strip() or SETTINGS_DEFAULTS["globalHotkeyId"]
        new_launch_at_startup = bool(self.settings_startup_var.get())
        parsed_hotkey = parse_hotkey_id(new_hotkey_id)
        if new_hotkey_enabled and not parsed_hotkey:
            messagebox.showerror(self.t("settings_title"), self.t("hotkey_invalid"), parent=self.settings_window)
            return
        if parsed_hotkey:
            new_hotkey_id = parsed_hotkey[0]

        if new_hotkey_enabled and not self._is_hotkey_available(new_hotkey_id):
            messagebox.showerror(self.t("settings_title"), self.t("hotkey_in_use").format(new_hotkey_id), parent=self.settings_window)
            return

        if not self._set_launch_at_startup(new_launch_at_startup):
            messagebox.showerror(self.t("settings_title"), self.t("startup_sync_failed"), parent=self.settings_window)
            return

        self.settings = {
            "language": new_language,
            "globalHotkeyEnabled": new_hotkey_enabled,
            "globalHotkeyId": new_hotkey_id,
            "launchAtStartup": new_launch_at_startup,
        }
        self.language = new_language
        self._save_settings()
        self._apply_hotkey_settings()
        self.apply_language()
        self.refresh_view()
        self.set_status("settings_saved")
        self.close_settings_window()

    def _panel(self, parent: tk.Widget, **grid_kwargs) -> tk.Frame:
        frame = tk.Frame(parent, bg=THEME["panel"], bd=0, highlightbackground=THEME["border"], highlightthickness=1)
        if grid_kwargs:
            frame.grid(**grid_kwargs)
        return frame

    def _make_stat(self, parent: tk.Widget, column: int):
        card = tk.Frame(parent, bg=THEME["panel_strong"], bd=0, highlightbackground=THEME["border"], highlightthickness=1, width=168, height=102)
        card.grid(row=0, column=column, padx=(0 if column == 0 else 14, 0), sticky="ne")
        card.grid_propagate(False)
        caption = tk.Label(card, bg=THEME["panel_strong"], fg=THEME["muted"], font=FONTS["small_bold"])
        caption.place(x=16, y=18)
        value = tk.Label(card, bg=THEME["panel_strong"], fg=THEME["ink"], font=FONTS["stat"])
        value.place(x=16, y=42)
        return value, caption

    def _chip(self, parent: tk.Widget, bg: str | None = None) -> tk.Label:
        return tk.Label(
            parent,
            bg=bg or THEME["accent_soft"],
            fg=THEME["ink"],
            font=FONTS["small_bold"],
            padx=10,
            pady=4,
        )

    def _form_label(self, parent: tk.Widget, row: int) -> tk.Label:
        label = tk.Label(parent, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["small_bold"])
        label.grid(row=row, column=0, padx=20, pady=(0, 6), sticky="w")
        return label

    def _entry(self, parent: tk.Widget, row: int) -> tk.Entry:
        entry = tk.Entry(parent, bg=THEME["panel_strong"], relief="solid", bd=1, font=FONTS["body"], insertbackground=THEME["ink"])
        entry.grid(row=row, column=0, padx=20, pady=(0, 12), sticky="ew")
        return entry

    def _action_button(self, parent: tk.Widget, column: int, bg: str, fg: str, command) -> RoundedButton:
        border_color = THEME["border"] if bg in {THEME["panel_strong"], THEME["accent_soft"], THEME["accent_muted"]} else bg
        button = RoundedButton(
            parent,
            bg=bg,
            fg=fg,
            command=command,
            width=120,
            height=42,
            radius=18,
            border_color=border_color,
            border_width=1,
        )
        button.grid(row=0, column=column, padx=(12 if column else 0, 0))
        self._style_button(button, bg, fg)
        return button

    def _style_button(self, button, bg: str, fg: str) -> None:
        button.config(
            font=FONTS["body_bold"],
            activebackground=bg,
            activeforeground=fg,
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

    def _default_settings(self):
        return dict(SETTINGS_DEFAULTS)

    def _normalize_settings(self, raw):
        settings = self._default_settings()
        if isinstance(raw, dict):
            language = raw.get("language")
            if language in {"zh", "en"}:
                settings["language"] = language
            hotkey_enabled = raw.get("globalHotkeyEnabled")
            if isinstance(hotkey_enabled, bool):
                settings["globalHotkeyEnabled"] = hotkey_enabled
            hotkey_id = raw.get("globalHotkeyId")
            parsed_hotkey = parse_hotkey_id(hotkey_id)
            if parsed_hotkey:
                settings["globalHotkeyId"] = parsed_hotkey[0]
            launch_at_startup = raw.get("launchAtStartup")
            if isinstance(launch_at_startup, bool):
                settings["launchAtStartup"] = launch_at_startup
        return settings

    def _load_settings(self):
        raw = self._load_json(self.settings_path)
        settings = self._normalize_settings(raw if isinstance(raw, dict) else {})
        if not self.settings_path.exists():
            self._write_json(self.settings_path, settings)
        return settings

    def _save_settings(self):
        self._write_json(self.settings_path, self.settings)

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

    def _comparable_value(self, value: str, mode: str | None = None) -> str:
        mode = mode or self.mode
        if mode == "links":
            normalized = self._normalize_url(value).strip().lower()
            return normalized[:-1] if normalized.endswith("/") else normalized
        normalized = self._normalize_folder_path(value)
        return os.path.normcase(os.path.normpath(normalized)) if normalized else ""

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
        self.kicker_label = tk.Label(title_wrap, bg=THEME["panel"], fg=THEME["accent"], font=FONTS["small_bold"], anchor="w")
        self.kicker_label.pack(anchor="w")
        self.title_label = tk.Label(title_wrap, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["title"], anchor="w")
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(title_wrap, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["body"], anchor="w", justify="left")
        self.subtitle_label.pack(anchor="w", pady=(8, 0))
        self.hero_chip_row = tk.Frame(title_wrap, bg=THEME["panel"])
        self.hero_chip_row.pack(anchor="w", pady=(12, 0))
        self.mode_badge = self._chip(self.hero_chip_row)
        self.mode_badge.pack(side="left")
        self.launch_chip = self._chip(self.hero_chip_row, THEME["accent_muted"])
        self.launch_chip.pack(side="left", padx=(10, 0))
        self.favorite_chip = self._chip(self.hero_chip_row, THEME["accent_muted"])
        self.favorite_chip.pack(side="left", padx=(10, 0))
        self.drag_chip = self._chip(self.hero_chip_row, THEME["accent_muted"])
        self.drag_chip.pack(side="left", padx=(10, 0))
        self.health_chip = self._chip(self.hero_chip_row, THEME["accent_muted"])
        self.health_chip.pack(side="left", padx=(10, 0))

        action_wrap = tk.Frame(self.header, bg=THEME["panel"])
        action_wrap.grid(row=0, column=1, padx=(0, 20), pady=18, sticky="ne")
        self.settings_button = RoundedButton(
            action_wrap,
            bg=THEME["panel_strong"],
            fg=THEME["ink"],
            command=self.open_settings_window,
            width=102,
            height=42,
            radius=18,
            border_color=THEME["border"],
            border_width=1,
        )
        self.settings_button.grid(row=0, column=0, padx=(0, 10))
        self.mode_button = RoundedButton(
            action_wrap,
            bg=THEME["accent_soft"],
            fg=THEME["ink"],
            command=self.switch_mode,
            width=112,
            height=42,
            radius=18,
            border_color=THEME["accent_soft"],
            border_width=1,
        )
        self.mode_button.grid(row=0, column=1)
        self._style_button(self.settings_button, THEME["panel_strong"], THEME["ink"])
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

        self.form_title_label = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["section"])
        self.form_title_label.grid(row=0, column=0, padx=20, pady=(18, 8), sticky="w")
        self.form_tip_label = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["body"], wraplength=280, justify="left")
        self.form_tip_label.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")
        self.name_label = self._form_label(self.left_panel, 2)
        self.name_entry = self._entry(self.left_panel, 3)
        self.path_label = self._form_label(self.left_panel, 4)

        self.path_row = tk.Frame(self.left_panel, bg=THEME["panel"])
        self.path_row.grid(row=5, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.path_row.grid_columnconfigure(0, weight=1)
        self.path_entry = tk.Entry(self.path_row, bg=THEME["panel_strong"], relief="solid", bd=1, font=FONTS["body"], insertbackground=THEME["ink"])
        self.path_entry.grid(row=0, column=0, sticky="ew")
        self.browse_folder_button = RoundedButton(
            self.path_row,
            bg=THEME["accent_soft"],
            fg=THEME["ink"],
            command=self.browse_folder,
            width=92,
            height=38,
            radius=16,
            border_color=THEME["accent_soft"],
            border_width=1,
        )
        self.browse_folder_button.grid(row=0, column=1, padx=(10, 0))
        self._style_button(self.browse_folder_button, THEME["accent_soft"], THEME["ink"])
        self.browse_file_button = RoundedButton(
            self.path_row,
            bg=THEME["accent_muted"],
            fg=THEME["ink"],
            command=self.browse_file,
            width=86,
            height=38,
            radius=16,
            border_color=THEME["accent_muted"],
            border_width=1,
        )
        self.browse_file_button.grid(row=0, column=2, padx=(10, 0))
        self._style_button(self.browse_file_button, THEME["accent_muted"], THEME["ink"])

        self.category_label = self._form_label(self.left_panel, 6)
        self.category_entry = self._entry(self.left_panel, 7)
        self.notes_label = self._form_label(self.left_panel, 8)
        self.notes_text = tk.Text(self.left_panel, height=4, bg=THEME["panel_strong"], relief="solid", bd=1, font=FONTS["body"], insertbackground=THEME["ink"])
        self.notes_text.grid(row=9, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.added_label = self._form_label(self.left_panel, 10)
        self.added_value = tk.Label(self.left_panel, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["body"])
        self.added_value.grid(row=11, column=0, padx=20, pady=(0, 6), sticky="w")
        self.data_note_label = tk.Label(self.left_panel, bg=THEME["panel_alt"], fg=THEME["muted"], font=FONTS["small"], wraplength=280, justify="left", padx=14, pady=8)
        self.data_note_label.grid(row=12, column=0, padx=20, pady=(0, 10), sticky="ew")

        button_row = tk.Frame(self.left_panel, bg=THEME["panel"])
        button_row.grid(row=13, column=0, padx=20, pady=(0, 10), sticky="w")
        self.save_button = RoundedButton(
            button_row,
            bg=THEME["accent"],
            fg="white",
            command=self.save_current,
            width=132,
            height=44,
            radius=18,
            border_color=THEME["accent"],
            border_width=1,
        )
        self.save_button.grid(row=0, column=0, padx=(0, 12))
        self.clear_button = RoundedButton(
            button_row,
            bg=THEME["accent_soft"],
            fg=THEME["ink"],
            command=self.clear_form,
            width=120,
            height=44,
            radius=18,
            border_color=THEME["accent_soft"],
            border_width=1,
        )
        self.clear_button.grid(row=0, column=1)
        self._style_button(self.save_button, THEME["accent"], "white")
        self._style_button(self.clear_button, THEME["accent_soft"], THEME["ink"])
        self.status_label = tk.Label(self.left_panel, bg=THEME["accent_soft"], fg=THEME["success"], font=FONTS["body"], wraplength=280, justify="left", padx=14, pady=8)
        self.status_label.grid(row=14, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.right_panel = self._panel(body, row=0, column=1, padx=(16, 0), sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=1)

        topbar = tk.Frame(self.right_panel, bg=THEME["panel"])
        topbar.grid(row=0, column=0, padx=20, pady=(18, 4), sticky="ew")
        topbar.grid_columnconfigure(0, weight=1)
        self.collection_title_label = tk.Label(topbar, bg=THEME["panel"], fg=THEME["ink"], font=FONTS["section"])
        self.collection_title_label.grid(row=0, column=0, sticky="w")

        toolbar = tk.Frame(topbar, bg=THEME["panel"])
        toolbar.grid(row=0, column=1, sticky="e")
        self.open_button = self._action_button(toolbar, 0, THEME["accent"], "white", self.open_selected)
        self.favorite_button = self._action_button(toolbar, 1, THEME["panel_strong"], THEME["ink"], self.toggle_favorite_selected)
        self.favorites_only_button = self._action_button(toolbar, 2, THEME["accent_soft"], THEME["ink"], self.toggle_favorites_filter)
        self.check_paths_button = self._action_button(toolbar, 3, THEME["accent_muted"], THEME["ink"], self.check_paths)
        self.edit_button = self._action_button(toolbar, 4, THEME["accent_soft"], THEME["ink"], self.start_edit_selected)
        self.delete_button = self._action_button(toolbar, 5, THEME["danger"], "white", self.delete_selected)

        subtitlebar = tk.Frame(self.right_panel, bg=THEME["panel"])
        subtitlebar.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="ew")
        subtitlebar.grid_columnconfigure(0, weight=1)
        self.collection_subtitle_label = tk.Label(subtitlebar, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["body"])
        self.collection_subtitle_label.grid(row=0, column=0, sticky="w")
        self.collection_meta_label = tk.Label(subtitlebar, bg=THEME["panel"], fg=THEME["muted"], font=FONTS["small_bold"])
        self.collection_meta_label.grid(row=0, column=1, sticky="e")

        filter_row = tk.Frame(self.right_panel, bg=THEME["panel_alt"], bd=0, highlightbackground=THEME["border"], highlightthickness=1)
        filter_row.grid(row=2, column=0, padx=20, pady=(0, 12), sticky="ew")
        filter_row.grid_columnconfigure(1, weight=1)
        self.search_label = tk.Label(filter_row, bg=THEME["panel_alt"], fg=THEME["ink"], font=FONTS["small_bold"])
        self.search_label.grid(row=0, column=0, padx=16, pady=(14, 0), sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search_change)
        self.search_entry = tk.Entry(filter_row, textvariable=self.search_var, bg=THEME["panel_strong"], relief="solid", bd=1, font=FONTS["body"], insertbackground=THEME["ink"])
        self.search_entry.grid(row=1, column=0, columnspan=2, padx=16, pady=(8, 14), sticky="ew")
        self.search_hint_label = tk.Label(filter_row, bg=THEME["panel_alt"], fg=THEME["muted"], font=FONTS["body"])
        self.search_hint_label.grid(row=1, column=2, padx=(14, 0), sticky="w")
        self.filter_label = tk.Label(filter_row, bg=THEME["panel_alt"], fg=THEME["ink"], font=FONTS["small_bold"])
        self.filter_label.grid(row=0, column=3, padx=(20, 16), pady=(14, 0), sticky="w")
        self.filter_var = tk.StringVar()
        self.filter_combo = ttk.Combobox(filter_row, textvariable=self.filter_var, state="readonly", style="Hub.TCombobox")
        self.filter_combo.grid(row=1, column=3, padx=(20, 16), pady=(8, 14), sticky="e")
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_view())

        table_wrap = tk.Frame(self.right_panel, bg=THEME["panel_strong"], bd=0, highlightbackground=THEME["border"], highlightthickness=1)
        table_wrap.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_wrap, columns=("favorite", "name", "kind", "state", "category", "added", "path", "notes"), show="headings", style="Hub.Treeview")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.on_select())
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Configure>", lambda _event: self._resize_columns())
        self.tree.tag_configure("missing", foreground=THEME["danger"])
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.context_menu = tk.Menu(self, tearoff=0, bg=THEME["panel_strong"], fg=THEME["ink"], activebackground=THEME["accent_soft"], activeforeground=THEME["ink"], relief="flat", bd=1)
        self.empty_label = tk.Label(
            table_wrap,
            bg=THEME["panel_strong"],
            fg=THEME["muted"],
            font=("Segoe UI", 11, "bold"),
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

    def current_favorites_only(self) -> bool:
        return self.link_favorites_only if self.mode == "links" else self.folder_favorites_only

    def set_current_favorites_only(self, value: bool) -> None:
        if self.mode == "links":
            self.link_favorites_only = value
        else:
            self.folder_favorites_only = value

    def current_path_key(self) -> str:
        return "url" if self.mode == "links" else "path"

    def current_data_path(self) -> Path:
        return self.site_path if self.mode == "links" else self.folder_path

    def _find_duplicate_item(self, normalized_value: str, exclude_id: str | None = None):
        path_key = self.current_path_key()
        comparable_value = self._comparable_value(normalized_value)
        for item in self.current_items():
            if exclude_id and item.get("id") == exclude_id:
                continue
            if self._comparable_value(str(item.get(path_key, ""))) == comparable_value:
                return item
        return None

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

        existing_paths = {self._comparable_value(item.get("path", ""), "folders") for item in self.folders}
        added = 0
        skipped = 0
        now = datetime.now().astimezone
        for candidate in valid_paths:
            normalized_path = str(candidate)
            key = self._comparable_value(normalized_path, "folders")
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
        background = THEME["accent_soft"]
        if color == THEME["danger"]:
            background = "#fff0ef"
        elif color == THEME["muted"]:
            background = THEME["panel_alt"]
        self.status_label.config(text=text, fg=color or THEME["success"], bg=background)

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

    def toggle_favorites_filter(self) -> None:
        self.set_current_favorites_only(not self.current_favorites_only())
        self.refresh_view()

    def toggle_language(self) -> None:
        self.language = "en" if self.language == "zh" else "zh"
        self.settings["language"] = self.language
        self._save_settings()
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
        self.kicker_label.config(text=self.t("kicker"))
        self.title_label.config(text=self.t("window_title"))
        self.subtitle_label.config(text=self.t("subtitle_links" if self.mode == "links" else "subtitle_folders"))
        self.mode_badge.config(text=f"{self.t('current_mode')} · {self.t('mode_links_label' if self.mode == 'links' else 'mode_folders_label')}")
        self.launch_chip.config(text=self.t("chip_launch"))
        self.favorite_chip.config(text=self.t("chip_favorite"))
        self.drag_chip.config(text=self.t("chip_drag"))
        self.health_chip.config(text=self.t("chip_health"))
        self.settings_button.config(text=self.t("settings_button"))
        self.total_caption.config(text=self.t("total_links" if self.mode == "links" else "total_folders"))
        self.category_caption.config(text=self.t("categories"))
        self.visible_caption.config(text=self.t("visible_now"))
        self.form_tip_label.config(text=self.t("form_tip_links" if self.mode == "links" else "form_tip_folders"))
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
        self.favorites_only_button.config(text=self.t("favorites_only" if not self.current_favorites_only() else "show_all_items"))
        self.check_paths_button.config(text=self.t("check_paths"))
        self.edit_button.config(text=self.t("edit"))
        self.delete_button.config(text=self.t("delete"))
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
        for column in ("favorite", "name", "kind", "state", "category", "added", "path", "notes"):
            self.tree.heading(column, anchor="w")
        self.empty_label.config(text=self.t("empty_links" if self.mode == "links" else "empty_folders"))
        if self.search_var.get() != self.current_search_value():
            self.search_var.set(self.current_search_value())
        self.update_mode_ui()
        self.refresh_categories()
        self._refresh_tray_icon()
        self._refresh_settings_window_text()

    def update_mode_ui(self) -> None:
        is_links = self.mode == "links"
        selected = self.selected_item()
        mode_bg = THEME["accent_soft"] if is_links else THEME["accent"]
        mode_fg = THEME["ink"] if is_links else "white"
        self.mode_button.config(text=self.t("switch_to_folders" if is_links else "switch_to_links"))
        self.mode_button.config(bg=mode_bg, fg=mode_fg, activebackground=mode_bg, activeforeground=mode_fg, highlightbackground=mode_bg)
        self.form_title_label.config(text=self.t("form_edit_link" if is_links and self.editing_id else "form_add_link" if is_links else "form_edit_folder" if self.editing_id else "form_add_folder"))
        self.collection_title_label.config(text=self.t("collection_links" if is_links else "collection_folders"))
        self.collection_subtitle_label.config(text=self.t("collection_links_subtitle" if is_links else "collection_folders_subtitle"))
        self.save_button.config(text=self.t("save_changes" if self.editing_id else "save_link" if is_links else "save_folder"))
        self.favorite_button.config(text=self.t("unfavorite" if selected and selected.get("favorite") else "favorite"))
        favorites_filter_active = self.current_favorites_only()
        favorites_bg = THEME["accent"] if favorites_filter_active else THEME["accent_soft"]
        favorites_fg = "white" if favorites_filter_active else THEME["ink"]
        self.favorites_only_button.config(
            text=self.t("show_all_items" if favorites_filter_active else "favorites_only"),
            bg=favorites_bg,
            fg=favorites_fg,
            activebackground=favorites_bg,
            activeforeground=favorites_fg,
            highlightbackground=favorites_bg,
        )
        if is_links:
            self.check_paths_button.grid_remove()
            self.browse_folder_button.grid_remove()
            self.browse_file_button.grid_remove()
            self.path_entry.grid_configure(columnspan=3)
        else:
            self.check_paths_button.grid()
            self.check_paths_button.config(state="normal")
            self.path_entry.grid_configure(columnspan=1)
            self.browse_folder_button.grid()
            self.browse_file_button.grid()
            self.browse_folder_button.config(state="normal")
            self.browse_file_button.config(state="normal")
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
        favorites_only = self.current_favorites_only()
        visible = []
        path_key = self.current_path_key()

        for item in self.current_items():
            if current_filter != "__all__" and item["category"] != current_filter:
                continue
            if favorites_only and not item.get("favorite"):
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
        if favorites_only:
            summary = f"{summary} · {self.t('favorites_only_suffix')}"
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
            self.tree.column(column, width=column_width, minwidth=min_width, stretch=stretch, anchor="w")

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
        if self.tree.exists(item["id"]):
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

    def copy_selected_value(self) -> None:
        item = self.selected_item()
        if not item:
            self.set_status("select_first_link" if self.mode == "links" else "select_first_folder", color=THEME["danger"])
            return
        value = item.get("url" if self.mode == "links" else "path", "")
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.update_idletasks()
        self.set_status("copied_url" if self.mode == "links" else "copied_path")

    def show_context_menu(self, event) -> str:
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return "break"
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        self.on_select()
        self.context_menu.delete(0, tk.END)
        self.context_menu.add_command(label=self.t("open"), command=self.open_selected)
        if self.mode != "links":
            self.context_menu.add_command(label=self.t("open_location"), command=self.open_location_selected)
        self.context_menu.add_command(label=self.t("edit"), command=self.start_edit_selected)
        self.context_menu.add_command(label=self.t("unfavorite" if self.selected_item() and self.selected_item().get("favorite") else "favorite"), command=self.toggle_favorite_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=self.t("copy_url" if self.mode == "links" else "copy_path"), command=self.copy_selected_value)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=self.t("delete"), command=self.delete_selected)
        self.context_menu.tk_popup(event.x_root, event.y_root)
        self.context_menu.grab_release()
        return "break"

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
            if self._find_duplicate_item(normalized_path, exclude_id=self.editing_id):
                self.set_status("duplicate_link_path", color=THEME["danger"])
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
            if self._find_duplicate_item(normalized_path, exclude_id=self.editing_id):
                self.set_status("duplicate_folder_path", color=THEME["danger"])
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

        deduped = []
        seen = set()
        skipped = 0
        path_key = self.current_path_key()
        for item in normalized:
            comparable = self._comparable_value(str(item.get(path_key, "")))
            if comparable in seen:
                skipped += 1
                continue
            seen.add(comparable)
            deduped.append(item)

        if self.mode == "links":
            self.sites = deduped
        else:
            self.folders = deduped
        self.save_current_collection()
        self.clear_form()
        if skipped:
            self.set_status("backup_imported_skipped", args=[len(deduped), skipped])
        else:
            self.set_status("backup_imported")
        self.refresh_view()


if __name__ == "__main__":
    instance_guard = None
    try:
        instance_guard = SingleInstanceGuard(APP_MUTEX_NAME)
        if not instance_guard.acquire():
            signal_running_instance()
            raise SystemExit(0)
        app = ResourceHubApp(instance_guard=instance_guard)
        app.mainloop()
        if instance_guard:
            instance_guard.release()
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
        try:
            if instance_guard:
                instance_guard.release()
        except Exception:
            pass
        raise SystemExit(1)
