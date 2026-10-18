# Resource Hub — 迁移第一阶段：审计与环境检查

审计日期：2026-10-17
审计对象：`E:\Mytools\ResourceHub-GitHub-Ready`
审计方式：只读（未修改、未删除、未安装任何内容）
所有行号均指向 `resource_hub.pyw`，除非另有说明。

> **状态更新（2026-10-17 当天后段）：** 环境缺件已补齐，Flutter 原型已构建并在真机实测通过。
> **§1–§7 记录的是审计当时的状态；§8 是最终执行结果。两者冲突时以 §8 为准。**
> 原应用 `resource_hub.pyw` 全程未修改。

---

## 0. 结论摘要

| 项目 | 结果 |
|---|---|
| 现有技术栈 | Python 3.13 + Tkinter/ttk + tkinterdnd2 + pystray + Pillow |
| 代码规模 | `resource_hub.pyw` 单文件 2916 行；无其他 Python 模块 |
| 现有测试 | **零**。没有任何测试文件、测试框架或 CI 配置 |
| Flutter SDK | 审计时未安装 → **已装 3.47.7 stable**（`F:\flutter`），见 §8 |
| Dart | 审计时未安装 → **已装 3.13.5** |
| MSVC C++ 工具链 | `D:\Visual C++ Build Tools`（MSVC 14.50.35717）**存在但未注册、不可用** → **已装 VS 生成工具 2022 至 `F:\VS2022-BuildTools`** |
| Windows SDK | 审计时未安装 → **已装 10.0.26100.0** |
| Flutter Windows 原型 | 审计时判断无法构建 → **已构建并真机验证通过**，见 §8 |

**本阶段交付了：完整功能清单、数据契约、回归测试方案、迁移风险清单、下一阶段计划，以及一个可运行并已实测验证的 Flutter 原型（§8）。**
原型最初因环境缺件而未编写——"写了也只是一堆未编译的文本"。环境补齐后已构建并真机实测通过，八项验证全部达标（§8.2）。

---

## 1. 环境检查结果（第 4、5 项任务）

### 1.1 已具备

| 组件 | 版本 / 路径 | 来源 |
|---|---|---|
| Python | 3.13.11（`D:\miniconda3\python.exe`） | `start-resource-hub-python.bat:12` |
| MSVC 编译器 | 14.50.35717 | `D:\Visual C++ Build Tools\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x64\cl.exe` |
| MSBuild | Current | `D:\Visual C++ Build Tools\MSBuild\Current\Bin\MSBuild.exe` |
| git | 2.55.0.windows.3 | PATH |
| winget | v1.29.380 | PATH |
| 操作系统 | Windows 11 build 26200 | `cmd /c ver` |
| 磁盘可用 | C: 81 GB / D: 46 GB / E: 44 GB | `df -h` |

### 1.2 缺失（阻塞项）

| 组件 | 状态 | 影响 |
|---|---|---|
| Flutter SDK | 未安装。`flutter` / `dart` 不在 PATH，`C:\flutter`、`D:\flutter`、`~/flutter` 等常见位置均无 | 无法创建/运行任何 Flutter 工程 |
| Windows 10/11 SDK | 未安装。`C:\Program Files (x86)\Windows Kits\10` 下只有 `Catalogs`、`Debuggers`，**没有 `Include` 和 `Lib`** | 没有 `windows.h`、`kernel32.lib`；MSVC 装了也编不出 Windows 程序 |
| CMake / Ninja | 独立安装不存在 | **不构成阻塞**：Flutter 自带 cmake/ninja bundle |

### 1.3 需要留意的风险

- **MSVC 14.50.35717 版本很新**。该版本与当前 Flutter stable 的 CMake 生成器是否完全兼容，需要装完 Flutter 后用 `flutter doctor -v` 实测确认，不能假定可用。
- 现有 `python` 在 PATH 上是 3.13.11，与打包 EXE 用的 `python313.dll` 一致，后端迁移时可直接复用这个解释器。
- 机器上没有 Visual Studio IDE，只有 Build Tools，装在非默认路径 `D:\Visual C++ Build Tools`。Flutter 的 `flutter doctor` 依赖 `vswhere.exe` 定位 VS，而 **`vswhere.exe` 当前不存在**（`C:\Program Files (x86)\Microsoft Visual Studio\Installer\` 缺失）。这很可能导致 `flutter doctor` 报告"Visual Studio 未找到"，即使 MSVC 其实装了。需要在装 Flutter 时一并处理（装 VS Installer 或设置 `VSINSTALLDIR`）。

---

## 2. 现有架构

### 2.1 文件构成

| 文件 | 作用 |
|---|---|
| `resource_hub.pyw` | 全部应用代码，2916 行单文件 |
| `ResourceHubPython.spec` | PyInstaller onedir 打包 spec |
| `build/resourcehub-onefile-specs-1818/ResourceHub.spec` | PyInstaller onefile 打包 spec |
| `build-resource-hub-python.ps1` | 构建脚本（93 行） |
| `start-resource-hub-python.bat` | 源码模式启动器（89 行，探测 Python 环境） |
| `start-resource-hub-python.vbs` | 无窗口启动 |
| `Install-ResourceHub-*-Shortcut.vbs` | 桌面快捷方式安装 |
| `requirements-python.txt` | `tkinterdnd2==0.4.3`、`pystray==0.19.5` |
| `sites.json` / `folders.json` / `settings.json` | 运行时数据（git 忽略） |
| `DesktopShortcut.ico/.png`、`LinkHub.ico`、`settings_icon.png` | 图标资源 |

### 2.2 进程模型

```
__main__ (2880)
  └─ SingleInstanceGuard(APP_MUTEX_NAME)          # 命名互斥体 69/617
       ├─ 已存在 → signal_running_instance()      # 640：SetEvent 唤醒旧实例
       └─ 未存在 → ResourceHubApp(instance_guard) # 885
                     └─ mainloop()
