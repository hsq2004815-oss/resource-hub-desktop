# Phase 5 — 前端接真实后端

- 日期：2026-10-17
- 改动：`app/lib/`（数据层、外壳、表单、设置）、`backend/resource_hub_core/`（新增 `launcher.py`、`resources.open/reveal`）
- 前置：`migration/phase4-ipc-protocol.md`
- 原应用 `resource_hub.pyw` **未修改**

---

## 1. 结论

界面已跑在真实数据上。删除 `lib/demo/` 后，列表内容全部来自 `folders.json` / `sites.json`。

| 验证项 | 结果 |
|---|---|
| 实机截图 | 11 条真实资源、5 个分类、`当前显示 11 / 11`（`migration/screenshots/phase5-live.png`） |
| Flutter 测试 | **20 / 20**（13 外壳 + 7 端到端协议） |
| 后端测试 | **137 / 137** |
| `flutter analyze` | 0 issue |
| 启动失败路径 | 独立错误页 + 重试，不再白屏 |

**已接通**：读列表、增/改/删、收藏、路径检测、打开/定位、语言与热键开关持久化、数据损坏只读态。

**未接通**（见 §7）：拖拽入窗、文件选择器、托盘、热键触发窗口显隐、导入导出 UI、开机启动、打包。
→ 已于 **Phase 5b / Phase 6** 补齐：见 `phase5b-shell-integration.md` 与 `phase6-packaging.md`。

---

## 2. 分层

```
main.dart                    启动后端 → app.hello → 读设置 → 注册热键 → 渲染外壳
  ├─ data/backend_bootstrap  定位并启动进程（脚本 / Python / 数据目录）
  ├─ data/backend_client     JSON Lines 传输（Phase 4）
  ├─ data/backend_repository 协议方法 → 模型，implements ResourceApi
  ├─ data/resource_api       外壳需要的数据操作接口
  └─ features/home/home_page 视图状态 + 调用 api
```

**为什么要有 `ResourceApi` 接口**：`HomePage` 依赖接口而不是具体仓库，测试就能用内存假实现跑完整外壳（13 个用例，不启动 Python）。真实链路另有 7 个端到端用例覆盖。

---

## 3. 后端新增

| 方法 | 作用 | 实现 |
|---|---|---|
| `resources.open` | 打开链接或文件/文件夹 | `launcher.open_link` / `open_path` |
| `resources.reveal` | 在资源管理器中定位 | `launcher.reveal_path`（`explorer /select,`） |

新增错误码 **`operation_failed`**：`ServiceError`（路径不存在、备份非法）不再被归为 `internal`——那不是后端缺陷，是操作失败。`internal` 现在只用于真正的未预期异常，并写 stderr 堆栈。

`launcher.py` 把副作用集中到一个文件，模块级 `_open_url` / `_startfile` / `_popen` 便于测试替换，测试中不会真的弹出窗口。

---

## 4. 启动与失败处理

```
spawn 后端 ──失败──> 错误页（原因 + 重试）
   │
app.hello ──协议版本不符──> 错误页
   │
   ├─ dataStatus=corrupt ──> 进入只读态：状态栏红字 + "只读" 标记，所有写操作被后端拒绝
   └─ ok ──> 读设置 → 注册热键（失败不阻塞，状态栏提示）→ 渲染外壳
```

错误页显示的是可复制的原始信息（例如"找不到后端脚本 backend/main.py"），不是笼统的"启动失败"。

---

## 5. 数据源定位

`BackendBootstrap.locate()` 的解析顺序：

| 目标 | 顺序 |
|---|---|
| 后端可执行 | `RH_BACKEND_EXE`（Phase 6 打包后用） |
| 后端脚本 | `RH_BACKEND_SCRIPT` → `backend/main.py` → `../backend/main.py` → 可执行文件同目录 |
| Python | `RH_PYTHON` → `python` → `py` → `python3` |
| 数据目录 | `RH_DATA_DIR` → 脚本所在目录的上一级 |

