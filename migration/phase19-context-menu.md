# Phase 19 — 资源管理器右键菜单：添加到常用资源工具

- 日期：2026-10-18
- 触发：用户希望「在电脑任意文件夹上右键，菜单里点一下就能把这个文件夹添加到工具里」，并让工具
  和这个文件夹产生交互。
- 结论：用 **HKCU 注册表传统菜单项**实现，点击后通过 `--add-folder "<路径>"` 把文件夹交给工具；
  工具开着就直接添加并弹窗选中，没开就启动工具再添加。
  Windows 11 的**新式主右键菜单**只认 COM 扩展，传统菜单项会出现在「显示更多选项」里——这是
  Win11 的平台行为，本次按用户确认先做传统方式（以后可升级 COM shell 扩展进主菜单）。

## 1. 行为

| 场景 | 结果 |
|---|---|
| 右键文件夹图标 | 菜单出现「添加到常用资源工具」（Win11：右键 →「显示更多选项」→ 该项；Win10/经典菜单直接出现） |
| 右键文件夹**内部空白处** | 菜单出现「添加当前文件夹到常用资源工具」，把当前打开的文件夹加进来（Phase 19.1 补充） |
| 点击时工具在运行 | 工具窗口弹出并前置 → 切换到「资源」页 → 新文件夹插入列表并选中 → 状态栏「已添加文件夹：xxx」 |
| 点击时工具没运行 | 启动工具，启动完成后自动添加并选中（`--add-folder` 参数在 Flutter 就绪后回放） |
| 文件夹已在资源库 | 不重复添加，只切到「资源」并选中已有项，状态栏提示「“xxx”已在资源库中」 |
| 窗口在托盘/隐藏 | 自动唤出完整窗口并显示结果 |
| 设置在设置页关闭「资源管理器右键菜单」 | 删除 HKCU 菜单项；重新打开则恢复 |

- 新加文件夹：名称 = 文件夹名；分类 = 未分类；备注为空；不收藏。
- 只处理**文件夹**（用户确认的范围），文件和网址暂不处理；文件夹图标与文件夹内空白处都支持。
- 注册表只写 **HKCU**（无需管理员），随时可删；程序移动位置后下一次启动会重新注册到新路径。
- 两个入口（文件夹图标 / 文件夹内空白处）共用同一个开关，关闭时一起移除。

## 2. 实现

### 2.1 注册表（runner 负责）

```
HKCU\Software\Classes\Directory\shell\ResourceHubAddFolder
    (默认)   = 添加到常用资源工具
    Icon     = "<exe 路径>",0
    Position = top
    command\(默认) = "<exe 路径>" --add-folder "%1"

HKCU\Software\Classes\Directory\Background\shell\ResourceHubAddFolder
    (默认)   = 添加当前文件夹到常用资源工具
    command\(默认) = "<exe 路径>" --add-folder "%V"
```

- `app/windows/runner/native_shell.cpp`：`SetShellContextMenuEnabled(bool)` /
  `GetShellContextMenuEnabled()`，用 `RegCreateKeyExW` / `RegDeleteTreeW` 写入/删除上面的键。
- 入口在 `flutter_window.cpp` 的 `resource_hub/window` channel：
  - `setShellContextMenuEnabled`：开/关菜单项；
  - `isShellContextMenuEnabled`：查询（QA 用）；
  - 启动时 Flutter 按 `shellContextMenuEnabled` 设置同步一次。

### 2.2 把文件夹交给工具

- `main.cpp` 解析 `--add-folder <路径>`：
  - 已有实例：用 `WM_COPYDATA`（`dwData = 'RHAF'`，payload 为 UTF-16 路径）发给运行中的窗口，
    再发原有的 wake 消息，然后退出（保持单实例）；
  - 没有实例：正常启动，路径在 `FlutterWindow` 构造函数中缓存。
- `flutter_window.cpp`：
  - `MessageHandler` 处理 `WM_COPYDATA`；Dart 尚未就绪时缓存，Flutter 调用 `shellAddReady`
    后回放为 `addFolderPath` 事件；运行中就绪后立即发事件；
  - 事件只走现有的 `resource_hub/window` channel，Dart 侧 `NativeShell.addFolderRequests` 接收。
- Flutter：
  - `main.dart` 启动读设置后同步菜单开关；
  - `HomePage` 监听 `addFolderRequests`，`_handleShellAddFolder` 负责去重、添加、切换页、选中、
    状态栏提示（先 `WindowControl.show()` 唤出窗口）。

### 2.3 设置

- `settings.py` 新增 `shell_context_menu_enabled`（默认 `true`）↔ `shellContextMenuEnabled`。
- 设置页「系统集成 → 资源管理器右键菜单」开关（`ValueKey('shell-context-menu-switch')`），
  关闭后自动移除菜单项。

### 2.4 顺带修掉的桥 bug

Phase 19 联调时发现：真实程序运行时（占用 bridge 端口 47821），后端测试的第二个 bridge 也能
"成功"绑同一个端口——Windows 的 `SO_REUSEADDR` 允许重复监听，导致测试请求被真实程序的 bridge
收走（10 个 bridge 测试失败）。修复：`_BridgeHTTPServer.allow_reuse_address = False`，
端口被占时按设计自动退到下一个空闲端口；新增回归测试 `test_a_second_bridge_does_not_share_a_port`。

## 3. 验证

| 项 | 结果 |
|---|---|
| 后端测试 | **271 / 271**（270 + 端口复用回归；1 个 symlink skip） |
| Flutter 测试 | **69 / 69**（+3：右键事件添加/去重、设置开关持久化） |
| `flutter analyze` | 0 issue |
| `verify_context_menu.py`（新实机脚本） | **10 / 10 PASS**（同时校验两个注册表入口） |
| `verify_quick_panel.py` | 10 / 10 PASS |
| `verify_shell.py` | 9 / 9 PASS |
| Windows 11 实测 | 右键文件夹 →「显示更多选项」→「添加到常用资源工具」可见并可用 |

`verify_context_menu.py` 覆盖：启动时注册（label/icon/command 都指向当前 exe）、运行中点击添加、
单实例（不会多开）、窗口可见、重复点击不重复添加、工具关闭时点击能启动并添加、设置关闭后删除
注册表项、重新打开后恢复、用户 folders.json / settings.json 逐字节还原。

截图（`migration/screenshots/`）：

- `phase19-context-menu-classic.png`：Win11「显示更多选项」经典菜单里的「添加到常用资源工具」；
- `phase19-context-menu.png`：Win11 主右键菜单（可见「显示更多选项」入口）；
- `phase19-settings-context-menu.png`：设置里的「资源管理器右键菜单」开关。

## 4. 已知限制 / 后续

- Windows 11 **主**右键菜单需要 COM shell 扩展（IExplorerCommand）或 MSIX 打包，工作量与兼容性
  成本更高；需要的话作为后续 Phase 升级。
- 目前只支持文件夹；右键文件、驱动器根目录暂不出现该菜单项。
- 文件夹路径重复时只选中已有项，不修改它的名称/分类/备注。
- 程序被移动后，首次启动会重新注册到新路径；旧路径的注册表项会被覆盖（同一个 key）。
- 注册表是 per-user 的：换 Windows 用户后需要在该用户下启动一次工具才会出现菜单。

## 5. 复现

```powershell
# 后端
cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 前端
cd ..\app; flutter analyze; flutter test

# 实机右键菜单（会临时改动 folders.json/settings.json，脚本结束自动还原）
cd ..; D:\miniconda3\python.exe migration\tools\verify_context_menu.py
```
