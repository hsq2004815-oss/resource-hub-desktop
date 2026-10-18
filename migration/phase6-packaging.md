# Phase 6 — 打包与干净环境验证

- 日期：2026-10-17
- 前置：`phase5-ui-wiring.md`、`phase5b-shell-integration.md`、`adr/ADR-002-native-shell-ownership.md`
- 原应用 `resource_hub.pyw` **未修改**，仍可独立运行（回滚路径）

---

## 1. 结论

打包版可在一台**没有 Python 环境**的机器上运行：Flutter exe + 冻结后端 onedir，数据文件写在 exe 同目录。

| 验证项 | 结果 |
|---|---|
| 打包产物 | `release\ResourceHub-Desktop-20261017-1835\`（**47.7 MB**，Phase 7 起含完整图标字体） |
| 干净环境（复制到临时目录、清除 `RH_*` 环境变量）启动 | ✅ 窗口正常出现 |
| 子进程 | ✅ `resource_hub_backend.exe`（无系统 `python.exe`） |
| 首次运行 | ✅ 自动生成 `sites.json` / `folders.json`（旧版示例数据） |
| 真实数据渲染 | ✅ 截图 `migration/screenshots/phase6-release-clean.png` |
| 后端冷启动 → `app.hello` | 104–121 ms（源码模式 119–131 ms，无额外开销） |
| 后端协议验证（打包后 exe） | 23 / 23 通过（`build/backend-exe/verify_backend_exe.py`） |

---

## 2. 产物结构

```
release\ResourceHub-Desktop-<stamp>\
├─ resource_hub.exe          Flutter 客户端（约 14 MB，含引擎）
├─ flutter_windows.dll 等    Flutter 运行时
├─ data\                     Flutter 资源（icudtl.dat 等）
├─ backend\                  冻结后端（**整目录必须随包分发**）
│  ├─ resource_hub_backend.exe    1.80 MB
│  └─ _internal\                  60 个文件 / 18.9 MB（CPython 运行时 + 标准库）
└─ README.txt                首次运行 / 数据目录说明
```

首次运行后会在**同目录**生成 `sites.json`、`folders.json`、`settings.json`（以及写盘时的 `.bak`）。
不把数据文件打进发布包，避免覆盖用户已有数据。

---

## 3. 构建方式

一键脚本（仓库根）：`build-flutter-release.ps1`

```powershell
# 完整构建（Flutter + 冻结后端 + 组装）
powershell -NoProfile -File .\build-flutter-release.ps1

# 只重新组装（复用现有构建产物）
powershell -NoProfile -File .\build-flutter-release.ps1 -SkipFlutter -SkipBackend -Tag 20261017-1820
```

脚本做三件事：

1. **冻结后端**：PyInstaller onedir，console 子系统（stdio 是协议生命线）：
   ```powershell
   $env:PATH = "D:\miniconda3\Library\bin;$env:PATH"   # conda 的 _ctypes 需要 ffi.dll
   D:\miniconda3\python.exe -m PyInstaller `
     --noconfirm --clean --onedir --console --hide-console hide-early `
     --add-binary "D:\miniconda3\Library\bin\ffi.dll;." `
     --paths backend --name resource_hub_backend `
     --distpath build\backend-exe\dist --workpath build\backend-exe\work `
     backend\main.py
   ```
   细节与踩坑见 `build/backend-exe/REPORT.md`（**ffi.dll 必须钉住**，否则 exe 启动即 `ImportError`）。
2. **Flutter 构建**：`flutter build windows --release --no-tree-shake-icons`（必须清除系统代理再跑，见 MEMORY.md）。
   `--no-tree-shake-icons` 是 Phase 7 加上的：默认的图标 tree-shaker 只保留 const 上下文的 `IconData`，
   通过 widget 参数传递的图标（导出/导入、列表/网格）会被漏掉，表现为按钮/分段空白；代价是字体 6 KB → 1.6 MB。