```

- 单实例互斥体名：`Local\Mytools.ResourceHub.SingleInstance`（`:69`）
- 唤醒事件名：`Local\Mytools.ResourceHub.WakeEvent`（`:70`，创建于 `:1235`，等待于 `:1271`）

### 2.3 线程模型

| 线程 | 职责 | 代码位置 |
|---|---|---|
| Tk 主线程 | 全部 UI + 数据读写 | 隐式 |
| `ResourceHubHotkey`（daemon） | Win32 消息循环，`RegisterHotKey`/`GetMessageW`，命中后投递到 `queue.SimpleQueue` | `:670-700` |
| pystray 托盘线程 | `run_detached()`，回调经 `self.after(0, ...)` 回主线程 | `:1316`、`:1329`、`:1332` |
| 主线程定时轮询 | 每 80ms 排空热键队列 + 检查唤醒事件 | `:1249-1277` |

**这是本次迁移最关键的耦合点**：全局热键必须在拥有该热键消息循环的线程上注册/注销；托盘与 Tk 主循环靠 `after` 轮询桥接。Flutter 接管 UI 后，这两者归谁管是个必须先定的架构决策（见 §6）。

---

## 3. 完整功能清单（第 2 项任务）

### 3.1 窗口

| 窗口 | 类型 | 尺寸 | 说明 | 行号 |
|---|---|---|---|---|
| 主窗口 | `TkinterDnD.Tk` | 1280×820，最小 1180×760 | 单窗口，无标签页/无路由 | `:984-985` |
| 设置窗口 | `tk.Toplevel` | 500×500，不可缩放，`grab_set()` 模态 | 打开时若已存在则前置 | `:1537-1544` |
| 关于/其他 | 无 | — | — | — |

**"页面"概念 = 模式切换**：`links`（网站）↔ `folders`（资源），`switch_mode()` `:2391`。
两种模式共用同一套控件，靠 `update_mode_ui()` `:2466` 切换可见性与文案。

### 3.2 主窗口布局

```
header (:1964)
  ├─ kicker / title / subtitle / 4 个 chip (:1970-1987)
  ├─ settings_button + mode_button (:1989-2016)
  └─ 3 张统计卡 total / categories / visible (:2018-2022, :1761)

body (:2024)
  ├─ left_panel 表单 (:2029) — 固定宽 340
  │    name_entry, path_entry + browse_folder/file,
  │    category_entry, notes_text(4行), added_value,
  │    data_note, save_button, clear_button, status_label
  └─ right_panel 列表 (:2116)
       ├─ topbar: 标题 + 6 个工具栏按钮 (:2120-2133)
       ├─ subtitlebar: 副标题 + 结果统计 (:2135-2141)
       ├─ filter_row: search_entry + filter_combo (:2143-2159)
       └─ table_wrap: ttk.Treeview 8 列 + 滚动条 + empty_label (:2161-2183)
