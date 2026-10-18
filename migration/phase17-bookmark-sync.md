# Phase 17 — 浏览器书签自动同步（Chrome / Edge）

- 日期：2026-10-18
- 触发：用户希望「在 Chrome / Edge 里收藏网站后，自动同步到这个工具」，并询问某浏览器扩展
  （BOOKSyncHook）是否可行。
- 结论：**不需要浏览器扩展**。Chrome / Edge 的书签本来就存在本地 JSON 文件里，后端只读解析即可；
  扩展方案（BOOKSyncHook 之类）需要额外安装和权限，所以没有采用。
- 范围：后端新增书签桥（读取 + 监听），前端新增同步入口、设置区块与后台事件刷新；数据格式不变。

---

## 1. 设计决策（与用户逐项确认）

| 问题 | 结论 |
|---|---|
| 实现方式 | A. 内置书签桥：后端读取浏览器 `Bookmarks` 文件 + 轮询监听（零安装、零权限、Chrome+Edge） |
| 同步关系 | **只新增**：浏览器新增书签会导入；浏览器改名/删除不影响工具里的资源；工具里删掉的同步项不会被重新加回来 |
| 分类 | 用浏览器**书签文件夹名**做分类，如 `开发/工具`；书签栏根下的归「书签栏」，其他收藏根下的归「其他收藏」 |
| 首次 | 首次开启（以及每次启动）把现有书签导入一次，之后只跟进新增 |
| 触发 | 后台自动监听（默认开启，可在设置关闭）+ 「⋮」菜单里的「同步浏览器书签」手动触发 |
| 自定义目录 | 设置里可指定「自定义书签目录」，兼容其他 Chromium 浏览器或便携版 |

## 2. 读取范围与规则

- 自动发现（Windows，当前用户）：
  - `%LOCALAPPDATA%\Google\Chrome\User Data\<Default|Profile N>\Bookmarks`
  - `%LOCALAPPDATA%\Microsoft\Edge\User Data\<Default|Profile N>\Bookmarks`
  - 自定义目录：可直接填 `User Data` 目录、某个 profile 目录，或 `Bookmarks` 文件本身。
  - 测试/便携覆盖：环境变量 `RH_BROWSER_DATA_DIRS`（`;` 分隔）替代默认根目录。
- 解析：`roots.bookmark_bar / other / synced` 递归；只收 `http/https`，跳过 `chrome://`、`edge://`、
  `javascript:`、`about:`、`data:`、`file://` 等；空标题回退为域名。
- 去重：URL 规范化（去空白、小写、去末尾斜杠）后与 `sites.json` 现有 URL + 历史已同步集合比对。
- 只新增：已同步 URL 记在 `.resourcehub-meta.json` 的 `bookmarks.seenUrls` 里，工具里删掉也不会复活；
  `orderVersion` 等原有键原样保留。
- 新同步项**追加在网站列表末尾**，不打乱手动拖动排序。
- 浏览器文件**只读**：任何情况下都不写入浏览器目录。

## 3. 实现

### 3.1 后端（`backend/resource_hub_core/`）

- `bookmarks.py`（新）：
  - `discover_profiles()` / `parse_bookmarks()` / `collect_bookmarks()`；
  - `BookmarkSyncEngine`：`status()` 只读快照，`sync(service, settings)` 导入并维护 seen ledger；
  - `BookmarkWatcher`：daemon 线程，2 秒轮询 mtime/size、0.6 秒防抖、每 30 秒重新发现配置；
    首次轮询也会同步一次（应用关闭期间新增的书签在下次启动时补进来）。
- `service.py`：`add_synced()` —— 与 `add()` 相同的校验/去重，但跳过非法与重复项、追加到末尾、只写一次盘。
- `protocol.py`：`bookmarks.status` / `bookmarks.sync` 方法；`ServerState.bookmark_engine/lock/watcher`；
  所有协议请求与 watcher 写入共用一把 `RLock`；`serve_forever` 启动前先做一次同步（第一个
  `resources.list` 就已经包含导入的书签），watcher 变化时推事件
  `{"event":"bookmarks","payload":{"added":n,"lastSyncAt":...,"profiles":[...]}}`；`app.shutdown` / stdin EOF 停线程。
