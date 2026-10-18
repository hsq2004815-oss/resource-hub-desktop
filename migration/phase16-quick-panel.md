# Phase 16 — 快捷键直达树状图（快速面板 HUD）

- 日期：2026-10-18
- 触发：用户提出「按快捷键没必要把整个页面全部显示出来，我们直接不同的快捷键显示对应的网页或者文件夹的树状图」；
  举例 `Ctrl+K` 单击显示网页树、连续按两下显示文件夹树，先讨论设计再实现。
- 范围：新增「快速面板」窗口形态 + 三组全局热键 + 两棵竖向树；不改数据格式、不改主界面信息架构。

---

## 1. 设计结论（与用户逐项确认）

讨论时逐项确认，最终选型：

| 问题 | 结论 |
|---|---|
| 快捷键方案 | **两个独立键**：`Ctrl + Alt + Shift + L` 网站树、`Ctrl + Alt + Shift + F` 文件夹树；原 `Ctrl + Alt + Space` 保留给完整窗口；三个都可在设置里录制 |
| 窗口形态 | **主窗口"变身"成 HUD**（同一 Flutter 引擎，无第二窗口/插件） |
| 树的样式 | **竖向树 / 大纲**（紧凑、键盘友好；不用横向 mind map） |
| HUD 交互 | **带搜索框，输入即过滤；Enter/单击直接打开目标**，打开后自动收起 |

### 为什么否掉了"同一个键按两下切树"

1. **全局热键是系统独占的**：`RegisterHotKey` 一旦抢到 `Ctrl+K`，Chrome/Edge 地址栏搜索、VS Code
   命令前缀等都会失灵 —— 这个应用的核心用途就是开网页，抢 `Ctrl+K` 尤其伤。
2. **双击判定天然有歧义**：第一下必须立刻响应，第二下只能靠 ~300ms 时间窗 + "面板已打开"状态来切换；
   能实现，但用户记不住、无法自助发现，按快了/按慢了行为都不直观。
3. 想"一个键"的诉求由 **HUD 内 `Tab` 切换两棵树**满足，零延迟、零学习成本；
   两个独立键则保证"按一下直达对应树"。

### 默认键位的实测修正

初版默认 `Ctrl + Alt + L` / `Ctrl + Alt + F`，实机状态栏报「被其他程序占用」。
用 `is_combination_available` 逐项探测后确认本机确实已被其他程序占用（`Ctrl+Alt+Space` 归本应用），
因此默认改为 **`Ctrl + Alt + Shift + L/F`**（已探测空闲），仍是用户可自行录制的普通热键。
`Ctrl+K` / `Ctrl+Shift+F` 这类浏览器/编辑器常用组合刻意不用。

---

## 2. 交互规格

- **三组热键**（均可关、可录制、有冲突检测）：
  - `Ctrl + Alt + Space`：完整窗口显示/隐藏（原行为不变）；
  - `Ctrl + Alt + Shift + L`：快速面板 · 网站树；
  - `Ctrl + Alt + Shift + F`：快速面板 · 文件夹树。
- **HUD 形态**：480×600 逻辑像素，居中偏上（工作区 12% 高度），无边框、置顶、不进任务栏；
  高 DPI 按窗口 DPI 换算；Win11 走 DWM 圆角（旧系统退化为方角）。
- **开关规则**：
  - 同一组热键再按一次 = 收起；
  - 另一组快速热键 = 原地切换树（不重新缩放窗口）；
  - 面板内 `Ctrl+Alt+Space` = 展开为完整窗口；
  - `Esc` / 点其他窗口（失焦）/ 托盘图标 / 二次启动 / Alt+F4 = 收起；
  - **收起后回到打开前的状态**：原本窗口可见 → 还原完整窗口；原本在托盘 → 回到托盘。
- **键盘**：输入即过滤（`↑↓` 选择、`Enter` 打开、`→` 展开、`←` 收起、`Esc` 关闭、`Tab` 切树）；
  IME 组合输入期间不拦截按键（中文输入法候选窗可用）。
- **单击行为**：
  - 网站行 = 浏览器打开；文件夹资源行 = 资源管理器打开；
  - 文件夹资源左侧箭头 = 懒加载展开真实子目录；
  - 真实目录内的子项：单击文件夹 = 展开/收起，单击文件 = 默认程序打开；
  - 路径缺失的资源显示红色感叹号（沿用主界面 `PathState`）。
