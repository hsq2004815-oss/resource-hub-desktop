# Phase 5b — 补齐壳层功能

- 日期：2026-10-17
- 前置：`migration/phase5-ui-wiring.md`（Phase 5 主链路）、`migration/adr/ADR-002-native-shell-ownership.md`
- 原应用 `resource_hub.pyw` **未修改**

---

## 1. 结论

Phase 5 的"未接通清单"已清零，应用具备与旧版对等的桌面壳层能力：

| 功能 | 结果 |
|---|---|
| 关闭按钮 → 隐藏到托盘（进程存活） | ✅ 实机验证 |
| 托盘图标 + 菜单（显示/隐藏、退出），菜单文案随语言 | ✅ 实机验证 |
| 全局热键 → 窗口显隐 + 搜索框聚焦 | ✅ 实机验证（后端注册，前端编排） |
| 拖拽文件/文件夹入窗 → 新增资源 | ✅ 实机验证（`WM_DROPFILES` 写入 `folders.json`） |
| 选择文件夹 / 选择文件按钮 | ✅ 原生对话框实测 |
| 导入 / 导出（JSON 备份，格式兼容旧版） | ✅ 单元测试 + 真实对话框 |
| 开机启动开关（启动目录 `.lnk`，静默进托盘） | ✅ 原生探针实测创建/删除 |
| 单实例：二次启动唤醒已有窗口 | ✅ 实机验证（进程数不变、窗口被唤出） |
| 热键录制 + 占用检测 | ✅ 测试覆盖 + 实机链路（后端 probe） |
| 打开文件夹/文件/网站、在资源管理器中定位 | ✅ runner 原生 `ShellExecuteW` / `SHOpenFolderAndSelectItems`（`native-shell-probe open/reveal`）；打开时把前台权让给 shell，避免新窗口开在应用后面 |

| 验证项 | 结果 |
|---|---|
| Flutter 测试 | **32 / 32**（22 外壳 + 7 后端端到端 + 3 JSON 备份） |
| 后端测试 | **138 / 138** |
| `flutter analyze` | 0 issue |
| 实机壳层 QA（`verify_shell.py`） | **9 / 9 通过** |
| 原生壳层探针（`native_shell_probe.cpp`） | 对话框可打开/返回路径；启动快捷方式可建可删；`open`/`reveal` 返回成功并唤起资源管理器 |
| 打包版干净环境（`verify_release.py`） | 见 `phase6-packaging.md` |

---

## 2. 架构

```
Flutter (resource_hub.exe)
  ├─ home_page.dart ── ResourceApi ── JSON Lines ──> Python 后端（数据、热键注册）
  │     │                                            └─ event: hotkey
  │     ├─ WindowControl ──┐
  │     └─ NativeShell ────┤  method channel `resource_hub/window`
  │                        ▼
  └─ windows/runner (C++)
        ├─ flutter_window.cpp  托盘 / WM_CLOSE→隐藏 / 显示·隐藏 / topmost 抢前台
        │                      WM_DROPFILES → 反向调用 Dart `dropPaths`
        ├─ native_shell.cpp    IFileOpenDialog / IFileSaveDialog / Startup .lnk
        └─ main.cpp            单实例互斥体 + `ResourceHub.ShowWindow` 唤醒消息
```

**归属裁定见 ADR-002**：托盘/窗口/对话框/开机启动/单实例归 Flutter runner；全局热键仍归 Python 后端（维持 ADR-001 D1），只把按键事件交给前端编排。

---

## 3. 关键实现

### 3.1 托盘与窗口

- `InstallTray()` 用 `Shell_NotifyIconW`；图标复用 `IDI_APP_ICON`（`Runner.rc`）。
- 左键单击/双击托盘 → `ToggleVisibility()`；右键 → `TrackPopupMenu`（显示/隐藏、退出）。
- 关闭按钮 `WM_CLOSE` → `HideToTray()`（`SW_HIDE`），不退出；`quitting_` 时放行。
- `ShowFromTray()` 保留旧应用的 **topmost 闪一下 + `SetForegroundWindow`** 技巧，否则 Windows 拒绝把后台进程调到前台（`resource_hub.pyw:1437`）。
- 托盘菜单文案由 Dart 通过 `setTrayLabels` 推送，语言切换即时生效。

### 3.2 热键：注册在后端，编排在前端