```

### 3.3 全部按钮与交互控件

| 控件 | 触发 | 行为 | 行号 |
|---|---|---|---|
| 设置 | `open_settings_window` | 开设置窗口 | `:1991` |
| 切换模式 | `switch_mode` | links ↔ folders | `:2003` |
| 选文件夹 | `browse_folder` | `filedialog.askdirectory` | `:2047`、`:2398` |
| 选文件 | `browse_file` | `filedialog.askopenfilename` | `:2060`、`:2406` |
| 保存 | `save_current` | 校验→去重→插入/更新→写盘 | `:2087`、`:2759` |
| 清空表单 | `clear_form` | 清空输入与选中 | `:2099`、`:2364` |
| 打开 | `open_selected` | 链接 `webbrowser.open`；资源 `os.startfile` | `:2128`、`:2698` |
| 收藏 | `toggle_favorite_selected` | 反转 favorite→写盘→置顶 | `:2129`、`:2658` |
| 只看收藏 | `toggle_favorites_filter` | 切换筛选并刷新 | `:2130`、`:2380` |
| 检测路径 | `check_paths` | 统计失效路径并提示 | `:2131`、`:2672` |
| 编辑 | `start_edit_selected` | 回填表单进入编辑态 | `:2132`、`:2639` |
| 删除 | `delete_selected` | `messagebox.askyesno` 确认后删除 | `:2133`、`:2683` |
| 列表双击 | `open_selected` | 同"打开" | `:2168` |
| 列表右键 | `show_context_menu` | 打开/定位/编辑/收藏/复制/删除 | `:2169`、`:2738` |
| 搜索框 | `on_search_change` | 实时过滤（`trace_add("write")`） | `:2149`、`:2376` |
| 分类下拉 | `refresh_view` | 按分类过滤 | `:2159` |
| 设置：保存/取消 | `save_settings_dialog` / `close_settings_window` | 见 §3.5 | `:1720`、`:1670` |

> `RoundedButton`（`:711`）是自定义控件：继承 `tk.Canvas`，用 Pillow 逐次生成圆角位图当背景，带 hover/disabled 三态。**Flutter 里这些全部由 Material 组件原生提供，不需要移植。**

### 3.4 键盘 / 全局快捷键

| 项 | 值 | 行号 |
|---|---|---|
| 默认快捷键 | `Ctrl + Alt + Space` | `:198` |
| 当前用户实际配置 | `Ctrl + Space` | `settings.json` |
| 支持的修饰键 | Ctrl / Alt / Shift / Win（含别名映射） | `:92-106` |
| 支持的特殊键 | 26 个（Space/Tab/Enter/Esc/方向/符号键）+ A–Z + 0–9 + F1–F24 | `:107-134` |
| 注册 API | `user32.RegisterHotKey`，热键 ID `0xB123` | `:682`、`:71` |
| 被占用时的处理 | 启动时提示"当前不可用"；保存设置时用临时 ID 试注册再回滚校验 | `:1057`、`:1068-1083` |
| 录制 | 设置窗口内捕获 `<KeyPress>`，Esc 取消，无修饰键则报错 | `:1128-1161` |
| 快捷键行为 | 切换窗口显示/隐藏（`toggle_window_visibility`） | `:1269`、`:1405` |

程序内没有其他键盘快捷键绑定（无全局 `<Control-*>` 绑定）。

### 3.5 托盘事件

| 项 | 说明 | 行号 |
|---|---|---|
| 库 | `pystray`，`run_detached()` | `:1310-1316` |
| 菜单项 1 | "显示 / 隐藏" → `toggle_window_visibility` | `:1302` |
| 菜单项 2 | "退出程序" → `exit_application` | `:1303` |
| 托盘图标 | 优先 `DesktopShortcut.png`，兜底用 Pillow 现画一个蓝底 "R" | `:1279-1298` |
| 语言切换后 | 重建菜单（`_refresh_tray_icon`） | `:1318`、`:2463` |
| 关闭主窗口 | `WM_DELETE_WINDOW` → `hide_to_tray`，**不退出** | `:1025` |
| 隐藏动画 | 窗口 alpha 140ms 三次缓出淡出 | `:202-203`、`:1342-1435` |
| 显示动画 | 淡入 + `topmost` 闪一下 + `SetForegroundWindow` + 搜索框聚焦 | `:1437-1480` |

### 3.6 拖拽事件

| 项 | 说明 | 行号 |
|---|---|---|
| 注册目标 | 5 个控件：根窗口、header、left_panel、right_panel、tree | `:1857-1864` |
| 协议 | `DND_FILES`（tkinterdnd2） | `:1861` |
| 处理 | `_on_drop_files` → `tk.splitlist(event.data)` 解析多路径 | `:1866-1872` |
| 业务 | `add_dropped_resources`（`:2270-2332`）：校验路径存在 → 若在 links 模式自动切到 folders → 规范化后按路径去重 → 新项 `insert(0, ...)` → 写盘 → 刷新 → 状态栏提示"已添加 N 个，跳过 M 个重复项" |
| 边界 | 全部无效时提示"拖入内容里没有可用的文件或文件夹"；空文件夹只存路径，不展开子项（README 明确说明） | `:2281` |

### 3.7 文件操作

| 操作 | 实现 | 行号 |
|---|---|---|
| 打开网站 | `webbrowser.open(url)` | `:2704` |
| 打开文件/文件夹 | `os.startfile(path)` | `:2710` |
| 在资源管理器定位 | `subprocess.Popen(["explorer", f"/select,{path}"])` | `:2723` |
| 选择目录/文件 | `filedialog.askdirectory` / `askopenfilename` | `:2401`、`:2409` |
| 存在性检测 | `Path(path).exists()` | `:2260-2262` |
| 复制到剪贴板 | `clipboard_clear` + `clipboard_append` | `:2733-2734` |
| 路径规范化 | `os.path.expandvars` + `expanduser`；比较用 `os.path.normcase(normpath(...))` | `:1901-1912` |
| 开机启动 | 用 PowerShell COM `WScript.Shell` 写 `.lnk` 到启动目录 | `:1168-1233` |
| 退出清理 | 注销热键 → 关唤醒事件 → 停托盘 → 释放互斥体 → `destroy()` | `:1482-1506` |

**开机启动细节**：快捷方式路径 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Resource Hub.lnk`（`:1169-1170`）；冻结态 target 指向 exe，源码态指向 `start-resource-hub-python.vbs`（`:1183-1198`）；带参数 `--startup-hidden`（`:201`），启动后直接进托盘（`:971-972`）。

### 3.8 数据持久化