- **树内容**：`分类 → 资源` 两级；文件夹树可继续展开到真实文件系统（`fs.children`，只读、深度上限 8，
  junction/symlink 不展开以避免环）。空分类不显示；未分类置底；搜索态变为扁平结果（带路径副标题）。

---

## 3. 实现

### 3.1 后端（`backend/resource_hub_core/`）

- `settings.py`：新增 `quick_links_hotkey_id` / `quick_folders_hotkey_id`，
  `to_json` 键 `quickLinksHotkeyId` / `quickFoldersHotkeyId`；沿用 `parse_hotkey_id` 规范化，
  非法值回落默认值（手改 settings.json 不会崩）。
- `protocol.py`：`ServerState.hotkey` 改为 `list[GlobalHotkeyListener]`；`hotkey.start` 同时注册
  3 个 listener（各自独立线程/消息泵），事件带动作：
  `{"event":"hotkey","payload":{"action":"toggle" | "quickLinks" | "quickFolders"}}`；
  返回值新增 `registrations` 数组（每个动作的 label / registered / reason），旧字段保持不变；
  `hotkey.stop` / `app.shutdown` 停止全部。某个组合被占用不影响另外两个。
- 单测 +5：默认值、规范化、to_json 往返、settings.get/set、disabled 路径的三条 registrations。

### 3.2 Windows runner（`app/windows/runner/flutter_window.cpp`）

新增 `enterQuickMode` / `exitQuickMode` / `isQuickMode` 通道方法：

- 进入：保存 `GWL_STYLE` / `GWL_EXSTYLE` / 窗口 rect / 可见性（最小化先 `SW_RESTORE`），
  去掉 `WS_CAPTION|WS_THICKFRAME|WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_SYSMENU`，加 `WS_POPUP` 与
  `WS_EX_TOOLWINDOW`；`SetWindowPos(HWND_TOPMOST, 居中偏上, 480×600×DPI)`；DWM 圆角属性 33；
  topmost 闪一下再 `SetForegroundWindow`（Windows 前台锁定）。
- 退出：恢复样式/位置/置顶，原本可见则显示完整窗口（不抢前台），原本隐藏则 `SW_HIDE`。
- 关闭信号：`WM_ACTIVATE(WA_INACTIVE)`、HUD 态 `WM_CLOSE`、托盘点击、二次启动 → 反向调用
  Dart `quickDismissed`，由 Dart 恢复界面并调用 `exitQuickMode()`。

### 3.3 Flutter

- `features/quick/quick_panel.dart`（新）：竖向树 HUD。`分类` 表头、资源行、真实目录懒加载行、
  搜索过滤、hover/选中、键盘导航（`HardwareKeyboard` 级拦截，避免被搜索框吞掉）、
  展开状态与 `fs.children` 缓存、错误行。
- `features/home/home_page.dart`：`_quickMode/_quickKind/_quickReturnVisible`；
  热键事件分流；`_buildQuick()` 渲染面板；打开资源前先收起 HUD 再走原 `_openResource`
  （保留 runner 的前台交接）；状态栏汇总不可用热键。
- `platform/window_control.dart`：`enterQuickMode/exitQuickMode` 发送端；
  `platform/native_shell.dart`：**唯一**持有 `resource_hub/window` 反向 handler，
  暴露 `quickDismissals`（两个 `setMethodCallHandler` 会互相覆盖，这个坑写进注释与记忆）。
- `features/home/settings_dialog.dart`：`_hotkeyRow` 复用三行录制器（完整窗口 / 网站树 / 文件夹树），
  录制期间停止全部热键；同键重复使用当场报错；关闭开关时三行显示 `—`。
- `backend_models.dart`：`AppSettings` 两个新字段 + 默认常量；`HotkeyStatus.registrations`。
- i18n：`app_strings_ext.dart` 新增快速面板/设置/冲突提示等键（zh/en 同步）。

---

## 4. 验证

