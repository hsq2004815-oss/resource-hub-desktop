# ADR-002 — Windows 壳层归属：托盘 / 窗口显隐 / 拖拽 / 文件对话框 / 开机启动

- 状态：**已接受**
- 日期：2026-10-17
- 决策者：Phase 5b 开发侧
- 关系：补充并部分修订 [ADR-001](ADR-001-tray-hotkey-ownership.md) D1

---

## 1. 背景

ADR-001 D1 决定"托盘、全局热键、单实例全部归 Python 后端"，理由是复用旧 Tkinter 代码、避免重写 Win32。
进入 Phase 5 后，实际形态与当时的假设有两处偏差：

1. **可见进程已经是 Flutter exe**，Python 只是它 `Process.start` 出来的子进程。子进程随前端退出而退出，无法独立持有托盘图标生命周期。若托盘仍在 Python，前端退出后托盘会残留或需要额外握手。
2. **Phase 2 已经在 runner 里加了 `resource_hub/window` 方法通道**（窗口标题），而托盘图标、`WM_CLOSE` 隐藏、`ShowWindow`/`SetForegroundWindow` 本来就是窗口/消息级操作，放在 runner 里比跨进程转发更直接。

ADR-001 D1 关于**全局热键**的判断依然成立：热键是系统级注册，与窗口无关，Python 后端用独立线程 + 自带消息循环实现，前端只消费 `hotkey` 事件。这一点不变。

## 2. 决策

| 能力 | 归属 | 位置 |
|---|---|---|
| 全局热键注册 / 注销 / 冲突探测 | **Python 后端**（维持 ADR-001 D1） | `backend/resource_hub_core/hotkey.py`、`protocol.py` |
| 热键事件 → 窗口显隐 | Flutter 前端编排 | `home_page.dart`（`hotkey` 事件 → `WindowControl.toggle()` → 搜索框聚焦） |
| 托盘图标、托盘菜单（显示/隐藏、退出）、关闭按钮隐藏 | **Flutter runner（C++）** | `windows/runner/flutter_window.cpp` |
| 窗口显示 / 隐藏 / 置前 / 标题 / 托盘文案 | Flutter runner | 同上 + `lib/platform/window_control.dart` |
| 拖拽文件/文件夹（`WM_DROPFILES`） | Flutter runner 接收，Dart 调后端 `resources.drop` | `flutter_window.cpp` + `lib/platform/native_shell.dart` |
| 打开 URL / 文件 / 文件夹、在资源管理器中定位 | **Flutter runner**（`ShellExecuteW` / `SHOpenFolderAndSelectItems` + `AllowSetForegroundWindow(ASFW_ANY)`） | `native_shell.cpp`，后端 `resources.open/reveal` 作为 fallback |
| 打开 / 保存文件对话框、选择文件夹 | Flutter runner（`IFileOpenDialog` / `IFileSaveDialog`） | `windows/runner/native_shell.cpp` |
| 开机启动（启动目录 `.lnk`） | Flutter runner（`IShellLink`） | 同上 |
| 单实例 + 二次启动唤醒已有窗口 | Flutter runner（命名互斥体 + 注册消息） | `windows/runner/main.cpp` |
| stdout 协议、数据读写 | Python 后端（不变） | `backend/main.py` |

**新增通道方法**（`resource_hub/window`）：`pickFolder`、`pickFile`、`pickJsonFile`、`saveFile`、`setLaunchAtStartup`、`isLaunchAtStartup`、`openTarget`、`revealPath`；runner → Dart 的反向调用：`dropPaths`（字符串数组）。

> **拖拽实现注意**：真实拖拽落在覆盖客户区的 `FLUTTERVIEW` 子窗口上，而该窗口的 WndProc 属于 Flutter
> 引擎、不处理 `WM_DROPFILES`。因此 runner 用 `SetWindowLongPtrW` 子类化该窗口把消息转发给
> `FlutterWindow::HandleDroppedFiles`（引擎重建 view 时自动重挂，销毁时还原）。只给顶层窗口
> PostMessage 的测试会假绿——`verify_shell.py` 已改为向子窗口投递。