| 文件 | 结构 | 字段 |
|---|---|---|
| `sites.json` | 顶层 JSON 数组 | `id, name, url, category, note, favorite, createdAt` |
| `folders.json` | 顶层 JSON 数组 | `id, name, path, kind, category, note, favorite, createdAt` |
| `settings.json` | 顶层 JSON 对象 | `language, globalHotkeyEnabled, globalHotkeyId, launchAtStartup` |

关键约定（迁移时必须逐条保持兼容）：

| 约定 | 详情 | 行号 |
|---|---|---|
| 编码与格式 | `encoding="utf-8"`，`ensure_ascii=False`，`indent=2` | `:1823-1824` |
| 存储位置 | 与 exe 同目录（非 AppData） | `:894-896` |
| `category` 哨兵值 | 未分类存为字面量 `__uncategorized__`；读取时也把 `"未分类"`/`"Uncategorized"` 归一化为该值 | `:1915`、`:1929` |
| 筛选哨兵值 | 全部 = `__all__`（仅内存，不落盘） | `:955`、`:2348` |
| `createdAt` | 本地时区 ISO8601 带偏移，如 `2026-04-22T13:53:49.313959+08:00` | `:1925` |
| `favorite` | 恒为 `bool`，缺失当 False | `:1924` |
| `url` 规范化 | 无 `://` 时自动补 `https://` | `:1893-1899` |
| `kind` 推断 | 无 `kind` 字段时按 `is_dir()` 推断；也兼容旧字段 `url` 代替 `path` | `:1932-1938` |
| 去重键 | links 用规范化 URL 去尾斜杠 + 小写；folders 用 `normcase(normpath())` | `:1906-1912` |
| 首次运行 | sites 为空则写入 OpenAI/GitHub 两条示例；folders 为空则写入 桌面/文档/下载 | `:1874-1891`、`:1953-1958` |
| 加载过滤 | 缺 `name` 或缺 `url`/`path` 的条目直接丢弃 | `:1951-1952` |

### 3.9 多语言

- `STRINGS` 字典，`zh` / `en` 两套完整文案（`:325-614`），约 130 个键
- 取值 `self.t(key)`（`:974`），缺键时回显 key 本身
- `apply_language()`（`:2414-2464`）一次性刷新所有控件文本，并在持久化后同步刷新托盘菜单和设置窗口
- 切换入口**只有设置对话框**（下拉框，`:1617`）

### 3.10 其他已实现细节

- 高 DPI：`SetProcessDpiAwarenessContext(per-monitor-v2)`，三级回退（`:19-39`）；Tk 缩放按系统 DPI 调整（`:1005-1015`）
- 窗口图标：优先 `.ico`→`iconbitmap`，退化到 `.png`→`iconphoto`（`:990-1003`）
- 列表列宽按窗口宽度百分比自适应（`:2602-2629`）
- 收藏项排序置顶（稳定排序，`:2555`）
- 失效路径行标红（Treeview tag `missing`，`:2171`、`:2560`）

---

## 4. 审计发现的问题

### 4.1 死代码：三个功能定义了但无法触发

| 函数 | 行号 | 引用次数 | 说明 |
|---|---|---|---|
| `export_current` | `:2827` | 1（仅定义） | 导出 JSON 备份，**没有任何按钮或菜单调用它** |
| `import_current` | `:2841` | 1（仅定义） | 导入 JSON 备份，**同上** |
| `toggle_language` | `:2384` | 1（仅定义） | 一键切换语言，**无调用点**（语言仍可在设置里改） |

**`README.md:14` 声称支持 "Import / export JSON backups"，但当前 UI 里根本点不到。** 迁移时要么补上入口，要么从文档里删掉——这是需要你决策的一个小口径问题。

### 4.2 数据写入没有原子性

`_write_json`（`:1823-1824`）直接 `path.write_text(...)` 覆盖原文件。没有临时文件 + rename，没有备份。
在写盘瞬间断电/崩溃 → `sites.json` / `folders.json` 可能被截断。而 `_load_json`（`:1815-1821`）遇到解析失败**静默返回 `[]`**，随后 `_load_all_data`（`:1953-1958`）会因为"数据为空"而**写入默认示例数据，直接覆盖掉用户恢复不了的原文件**。

这是一个真实的数据丢失路径。迁移到新架构时，协议层应该顺手修掉（临时文件 + `os.replace` + 解析失败时拒绝覆盖）。

### 4.3 业务逻辑与 UI 完全耦合

所有业务方法都是 `ResourceHubApp` 的方法，且大量依赖 UI 状态与控件：

- `set_status()` 直接操作 `self.status_label`（`:2334-2343`）
- `_find_duplicate_item` 依赖 `self.current_items()` / `self.current_path_key()`（`:2221-2229`）
- `refresh_view` 里同时做数据过滤**和** Treeview 插入（`:2520-2600`）
- `save_current` 里校验、去重、写盘、清表单、刷新 UI 混在一个函数（`:2759-2825`）

**纯逻辑可复用的部分实际只有**：`parse_hotkey_id` 及热键常量表（`:206-255`）、`_normalize_url` / `_normalize_folder_path` / `_comparable_value`（`:1893-1912`）、`_normalize_site` / `_normalize_folder`（`:1914-1948`）、`_load_json` / `_write_json`（`:1815-1824`）。
其余约 2000 行里，业务规则和布局/控件调用是交织的。第三阶段的"拆分"是**真重构**，不是搬运，需要按 §5 的测试方案兜底。