| 项 | 结果 |
|---|---|
| `flutter analyze` | 0 issue |
| Flutter 测试 | **59 / 59**（+6 HUD 行为，+3 关闭顺序回归：见 §7） |
| 后端测试 | **172 / 172**（1 个 symlink skip；基线 167 +5） |
| `verify_shell.py` | 9 / 9 PASS（关窗→托盘、全局热键、二次启动、拖放不受影响） |
| `verify_quick_panel.py`（新增实机脚本） | **7 / 7 PASS**（读取 `settings.json` 里的实际热键） |

`verify_quick_panel.py` 的实测输出（120 DPI，逻辑 480×600 → 物理 600×750）：

```text
PASS normal_window_baseline       frameless=False 1618x1072
PASS quick_links_hotkey_opens_hud frameless=True toolwindow=True 600x750 foreground=True
PASS escape_restores_full_window  frameless=False 1618x1072 foreground=True
PASS quick_folders_hotkey_opens_hud frameless=True toolwindow=True 600x750
PASS legacy_toggle_still_hides    visible=False
PASS quick_hud_opens_from_tray    frameless=True visible=True 600x750
PASS escape_returns_to_tray       visible=False
```

截图（`migration/screenshots/`）：

- `phase16-quick-links.png`：网站树，选中行高亮；
- `phase16-quick-search.png`：输入 `Git` 后的扁平过滤结果（含 URL 副标题）；
- `phase16-quick-folders-expanded.png`：文件夹树展开真实目录（懒加载）；
- `phase16-quick-links-from-tray.png`：窗口在托盘时热键直接拉起 HUD；
- `phase16-settings-hotkeys.png`：设置里三行快捷键（完整窗口 / 网站树 / 文件夹树）；
- `phase16-dismiss-fixed.png`：点击面板旁边收起后，完整窗口正常还原（§7 修复后的截图）。

---

## 5. 已知限制 / 后续可做

- HUD 尺寸固定 480×600，暂不可拖拽改大小；多显示器时跟随鼠标所在显示器居中。
- 主界面与 HUD 共用一个窗口/引擎：HUD 打开时完整窗口会被临时收起（收起后恢复），这是
  "不引入第二个 Flutter 引擎/多窗口插件"的代价；若以后要"HUD 与完整窗口同时显示"，需要独立小窗。
- 上次浏览的树/展开状态不跨会话保存（每次打开都是折叠态）。
- 默认键位是 4 键组合（本机 `Ctrl+Alt+L/F` 被占用）；用户可在设置里换成任何空闲组合。
- Windows 10 没有 DWM 圆角，HUD 为直角窗口（内容布局不受影响）。

## 6. 复现

```powershell
# 后端
cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 前端
cd ..\app; flutter analyze; flutter test

# 实机（先启动 release 里的 resource_hub.exe）
cd ..; D:\miniconda3\python.exe migration\tools\verify_quick_panel.py
```

---

## 7. 修复记录 — Phase 16.1：点击面板旁边出现黑色大窗口（用户反馈）

**现象**：HUD 弹出后点击旁边（失焦自动收起）时，窗口会偶发变成整个正常大小、四周纯黑、
中间还残留着树面板的截图状态。

**根因**（两个顺序问题叠加）：

1. runner 的 `ExitQuickMode()` 在窗口仍然可见时就把保存的完整尺寸/边框还原了 —— 窗口先放大，
   而 Flutter 引擎的下一次绘制还没发生，于是露出了未绘制的黑色区域和上一帧 HUD 内容；
   如果收集前完整窗口在托盘里，之后还会立刻 `SW_HIDE`，看起来就是"闪一下黑色大窗口"。
2. Dart 侧先 `await exitQuickMode()` 再 `setState` 切回完整界面，所以窗口放大那一刻 UI 还是 HUD。

**修复**：

- runner `ExitQuickMode(int visibility)` 增加可见性参数（`auto` / `show` / `hide` 对应 0/1/2）：
  - 需要隐藏时（`hide`，或 `auto` 且打开 HUD 前窗口不可见）**先 `SW_HIDE` 再恢复样式/尺寸**，
    屏幕上不会出现放大后的 HUD 窗口；
  - 恢复后调用 `flutter_controller_->ForceRedraw()`，尽快产出新帧。