- 后端 `hotkey.start` 注册并回 `HotkeyStatus{registered,label,reason}`；按键经 `event: hotkey` 推给前端。
- 前端收到事件 → `WindowControl.toggle()` → 变可见时 `_searchFocus.requestFocus()`。
- **录制**（设置对话框）：先 `hotkey.stop()` 释放旧组合（旧应用录制时热键仍生效，按到旧组合会把窗口藏起来）→ 捕获按键 → `settings.probeHotkey` 试注册 → 可用则保存并让 `main.dart` 重新 `hotkey.start`；不可用显示 `hotkey_in_use`。
- 组合键名映射在 `lib/util/hotkeys.dart`，与后端 `parse_hotkey_id` 的词汇表一致（26 个特殊键 + A–Z/0–9 + F1–F24 + 符号键）。

### 3.3 拖拽

- runner 对顶层窗口和 Flutter view 子窗口都调用 `DragAcceptFiles`；`WM_DROPFILES` 里用 `DragQueryFileW` 取路径（UTF-16 → UTF-8），通过通道反向调用 Dart 的 `dropPaths`。
- Dart 合并到 `NativeShell.drops` 流；`HomePage._handleDropPaths` 调 `resources.drop`（后端固定写 `folders.json`），成功后切到资源模式并刷新列表。
- 状态文案与旧版一致：`drop_added` / `drop_added_skipped` / `drop_switched` / `drop_invalid`；后端负责路径有效性、去重与"输入反序"等旧行为。

### 3.4 文件对话框与导入导出

- `native_shell.cpp` 用 `IFileOpenDialog` / `IFileSaveDialog`（COM STA，`main.cpp` 已初始化）：
  - `pickFolder`（`FOS_PICKFOLDERS`）
  - `pickFile`（任意文件，表单路径选择）
  - `pickJsonFile`（`*.json` 过滤，导入）
  - `saveFile`（`FOS_OVERWRITEPROMPT` + 默认文件名）
- 导入导出按钮加在列表工具栏；文件格式保持旧版 `json.dumps(..., ensure_ascii=False, indent=2)` UTF-8，`lib/util/json_backup.dart` 专门负责读写并可单测。
- 导入语义沿用旧版：**替换**当前集合（不是合并），后端复用旧去重规则；失败显示 `import_failed`。

### 3.5 开机启动