### 4.4 零测试

没有任何测试文件、没有 `pytest.ini`/`conftest.py`、没有 `.github/`。第 5 阶段要求"运行原有业务测试"——**没有可运行的原有测试**，必须从零建。

---

## 5. 回归测试方案（第 3 项任务）

因为项目零测试，本方案分两层。**第一批测试应该写在现有 Python 代码上（迁移前），作为行为基线**，否则新版本无从对比。

### 5.1 纯函数层（可立即写，无需 UI，无副作用）

| 用例 | 目标 | 断言要点 |
|---|---|---|
| `parse_hotkey_id` 正常 | `"Ctrl + Alt + Space"` | 返回 `(规范标签, 掩码, VK)`，掩码 = `MOD_CONTROL\|MOD_ALT`，VK = `0x20` |
| `parse_hotkey_id` 别名 | `"control+shift+q"` | 归一化为 `"Ctrl + Shift + Q"` |
| `parse_hotkey_id` 非法 | 缺修饰键 / 缺主键 / 两个主键 / 空串 | 返回 `None` |
| `parse_hotkey_id` 功能键 | `"Alt + F12"` | VK = `0x70+11` |
| `_normalize_url` | `"github.com"` / `"https://a.b"` / 空 | 补 `https://`；已带协议不重复；空返回空 |
| `_normalize_folder_path` | 含 `%VAR%`、`~`、空白 | 展开环境变量与用户目录；纯空白返回空 |
| `_comparable_value` (links) | `"HTTP://A.com/"` vs `"http://a.com"` | 判定为重复 |
| `_comparable_value` (folders) | 大小写/分隔符不同的同一路径 | 判定为重复 |
| `_normalize_site` | 缺字段 / `category="未分类"` / `favorite` 非 bool | 补默认值、哨兵归一化、强制 bool |
| `_normalize_folder` | 缺 `kind` 且路径是目录 / 旧字段用 `url` | 推断 `folder`；兼容 `url`→`path` |
| `format_added` | ISO 字符串 / 垃圾字符串 / 空 | 格式化；异常时原样返回 |

### 5.2 数据契约层（文件级，用临时目录）

| 用例 | 断言要点 |
|---|---|
| 读取现有真实 `sites.json` / `folders.json` | 解析成功，条目数不变，每条字段齐全 |
| 写入后重新读取 | 往返一致（round-trip）；中文不乱码；`indent=2`、无 `\uXXXX` 转义 |
| 空文件/损坏 JSON | 当前行为是返回 `[]`；**记录此行为**，迁移后应改为拒绝覆盖（见 §4.2） |
| 缺 `name` / 缺 `path` 条目 | 被过滤丢弃 |
| 首次运行 | 生成默认示例数据 |
| `settings.json` 非法值 | 回落到默认值（`language` 非 zh/en、`globalHotkeyId` 非法） |

### 5.3 业务层（需要 UI，改用无头构造或直接调用）

`add_dropped_resources` 的去重与自动切换模式、`save_current` 的校验分支、`import_current` 的去重统计、`refresh_view` 的过滤+排序规则（收藏置顶稳定性）——这些依赖 `self.tree`，建议先把纯计算部分抽出来再测，或接受用 Tk 无头实例（`root.withdraw()`）跑。

### 5.4 手工桌面验证清单（第 5、6 阶段必须逐条过）

这些**无法自动化**，必须在真实桌面上点点看：

| # | 场景 | 通过标准 |
|---|---|---|
| 1 | 从浏览器拖一个链接到窗口 | —（当前不支持拖 URL，仅文件/文件夹） |
| 2 | 拖 1 个文件夹到窗口 | 若在网站模式，切到资源模式并新增该项 |
| 3 | 拖多个文件（含 1 个重复） | 新增 N 个，跳过 1 个，状态栏文案正确 |
| 4 | 拖一个不存在的路径 | 提示"没有可用的文件或文件夹" |
| 5 | 按下全局快捷键 | 窗口在显示/隐藏间切换；焦点回到搜索框 |
| 6 | 在设置里录制新快捷键 | 录制中按 Esc 可取消；无修饰键时报错 |
| 7 | 把快捷键设成已被占用的组合 | 提示"已被其他程序占用"，不保存 |
| 8 | 点关闭按钮 | 窗口隐藏到托盘，进程仍在 |
| 9 | 托盘菜单"显示/隐藏" / "退出" | 分别正确；退出后进程消失、热键释放（再启动不冲突） |
| 10 | 二次启动 exe | 不产生第二个进程，已有窗口被唤到前台 |
| 11 | 勾选开机启动 → 重启系统 | 静默进托盘，无控制台闪窗 |
| 12 | 切换语言 zh↔en | 所有控件、表头、托盘菜单、设置窗口同步 |
| 13 | 中文路径拖入 + 打开 | 不乱码，能正确启动 |
| 14 | 失效路径 | 行标红，检测路径报告数量 |
| 15 | 路径含空格 / 中文的 `explorer /select` | 正确定位 |
| 16 | 高 DPI（125% / 150% 缩放） | 文字与控件不错位 |
| 17 | 写盘中途杀进程 | 数据文件不损坏（当前会，见 §4.2）|