- Dart `_closeQuick()` 按场景重排：
  - 托盘 → 托盘：`exitQuickMode(hide)` 先让面板消失，再 `setState` 重建完整界面（窗口保持隐藏）；
  - HUD 内按完整窗口快捷键：`exitQuickMode(hide)` → `setState` → `WindowControl.show()`；
  - 原窗口可见：先 `setState` + 等一帧（`endOfFrame`，120 ms 上限兜底），再 `exitQuickMode(auto)`
    放大窗口，避免用旧帧放大；
  - 进入 HUD 时不等待重绘，立即缩小，避免面板在大窗口里闪现。
- `verify_quick_panel.py` 改为从 `resource_hub.exe` 同目录的 `settings.json` 读取**用户实际配置的**
  三组热键（再按 VK 映射注入），而不是假设默认值；测试时先点击 HUD 搜索框让窗口取得前台，
  这样合成的 Esc/方向键才能到达应用。

**验证**：

| 项 | 结果 |
|---|---|
| Flutter 测试 | **59 / 59**（新增 3 个：托盘关闭先 hide、可见窗口关闭先重绘再 auto、HUD 内展开先 hide 再 show） |
| 实机 1 kHz 采样 | 托盘场景：点击旁边后 **< 5 ms 窗口即隐藏**，无任何"大窗口可见"帧；可见窗口场景：窗口恢复后 1–2 ms 内出现正确界面，无持续黑窗 |
| `verify_quick_panel.py` | 7 / 7 PASS（使用用户配置的 `Ctrl+Shift+G` / `Ctrl+Shift+V`） |
| 回归 | `verify_shell.py` 9 / 9 PASS；后端 172 / 172 |

截图：`migration/screenshots/phase16-dismiss-fixed.png`（点击旁边收起后完整窗口正常还原）。

---

## 8. 修复记录 — Phase 16.2：焦点/空白点击/行高亮闪烁（用户反馈）

**反馈**：① 弹出面板后焦点在搜索框，点击空白页无法直接关闭；② 用鼠标选择文件夹/网页时
有明显的黑色阴影闪烁。

**根因**：

1. **前台激活不可靠**：全局热键由 Python 后端进程注册，Flutter 进程没有前台权；`SetForegroundWindow`
   在另一个前台程序（如记事本）存在时会被系统拒绝，于是 HUD 窗口虽然出现，但系统焦点仍在原程序 ——
   点击桌面/别的窗口不会让我们收到 `WM_ACTIVATE(WA_INACTIVE)`，所以不会自动关闭；Esc/输入也不可靠。
2. **行内的 Material ink**：`InkWell` 默认的 hover/highlight 是 `onSurface` 深色（8%–12%），而行背景是用
   `AnimatedContainer` 从透明渐变到浅蓝（120 ms），渐变期间深色 ink 会透出来 → 鼠标扫过/点选时看到
   "黑色阴影闪烁"。
3. 之前没有"点击面板内空白处关闭"的行为，只有失焦自动关闭。

**修复**：

- runner 新增 `ForceForeground()`：topmost 闪一下 + `SetForegroundWindow`，仍失败则用
  `AttachThreadInput` 借用当前前台线程的输入队列再取前台；HUD 打开后重新置顶。
  激活过程会产生一次瞬态 `WA_INACTIVE`，用 `quick_activation_settling_` + `kQuickActivationSettled`
  消息忽略掉，避免面板刚出现就被自己关掉。
- `QuickPanel` 行/箭头禁用 Material ink：`hoverColor/highlightColor/splashColor` 全透明 +
  `NoSplash.splashFactory`，hover/选中只保留自绘的浅色背景。
- `QuickPanel` 增加"空白处单击关闭"：在列表区域外层放 `GestureDetector`，只有点击位置在最后一行
  下方时才关闭（行/箭头/分类标题的点击不会触发），空状态则点任意空白关闭。

**验证**：

| 场景 | 结果 |
|---|---|
| 记事本在前台 → 按快速键 | HUD 打开并成为前台（`foreground=True`），PASS |
| 面板打开后点击桌面/其他程序 | 面板关闭；从托盘打开的场景直接回托盘 |
| 点击面板内最后一行下方的空白 | 面板关闭；窗口可见时还原完整窗口 |
| 记事本在前台 → 打开面板 → Esc | 面板关闭（键盘事件到达 HUD） |
| Flutter 测试 | **60 / 60**（新增"点击面板空白关闭"） |
| `verify_quick_panel.py` | 7 / 7 PASS（含 `foreground=True`） |
| `verify_shell.py` | 9 / 9 PASS |