3. **组装**：复制 Flutter Release 全部内容 + 冻结后端到 `backend\`，生成 `README.txt`，检查两个 exe 存在。

---

## 4. 后端定位（`BackendBootstrap`）

打包后不再依赖"从仓库根启动"或 `RH_BACKEND_EXE`，解析顺序：

| 目标 | 顺序 |
|---|---|
| 后端可执行 | `RH_BACKEND_EXE` → `<exe目录>\backend\resource_hub_backend.exe` → `<exe目录>\resource_hub_backend.exe` |
| 后端脚本（开发用） | `RH_BACKEND_SCRIPT` → `backend/main.py` → `../backend/main.py` → `<exe目录>/backend/main.py` |
| Python（开发用） | `RH_PYTHON` → `python` → `py` → `python3` |
| 数据目录 | `RH_DATA_DIR` → 后端脚本的上一级目录 → 打包时 `<exe目录>` |

因此同一个 exe 既能跑开发模式（仓库里直接 `flutter run`/双击 Release 构建），也能跑打包版。

---

## 5. 干净环境验证

`migration/tools/verify_release.py` 做的事：

1. 取最新 `release\ResourceHub-Desktop-*`，**整目录复制到 `%TEMP%\rh-release-*`**；
2. 断言发布包**没有**携带 `sites.json` / `folders.json` / `settings.json`；
3. 清除所有 `RH_*` 环境变量后启动 exe（cwd 设为安装目录）；
4. 等窗口可见；用 Toolhelp 快照断言子进程是 `resource_hub_backend.exe` 且**没有** `python.exe`；
5. 断言首次运行在安装目录生成两个数据文件、示例 `sites.json` 为 2 条；
6. 截图（`phase6-release-clean.png`）后关闭。

实测输出（2026-10-17）：

```
PASS: window appears in the clean room
PASS: bundled backend is the child process (['resource_hub_backend.exe'])
PASS: no system Python is involved (frozen backend only)
PASS: first run seeds sites.json next to the exe
PASS: first run seeds folders.json next to the exe
PASS: sample sites contain 2 entries (got 2)
PASS: packaged release verified
```

截图显示真实列表（2 条示例资源、分类/状态/路径列齐全），说明 Flutter → 冻结后端的协议链路在干净环境可用。

---

## 6. 从旧版迁移

旧版（`resource_hub.pyw` / 其 PyInstaller exe）与新版**数据格式完全一致**。切换步骤：

1. 退出旧版；
2. 把旧版目录下的 `sites.json`、`folders.json`、`settings.json` 复制到新发布目录（与 `resource_hub.exe` 同级）；
3. 启动 `resource_hub.exe`。

首次运行若数据文件损坏，后端会拒绝写入并让 UI 进入只读告警态（ADR-001 D3），不会覆盖用户数据；可先用 `.bak` 或旧文件手工修复。

**回滚**：旧版目录不受影响，随时可直接运行旧版。

---

## 7. 已知问题 / 风险

| # | 问题 | 说明 / 缓解 |
|---|---|---|
| 1 | **无代码签名** | Windows SmartScreen 首次运行提示"未知发布者"；如要分发需自备证书签 `resource_hub.exe` 与 `backend\resource_hub_backend.exe` |
| 2 | onedir 不是单文件 | 60 个后端文件必须整目录复制；换来的是冷启动 ~110 ms（onefile 每次解包会额外数百 ms） |
| 3 | 控制台窗口 | 后端是 console 子系统，PyInstaller 已加 `--hide-console hide-early`；开发会话没有真实 GUI 窗口环境，未实测"从资源管理器双击是否闪黑框"，建议在真实桌面点一次；若仍有闪窗，需要在 `BackendClient.start` 用 `CREATE_NO_WINDOW`（Dart `Process.start` 目前不暴露该 flag，属 app 侧改动） |
| 4 | 安装目录必须可写 | 数据文件写在 exe 同目录；不要放 `Program Files`。若不接受，可改为 `%APPDATA%` 并把旧数据迁移（会破坏"绿色版"语义，未做） |
| 5 | 未做安装器 / 自动更新 | 当前是 zip 解压即用；没有 MSIX/Inno Setup，也没有更新检查 |
| 6 | 未签名的冻结 exe 可能被杀软误报 | onedir 比 onefile 误报少；如遇到可加白名单 |
| 7 | 前端 exe 体积 | Flutter Release 自身约 30+ MB，加后端共 46 MB；未做 strip/裁剪 |

---

## 8. 后续可选工作

- Inno Setup / MSIX 安装包（含开始菜单快捷方式、卸载时保留用户数据）。
- 代码签名 + SmartScreen 声誉。
- 后端改为按需下载或内嵌为单文件（trade-off 见 §7 #2）。
- 高 DPI/多显示器手工清单复核（审计 §5.4 第 15–17 项）。