---

## 6. 迁移风险与需要决策的点

### 6.1 高风险项

| # | 风险 | 说明 | 建议 |
|---|---|---|---|
| R1 | **全局热键归属** | 热键必须在原生消息循环线程注册。若 Python 后端变成无 UI 的子进程，它没有 Tk 消息循环了，现有实现（`:657-708`）直接失效，需要改用独立线程 + 自己的 `GetMessageW` 循环，或把热键交给 Flutter 侧处理 | 第 3 阶段前必须先定 |
| R2 | **托盘归属** | pystray 目前靠 `self.after()` 与 Tk 主循环桥接。去掉 Tk 后必须换成独立线程 + 线程安全队列 | 同上 |
| R3 | **双击/右键菜单的窗口依赖** | `messagebox.askyesno` 和 `filedialog` 是 Tk 模态对话框。后端进程里没有 Tk 窗口可依附 | 对话框全部搬到 Flutter 侧，后端只做纯粹的文件操作 |
| R4 | **数据文件覆盖风险** | §4.2 的静默覆盖路径 | 通信协议落地时顺手修 |
| R5 | **单实例与唤醒** | 现有互斥体 + 命名事件机制语义清晰，但 Flutter exe 会有自己的实例逻辑，两套并存可能打架 | 明确只有一层负责单实例 |
| R6 | **UI 全量重写的工作量** | 2916 行里超过 2000 行是 Tk 布局/样式代码，Flutter 侧要完全重写；能直接复用的只有 §4.3 列出的几个纯函数 | 按第 5 阶段"先只读页面"的顺序推进 |

### 6.2 关于通信协议（第 4 阶段预研）

现有业务特征偏简单：操作都是**短时、同步、本地文件读写**，没有长任务、没有流式进度、没有并发请求。

按"不为架构复杂而过度设计"的原则，**倾向选标准输入输出 JSON Lines**：

- 只读/短操作占绝大多数 → 不需要 HTTP 的路由/状态码/超时管理
- 没有并发压力 → 无需连接池
- 天然不用考虑端口冲突、回环监听、会话令牌、未授权本地请求
- 中文路径用 UTF-8 JSON 编码即可，注意显式设置子进程 stdio 编码（Windows 默认 `cp936` 会炸）
- 必须处理：协议消息走 stdout、日志走 stderr（或文件）；每请求带 `id` 关联响应；显式 `flush`

只有在出现"长时间任务 + 进度推送 + 前端可取消"这类需求时，才升级到命名管道或受保护的本机 HTTP。**当前功能清单里没有这类需求**（最长的是遍历 `Path.exists()`，毫秒级）。

### 6.3 需要你决策的问题

1. `export_current` / `import_current` 死代码：迁移时补上入口，还是从文档删除？
2. 托盘与全局热键最终由谁拥有——Flutter 前端，还是 Python 后端？
3. §4.2 的数据覆盖风险是否在本轮一并修复（会改变现有行为，虽然只影响"文件已损坏"这一路径）？
4. 环境：Flutter SDK 与 Windows SDK 的安装方式（见下节）。

---

## 7. 下一阶段计划

### 7.1 阻塞：先解决环境

> **2026-10-17 已解决**，见 §8。本节保留为当时的记录。

本阶段第 6 项任务（Flutter 原型）无法执行。需要补齐两件：

| 缺件 | 安装方式 | 估算 |
|---|---|---|
| Flutter SDK | `winget install --id Google.Flutter`，或 git clone stable 分支 | 下载约 1 GB，解压后约 3 GB |
| Windows 10/11 SDK | `winget install --id Microsoft.WindowsSDK.10.0.26100`，或用 VS Installer 给 `D:\Visual C++ Build Tools` 加装 | 约 1–2 GB |

装完必须跑 `flutter doctor -v` 确认三件事：
1. Flutter 与 Dart 版本号（记入文档，第 5 项任务）
2. Windows toolchain 是否识别到 MSVC（注意 §1.3 的 `vswhere.exe` 缺失问题）
3. `flutter doctor` 是否报告 Windows SDK 就绪

### 7.2 环境就绪后的原型验证项（第 6 项任务）

在一个**独立于本仓库的目录**建原型（不污染 `ResourceHub-GitHub-Ready`），只验证这些：

| 验证项 | 具体目标 |
|---|---|
| Material 3 | `useMaterial3: true` + 显式 `ColorScheme.fromSeed` |
| 明暗主题 | `themeMode` 三态（light/dark/system）实时切换 |
| 窗口尺寸 | 对齐现有 1280×820、最小 1180×760 |
| 中文字体 | `Microsoft YaHei UI` 在 Flutter 里的回退与渲染效果 |
| 图标 | 复用 `DesktopShortcut.ico` 生成 Windows 应用图标 |
| 滚动 | 长列表 + 滚动条行为 |
| 布局骨架 | 头部 + 左表单 + 右列表 三分区，能拖动缩放不错位 |
| 交互 | hover / focus / 主题切换的即时反馈 |