- `settings.py`：`bookmarkSyncEnabled`（默认 true）、`bookmarkCustomDir`（默认空，非法值不崩）。
- 单测 58 个：解析/过滤/分类/排序、配置发现顺序、自定义目录、去重与不复活、meta 保留、监听线程、
  协议方法、启动导入与幂等、真实文件只读等。

### 3.2 Flutter

- `backend_models.dart`：`AppSettings` 新字段；`BookmarkProfile` / `BookmarkStatus` / `BookmarkSyncResult`。
- `resource_api.dart` / `backend_repository.dart`：`bookmarks.status` / `bookmarks.sync`。
- `resource_list_panel.dart`：「⋮」菜单新增「同步浏览器书签」，触发手动同步。
- `home_page.dart`：手动同步结果写状态栏；后台 `bookmarks` 事件刷新网站列表并提示
  「已从浏览器同步 N 个新网站」；设置对话框三个回调（读取状态 / 立即同步 / 选择目录）。
- `settings_dialog.dart`：「浏览器书签同步」区块 —— 开关、检测到的配置数量与书签数、上次同步时间、
  自定义目录（选择/清除）、「立即同步」按钮与结果。
- i18n：`app_strings_ext.dart` 新增 20 个 zh/en 键。

## 4. 验证

| 项 | 结果 |
|---|---|
| 后端测试 | **230 / 230**（基线 172 + 58；1 个 symlink skip） |
| Flutter 测试 | **63 / 63**（+3：菜单手动同步、后台事件刷新、设置开关持久化） |
| `flutter analyze` | 0 issue |
| `verify_bookmark_sync.py`（新增实机脚本，跑在临时复制的发布包上） | **7 / 7 PASS** |
| `verify_shell.py` | 9 / 9 PASS |
| `verify_quick_panel.py` | 7 / 7 PASS |
| 真实机器只读验证 | 本机 Chrome+Edge 共 17 个书签被自动导入（`sites.json` 2 → 19），浏览器文件字节未变 |

`verify_bookmark_sync.py` 覆盖：启动导入、文件夹分类（书签栏/开发/其他收藏）、浏览器文件只读、
文件变化后 2 秒级自动导入（嵌套文件夹也正确）、重复轮询幂等、设置对话框检测到 3 个配置、
真实安装目录的 `sites.json` 字节不变。

截图（`migration/screenshots/`）：

- `phase17-bookmarks-imported.png`：导入后的网站列表（分类来自书签文件夹，状态栏提示自动同步）；
- `phase17-settings-bookmarks.png`：设置里的书签同步区块（开关/自定义目录/检测到的配置/上次同步/立即同步）。

## 5. 已知限制 / 后续可做

- 只内置 Chrome / Edge 的默认位置；其他 Chromium 浏览器或便携版用「自定义书签目录」指向即可。
- 只做「浏览器 → 工具」单向增量：浏览器改名/删除不同步（用户选择的只新增策略）；工具里删除的
  同步项不会被重新加回来。
- 应用运行时靠 2~3 秒轮询发现变化；应用关闭期间新增的书签在下次启动时导入。
- 首次全量导入可能一次加入很多行（会追加到末尾并去重）；书签量特别大时首次同步会有短暂写入。
- 语义边界：只同步 `http/https`；浏览器内部页/书签脚本不会被导入。

## 6. 复现

```powershell
# 后端
cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 前端
cd ..\app; flutter analyze; flutter test

# 实机书签桥（临时复制发布包 + 假浏览器配置，不碰真实数据目录）
cd ..; D:\miniconda3\python.exe migration\tools\verify_bookmark_sync.py
```