## 3. 理由

1. **生命周期正确**：托盘/单实例是"应用在前台存在"的语义，Flutter exe 才是应用进程。Python 子进程死掉（崩溃、被杀）时前端仍可提示并重试，而不是连托盘一起消失。
2. **不引入第三方依赖**：`file_selector` / `desktop_drop` / `window_manager` 等插件需要 pub 依赖、插件注册与网络；后端也保持"零第三方依赖"（pystray 会打破它，并与 PyInstaller 打包耦合）。本轮实现约 300 行 C++，全部在 runner 内。
3. **可测试性**：通道在 widget 测试中不存在 → `NativeShell`/`WindowControl` 全部返回 null 并降级为 no-op，外壳测试不需要 mock 插件；真实链路由 `migration/tools/verify_shell.py` 在实机上验证。
4. **i18n 仍由 Dart 驱动**：托盘菜单文案通过 `setTrayLabels` 从 Dart 推给 runner，语言切换时即时刷新，和旧应用行为一致。

## 4. 代价与约束

- 新增/修改的 C++ 只在 Windows 目标存在；Dart 侧必须对"通道缺失"无感（已实现：`MissingPluginException` / `PlatformException` 全部吞掉并返回 null）。
- `IFileOpenDialog` 依赖 COM 单线程套间：`main.cpp` 已 `CoInitializeEx(APARTMENTTHREADED)`；对话框必须在 UI 线程调用（当前在窗口消息线程）。
- 单实例互斥体名 `Local\Mytools.ResourceHub.Flutter`；二次启动通过注册消息 `ResourceHub.ShowWindow` 唤醒已有窗口。若第二次启动发生在首个实例窗口创建之前（毫秒级竞态），第二次会静默退出，首个实例继续正常启动——可接受。
- 开机启动快捷方式目标为本 exe + `--startup-hidden`；runner 检测该参数后不调用 `Show()`，直接驻留托盘。
- **为什么打开外部程序也归 runner**：Windows 前台锁定只允许前台进程（或获得其授权者）把新窗口推到前台。
  旧版单进程 `os.startfile` 天然是前台进程；迁移后由后台 Python 子进程调用时，Explorer/浏览器可能创建在应用窗口**后面**。
  runner 持有前台窗口，可以在 `ShellExecuteW` 前调用 `AllowSetForegroundWindow(ASFW_ANY)` 把这次前台权让给 shell，
  从而让资源管理器/浏览器正常前置。后端 `resources.open/reveal` 仍保留，作为通道缺失（测试/非 Windows）时的 fallback。
- 代价：打开/定位的副作用不再经过协议层，后端单测覆盖不到；用 `native_shell_probe.exe open|reveal` 与实机点击验证。

## 5. 被否决的方案

| 方案 | 否决原因 |
|---|---|
| 托盘继续留在 Python（pystray，ADR-001 D1 原文） | 前端退出后托盘生命周期不可控；给零依赖后端引入第三方包；PyInstaller 需额外 collect；跨进程"退出"协调复杂 |
| 用 Flutter 插件（`file_selector`、`desktop_drop`、`window_manager`） | 需要 pub 网络依赖与插件注册；`desktop_drop` 在 Windows 上仍走 `WM_DROPFILES`，插件层没有收益；窗口管理插件与现有 runner 尺寸/最小尺寸逻辑冲突 |
| 托盘菜单用 Python 事件驱动 | 菜单是 shell 交互，必须由拥有窗口的进程处理；跨进程转发只会增加失败面 |

## 6. 后续影响

- Phase 5b 交付见 `migration/phase5b-shell-integration.md`。
- Phase 6 打包：runner 已无可选 DLL 依赖（`shell32`/`ole32`/`uuid` 均为系统库），后端以 onedir 冻结版放在 `backend\` 子目录，`BackendBootstrap` 自动发现。见 `migration/phase6-packaging.md`。
- 若将来移植到 macOS/Linux，`NativeShell` 与 `WindowControl` 的接口保持不变，新增平台实现即可；Dart 侧无需改动。