原型产出：可运行的 `flutter run -d windows` 截图或录屏 + 一份"实际效果 vs 现有 UI"对照说明。**没跑起来就不算通过**。

### 7.3 之后按原计划推进

第 2 阶段（Material 3 设计系统）→ 第 3 阶段（拆 Python 业务层，先补 §5.1/5.2 测试）→ 第 4 阶段（stdio JSON Lines 协议）→ 第 5 阶段（逐功能迁移，每步过 §5.4 手工清单）→ 第 6 阶段（打包与干净环境验证）。

---

## 8. 第一阶段执行结果（2026-10-17 当天后段完成）

本节是可执行状态的唯一权威记录，覆盖 §0 的"环境缺失"判断与 §7.1 的阻塞结论。

### 8.1 环境最终状态

`flutter doctor -v` 只红一项，且与 Windows 桌面端无关：

| 组件 | 状态 | 位置 |
|---|---|---|
| Flutter 3.47.7 stable / Dart 3.13.5 | ✓ | `F:\flutter` |
| Windows 11 25H2（10.0.26200） | ✓ | — |
| Visual Studio 生成工具 2022 17.14.42 | ✓ | `F:\VS2022-BuildTools` |
| └ Windows SDK 10.0.26100.0 | ✓ | `C:\Program Files (x86)\Windows Kits\10` |
| Connected devices | ✓ | Windows desktop / Chrome / Edge |
| Network resources | ✓ | — |
| Android toolchain | ✗ | **无关，永久忽略** |

环境变量（用户级、永久）：`Path` += `F:\flutter\bin`、`PUB_CACHE=F:\pub-cache`、`FLUTTER_ROOT=F:\flutter`。

**排查陷阱**：Flutter 调用 vswhere 的参数是 `-format json -products * -utf8 -latest`（`visual_studio.dart:350`）。手工执行 vswhere **不带 `-products *`** 时查不到 Build Tools 产品，会误判为"未安装"。

**C 盘占用**：唯一落在 C 盘且无法搬移的是 Windows SDK **2.5 GB**（安装根路径由注册表 `KitsRoot10` 硬编码，迁移需管理员权限）。Flutter SDK 5.4 GB、pub cache 1.5 GB、VS Build Tools 4.4 GB 全在 F 盘。VS 另往 C 盘写入 `vswhere.exe`（469 KB）。C 盘可用空间 76 GB，与开工前基本持平。

### 8.2 原型验证结果（§7.2 八项，全部实测通过）

原型位置：`F:\ResourceHub-Flutter-Prototype`（**在仓库之外**，未污染 `ResourceHub-GitHub-Ready`）。

| 验证项 | 实测结果 |
|---|---|
| 窗口默认尺寸 | client `1600×1025` 物理 @125% DPI = **1280×820 逻辑**，与 `geometry("1280x820")` 语义一致 |
| 最小尺寸 | 强行缩至 400×300 → 被夹在 **1180×760 逻辑**，与 `minsize(1180,760)` 一致 |
| 中文字体 | 标题栏「常用资源工具」与界面中文全部正常 |
| Material 3 | `useMaterial3` + 显式 `ColorScheme.fromSeed(0xFF2F6FED)`，亮/暗双主题 |
| 主题三态切换 | 浅色 / 跟随系统 / 深色，点击即时生效 |
| 图标 | `DesktopShortcut.ico` 已替换进 runner |
| 滚动 | 滚轮驱动长列表，常显滚动条，hover / 选中态正常 |
| 交互 | SegmentedButton、输入框、卡片、Chip、状态底栏均可用 |

构建：debug 65.2 s、release 37.9 s 均通过；release 产物 `resource_hub_proto.exe` 97 KB + `flutter_windows.dll` 21 MB。

**过程中修掉的一个真缺陷**：左侧表单与右侧列表两个 `ListView` 同时挂在 `PrimaryScrollController` 上，触发 Scrollbar 断言 `attached to more than one ScrollPosition`。已改为给列表显式持有 `ScrollController`。**第 2 阶段搭真实列表时会再次遇到同一问题。**

**DPI 语义结论（第 2 阶段可直接沿用）**：Tkinter 未声明 DPI 感知，`geometry()` 数值是"逻辑像素"；Flutter 侧 `Win32Window::Size` 同样按逻辑像素处理。原型在 `windows/runner` 中实现的 client→outer 换算（`AdjustWindowRectExForDpi`）与 `WM_GETMINMAXINFO` 最小尺寸强制**可直接搬入正式版**。

### 8.3 能力边界（避免高估进度）

原型是**纯视觉空壳**。`F:\ResourceHub-Flutter-Prototype\lib\main.dart` 共 498 行，全文**不含** `File(` / `Directory(` / `json` / `http` / `socket` / `Process` —— 零文件 I/O、零网络、零子进程。

- 80 条记录由 `List.generate` 现造（`D:\Workspace\archive\item_N`），**不读** `sites.json` / `folders.json` / `settings.json`
- 「保存」只弹 SnackBar（"原型，不落盘"）；「设置」与「选择自定义图标」是空函数 `{}`
- 分类下拉写死五项，不识别用户自定义分类
- 无 Python 后端、无 IPC、无托盘、无全局热键、无拖拽入窗、无右键菜单、无双击打开、无中英切换、无导入导出、无单实例保护