**实测坑**：从 `app/build/.../Release/` 目录直接双击 exe 时，找不到 `backend/main.py`（脚本在仓库根）。当前需从仓库根启动，或设 `RH_BACKEND_SCRIPT`。Phase 6 打包时后端会与 exe 同目录，这条路径才会自然成立。

---

## 6. 过程中发现并修复的缺陷

| # | 缺陷 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | **单击选中延迟约 300ms** | 删除流程的接线测试选不中行，打印工具栏按钮发现 `enabled=false` | 根因：`InkWell.onDoubleTap` 会安装双击识别器，与单击竞争手势竞技场，`onTap` 要等双击超时才触发。改为在 `Listener.onPointerDown`（仅主键）里立即选中，双击仍用于打开 |
| 2 | 保存后表单不清空 | 接线测试（新增行后输入框仍有内容） | 表单状态类改为公开的 `ResourceFormState`，暴露 `clearForm()`；保存成功后由外壳调用 |
| 3 | 设置对话框无法改热键开关 | 重写时发现旧实现是只读快照 | 改为接收 `AppSettings` + `onSettingsChanged`，开关即时保存并重新注册热键 |
| 4 | 旧 `widget_test` 依赖演示数据 | 删除 `lib/demo/` 后编译失败 | 重写为基于 `FakeApi` 的离线外壳测试 |

第 1 条值得记：**它只在自动化测试里暴露**——手工点一下看不出 300ms 的差别，但测试断言"点完应该选中"直接失败。这类问题靠肉眼验收会漏。

---

## 7. 未接通的部分

> **2026-10-17 更新**：本节由 Phase 5b/6 关闭。归属裁定见 `adr/ADR-002-native-shell-ownership.md`，
> 实现与验证见 `phase5b-shell-integration.md`、`phase6-packaging.md`。

| 功能 | 现状（Phase 5） | Phase 5b/6 结果 |
|---|---|---|
| 拖拽文件/文件夹入窗 | 未接 | ✅ runner `WM_DROPFILES` → `native_shell.dart` → `resources.drop` |
| 选择文件/文件夹按钮 | 显示"尚未接入"提示 | ✅ 原生 `IFileOpenDialog` 对话框 |
| 托盘图标与菜单 | 未接 | ✅ runner `Shell_NotifyIcon`（显示/隐藏、退出，文案随语言） |
| 热键 → 窗口显隐 | 热键已注册，但窗口不响应 | ✅ 后端事件 → `WindowControl.toggle()` + 搜索框聚焦 |
| 导入/导出 UI | 未接 | ✅ 工具栏入口 + 原生打开/保存对话框，JSON 格式兼容旧版 |
| 开机启动 | 只读开关 | ✅ `IShellLink` 写启动目录快捷方式，`--startup-hidden` 静默进托盘 |
| 打包分发 | `python backend/main.py` | ✅ Flutter Release + PyInstaller onedir，见 `phase6-packaging.md` |

---

## 8. 一个刻意的重复

列表筛选在**前端**做（`home_page.dart` 的 `_visible`），后端也有等价实现（`service.visible`）。

原因：数据集是几十条量级，本地筛选零延迟、无请求竞态；走协议每次输入都要往返。

代价：两处规则可能漂移。缓解：后端 `visible()` 有 9 个单元测试锁定语义，前端筛选规则与之逐条对应（分类、收藏、子串搜索、收藏置顶稳定排序），并注明"后端实现是参考实现"。

如果将来数据量涨到需要服务端分页，前端筛选应整体删掉、改为防抖 + 请求序号。

---

## 9. 复现验证

```powershell
# 1. 后端
cd backend
D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 2. 前端
cd ..\app
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:NO_PROXY="localhost,127.0.0.1"
flutter analyze
flutter test
flutter build windows --release

# 3. 实机（必须从仓库根启动，否则找不到 backend/main.py）
cd ..
.\app\build\windows\x64\runner\Release\resource_hub.exe
```

截图：`D:\miniconda3\python.exe migration\tools\capture_window.py migration\screenshots\phase5-live.png`