- `native_shell::SetLaunchAtStartup` 用 `IShellLinkW` + `IPersistFile` 写
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Resource Hub.lnk`，目标为当前 exe，参数 `--startup-hidden`。
- runner 检测到该参数时**不调用 `Show()`**，启动即驻留托盘；托盘不可用时退回"直接退出"，避免不可达进程。
- 设置开关持久化到 `settings.json`；启动时若 `launchAtStartup=true` 会补建缺失的快捷方式（但不会在启动时删除它，避免 dev/release 互相踩）。

### 3.6 单实例

- `main.cpp` 创建命名互斥体 `Local\Mytools.ResourceHub.Flutter`；已存在时向已有窗口 `PostMessage(ResourceHub.ShowWindow)`（`RegisterWindowMessage`），然后退出。
- 已有实例收到消息 → `ShowFromTray()`（含置前与聚焦），不产生第二个后端进程、不会抢热键。
- 毫秒级竞态（第二实例早于第一实例建窗）时第二实例静默退出，第一实例正常启动。

---

## 4. 过程中发现并修复的缺陷

| # | 缺陷 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | 状态栏 `_Status.args` 从未传进文案模板，`{0}` 原样显示（如"已添加 {0} 个资源"） | 新增拖拽测试断言状态文案 | `_Status.resolve` 改为 `strings.tx(key, args)` |
| 2 | 设置对话框用父组件快照渲染开关，切换后 UI 不刷新（原有代码的隐患） | 重写对话框时审查发现 | 改为 StatefulWidget + 本地 `_settings` 快照 |
| 3 | 录制热键时旧热键仍生效，按旧组合会隐藏窗口 | 录制链路设计时对照旧应用 | 录制期间 `hotkey.stop()`，结束/保存后重启 |
| 4 | 从 Release 目录启动找不到 `backend/main.py` | Phase 5 已知 | Phase 6 打包后 `BackendBootstrap` 自动发现 `backend\resource_hub_backend.exe` |
| 5 | `flutter test` 中真实文件 IO 永远不完成（fake-async 无真实事件循环） | 导出/导入的 widget 测试挂死 | 文件 IO 拆到 `JsonBackup`，用普通 `test` 覆盖；widget 测试只测入口 |
| 6 | **`settings.json` 损坏（如 UTF-8 BOM）会让后端启动即崩**，与 `settings.py` 文档承诺的"设置永不 brick 应用"相悖 | 实机演示时手写带 BOM 的设置文件，后端抛 `CorruptDataError`、前端只看到"后端已退出" | `SettingsStore.load` 捕获 `CorruptDataError` 回退默认值并**保留原文件**不动；新增回归测试（后端 → 138） |
| 7 | **设置里语言/主题只能单向切换**：切到 English 后点"简体中文"无反应（主题同理） | 用户实机反馈"选了英文改不回去" | 根因：对话框把打开时的 `language`/`themeMode` 快照当作 `SegmentedButton.selected`；切换后快照过期，而 M3 的 `SegmentedButton` 对"已选中项"的点击直接忽略 → 回切点不动、再点另一项又因目标语言未变被上层 guard 吞掉。改为用**当前环境语言**（`context.l10n.language`）与本地 `_themeMode` 状态渲染选中项；补双向切换回归测试（Flutter → 29） |
| 8 | **打开文件夹/网站后窗口出现在应用后面**（需手动切换） | 用户实机反馈 | 根因：打开动作由后台 Python 子进程执行（`os.startfile` / `webbrowser`），非前台进程不能把新窗口前置（Windows 前台锁定）；旧版单进程无此问题，属迁移引入。改为 **runner 原生打开**（`ShellExecuteW` / `SHOpenFolderAndSelectItems`，调用前 `AllowSetForegroundWindow(ASFW_ANY)`），后端 `resources.open/reveal` 保留 fallback；补 fallback widget 测试（Flutter → 29） |
| 9 | **真实拖拽文件夹到窗口没有任何反应**（早期 `verify_shell` 却是 PASS） | 用户实机反馈 | 根因：`FLUTTERVIEW` 子窗口覆盖整个客户区，Explorer 把 `WM_DROPFILES` 投递给**子窗口**；子窗口只注册了 `DragAcceptFiles`，但它的 WndProc 是 Flutter 引擎的，不处理该消息 → 静默丢弃。而 `verify_shell.py` 之前直接向**顶层窗口** PostMessage，绕过了真实投递路径，所以测试假绿。修复：runner 用 `SetWindowLongPtrW` **子类化 FLUTTERVIEW 的 WndProc**，把 `WM_DROPFILES` 转发给 `FlutterWindow::HandleDroppedFiles`（引擎重建 view 时自动重新挂接、销毁时还原）；`verify_shell.py` 改为向子窗口投递（真实路径），已通过 |

第 5 条值得记：**widget 测试的 fake-async 没有真实事件循环**，`dart:io` 的 Future 不会完成；
涉及文件、进程、网络的逻辑必须移到普通 `test` 或用 `tester.runAsync`，否则表现为"测试挂死"而不是报错。

第 6 条值得记：**设置文件属于"偏好"而非"数据"**，解析失败必须降级为默认值而不是终止进程；
`json.loads` 不接受 UTF-8 BOM，而 Windows 记事本/`Set-Content -Encoding UTF8`（PowerShell 5）都会写 BOM——
这是用户手工编辑设置时非常容易踩到的路径。

---

## 5. 验证方法（可复现）

```powershell
# 1. 静态 + 单元/外壳测试
cd app
$env:PATH = "F:\flutter\bin;$env:PATH"
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:NO_PROXY="localhost,127.0.0.1"
flutter analyze
$env:RH_PYTHON = "D:\miniconda3\python.exe"   # backend_client_test 用
flutter test

# 2. 后端
cd ..\backend
D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 3. 实机壳层（关闭→托盘、热键、二次启动、拖拽）
cd ..
D:\miniconda3\python.exe migration\tools\verify_shell.py

# 4. 原生对话框 / 启动快捷方式（vcvars64 环境）
cmd /c build\runner-tests\build-probe.bat
build\runner-tests\native-shell-probe.exe startup
build\runner-tests\native-shell-probe.exe folder
build\runner-tests\native-shell-probe.exe save
```

截图证据：`migration/screenshots/phase5b-shell-start.png`（启动）、`phase5b-shell-drop.png`（拖拽后状态栏"已添加 2 个资源"）。

---

## 6. 未做 / 风险

- **无代码签名**：SmartScreen 首次运行会提示"未知发布者"。
- **高 DPI / 多显示器 / 长时运行句柄泄漏**仍属手工清单项（审计 §5.4 第 15–17 项），本轮未逐项复核。
- **UI 自动化受限**：Flutter Windows 的 UIA 树在本机只暴露 `FLUTTERVIEW`（semantics 未开启），无法用 UIA 点击按钮；因此对话框/录制改用"原生探针 + widget 测试 + 窗口消息"组合验证，未做端到端点击自动化。
- 托盘菜单只有"显示/隐藏、退出"两项，与旧版一致；旧版的隐藏/显示 alpha 动画未迁移（功能等价，无动画）。