**已就绪且可复用的只有三样**：窗口尺寸/最小尺寸的 native runner 代码、Material 3 主题方案与种子色、字体与图标配置。
**迁移主体（拆业务层、定通信协议、迁托盘与全局热键）一行未动。**

### 8.4 本次新增发现

1. **原应用可能缺少单实例保护**。实测到两个 `ResourceHub.exe` 同时运行（`--startup-hidden`，PID 21816 / 21876，启动时间相差 1 秒）。若确实如此，会产生重复托盘图标，且全局热键 `Ctrl+Space` 只能被其中一个进程抢到。**这使 §6.1 的"热键归属"风险升级：第 2 阶段确认归属时，必须一并决定是否需要单实例保护。** 尚未确认这是设计行为还是启动脚本重复触发。
2. 见 §8.1 的 vswhere `-products *` 排查陷阱。

### 8.5 待决策问题（阻塞第 2 阶段）

同 §6.3，三项均未决：

1. `export_current`（`:2827`）/ `import_current`（`:2841`）是死代码，但 `README.md:14` 宣称有导入导出 → 补 UI 入口，还是删掉该说法？
2. 托盘 + 全局热键（`Ctrl + Space`）归 Flutter 还是归 Python 后端？**最大架构岔口，选错会导致第 4 阶段返工。**
3. §4.2 的数据覆盖风险（解析失败即以示例数据覆盖用户文件）→ 本轮修复，还是先冻结现状？

### 8.6 仍未验证

- 托盘 / 全局热键在**无 Tk 消息循环**时能否存活 —— 第 2 阶段核心风险，本阶段刻意未触碰
- 多显示器跨屏拖动时的 DPI 切换行为
- 长时间运行的稳定性（内存 / 句柄泄漏）—— 只做了功能实测，未做持续观察

---

## 附：本次审计的边界

**已完整阅读**：`resource_hub.pyw`（2916 行全文）、`README.md`、`requirements-python.txt`、`start-resource-hub-python.bat`、`ResourceHubPython.spec`、`build/resourcehub-onefile-specs-1818/ResourceHub.spec`、`build-resource-hub-python.ps1`、两个 `release/*/README.md`、`settings.json`、`sites.json` 与 `folders.json` 的结构。

**未做**：
- 未运行现有 EXE 或源码程序（只做静态审计，不启动 GUI 进程）
- 未逐字节校验 `build/` 下 PyInstaller 的 `.toc` 分析产物
- 未检查 `Install-ResourceHub-*.vbs`、`start-resource-hub-python.vbs` 的具体实现内容
- 未验证 §5.4 中的任何一条手工场景（这些本来就该在真实桌面上做）

**未修改任何既有仓库文件**（本文档 `migration/phase1-audit.md` 为新增，是本次唯一的仓库写入）。

---

## 9. 勘误（Phase 2 接手复核，2026-10-17）

Phase 2 开工前对本文档的技术结论做了复核，**一处判断需要更正**，其余保持不变。

### 9.1 R1「全局热键归属」的代码事实有误

本文档 §6.1 R1 称现有热键实现"直接失效，需要改用独立线程 + 自己的 `GetMessageW` 循环"。实际复核 `GlobalHotkeyListener`（`:657-708`）：

- `:670` 起独立线程 `ResourceHubHotkey`
- `:677` 先 `PeekMessageW` 强制创建线程消息队列
- `:678-682` 在该线程内 `RegisterHotKey(None, ...)`
- `:688-694` 该线程自持 `GetMessageW` 循环接收 `WM_HOTKEY`
- `:706` 用 `PostThreadMessageW` 停止，`finally` 中注销

**热键从未依赖 Tk 的消息循环**。`self.after(0, ...)` 只出现在托盘回调（`:1328`、`:1331`），属于 R2 范畴。

### 9.2 §8.6 的首个未验证项已关闭

用 `migration/probes/probe_headless_tray_hotkey.py` 在**不创建 Tk root** 的进程里直接加载真实模块，7 项探针全部通过：热键注册、`WM_HOTKEY` 投递、注销、同组合重注册、托盘 `run_detached()` 可见、单实例互斥体、导入不产生 Tk root。

### 9.3 §8.5 三项待决问题的结论

见 `migration/adr/ADR-001-tray-hotkey-ownership.md`：

| 问题 | 结论 |
|---|---|
| 托盘 + 全局热键归属 | 归 Python 后端；Flutter 只做 UI，通过 IPC 订阅事件 |
| `export_current` / `import_current` 死代码 | 保留能力，Phase 5 补 UI 入口（`STRINGS` 里 `export` / `import` 键本已存在） |
| §4.2 数据覆盖风险 | 修复：临时文件 + `os.replace`、解析失败拒绝覆盖、写前 `.bak` 备份 |

### 9.4 复核未覆盖的部分

§1 环境表、§3 功能清单、§5 测试方案、§8.2 原型验证结果**均未重新验证**，仍以原文为准。§5.2 中"空文件/损坏 JSON → 返回 `[]`"的用例需按 ADR-001 D3 改写为"断言拒绝覆盖"。

