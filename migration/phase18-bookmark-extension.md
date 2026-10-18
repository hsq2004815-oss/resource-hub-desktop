# Phase 18 — 双向书签同步（浏览器扩展 + 本机回环桥）

- 日期：2026-10-18
- 触发：Phase 17 是「只新增」策略，用户发现**在浏览器里取消收藏后工具里还在**，于是提出
  「在工具里删除资源时，浏览器端也取消收藏」。
- 结论：可以，但**不能直接改浏览器书签文件**（校验和/运行中覆盖/丢书签风险）。最终方案：
  **轻量浏览器扩展 + 本机回环 HTTP 桥**，双向同步：工具删除 → 浏览器删书签；
  浏览器取消收藏/改名 → 工具同步删除/改名。扩展只与本机 `127.0.0.1` 通信，不联网。

## 1. 设计决策（用户确认）

| 问题 | 结论 |
|---|---|
| 写入浏览器的方式 | A. 浏览器扩展（官方 `chrome.bookmarks` API）——不在扩展外改文件 |
| 通信方式 | 本机回环端口（127.0.0.1:47821–47830，免注册表、免 Native Messaging 注册） |
| 删除交互 | 删除同步来源的资源时弹确认框，可勾选「同时从浏览器移除收藏」，可「记住我的选择」 |
| 反向同步 | 双向：浏览器取消收藏 → 删除工具里的同步项；浏览器改名 → 更新工具里的名称 |
| 扩展分发 | 发布包内置 `bookmark-extension/` 文件夹，Chrome/Edge 开发者模式加载（一次性） |

未采用：直接改 `Bookmarks` JSON（Chrome/Edge 有内部 checksum，运行时会覆盖外部修改，风险高）；
Native Messaging（要写注册表 + 固定扩展 ID，自用场景回环端口更省事）。

## 2. 架构

```
Chrome / Edge ──(扩展: chrome.bookmarks API)──┐
                                             │  HTTP 127.0.0.1:47821-47830 (JSON)
                                             ▼
Flutter UI ◄── stdio JSON Lines ── Python 后端 ── BookmarkBridge（loopback HTTP）
   │                                  │
   └─ bookmarks 事件（删除/改名刷新） └─ 只读书签文件（Phase 17 导入）
```

- 后端仍是唯一数据源；扩展只是「浏览器侧执行器 + 事件源」。
- 工具删除 → 后端把 `remove` 命令入队 → 扩展轮询 `/commands` → `chrome.bookmarks.remove` → `/ack`。
- 浏览器变化 → 扩展把 `onRemoved`/`onChanged` 批量 `POST /events` → 后端在 `bookmark_lock` 下
  删除/改名本地资源、维护 seen ledger，并推一条 `bookmarks` 事件刷新 Flutter 列表。

## 3. 后端实现

- `backend/resource_hub_core/bookmark_bridge.py`（新，`BookmarkBridge`）：
  - `ThreadingHTTPServer` 绑 `127.0.0.1`，端口 47821–47830 取第一个空闲，全占用则绑临时端口；
  - daemon 线程，`start()/stop()` 幂等；命令队列 10 分钟过期；
  - 所有响应带 CORS 头（扩展 `fetch` 直连），`OPTIONS` → 204；
  - `GET /ping`、`GET /commands`、`POST /ack`、`POST /events`；未知路径 404、坏 JSON 400。
- `protocol.py`：`ServerState.bookmark_bridge`；`serve_forever` 启动、`_shutdown`/`app.shutdown` 停止；
  新方法 `bookmarks.extensionStatus`（connected/lastSeenAt/port/pendingCommands/extensionPath）、
  `bookmarks.matches`（URL → 浏览器书签匹配，供删除确认）；`resources.delete` 支持
  `removeFromBrowser`，返回 `{deleted, browserQueued, extensionConnected}`。
- `bookmarks.py`：新增 `seen_urls()/forget_seen()`；反向删除时从 seen ledger 移除该 URL（保留
  `orderVersion` 等 meta 键），所以**重新收藏同一 URL 会再次导入**。
- `settings.py`：`bookmarkDeleteMode` ∈ `ask | remove | keep`（默认 ask，非法值归一为 ask）。
- 单测：269 个（Phase 17 的 230 + 39），含桥的端口/命令队列/事件/错误、反向删除/改名、
  seen 清理后重新导入、协议方法、settings。

## 4. 浏览器扩展（`bookmark-extension/`，随发布包）

- Manifest V3，Chrome/Edge 通用；权限仅 `bookmarks`、`storage` + `host_permissions: http://127.0.0.1/*`。
- `background.js`：端口发现缓存 → 1.5s 轮询 `/commands` → `chrome.bookmarks.search/remove` → `/ack`；
  `onRemoved`/`onChanged` 400ms 批量上报 `/events`，断线时事件进 storage 缓冲（上限 500）重连重放；
  过滤文件夹与 `chrome://`/`edge://`/`javascript:`；MV3 service worker 被回收后靠 storage 恢复。
- `README.md`：Chrome/Edge 30 秒安装说明、权限说明、验证方式、排障。
- `check_protocol.py`：stdlib 自检（静态检查 + 本地 mock bridge 跑完整协议）→ 52 PASS。

## 5. Flutter UI

- 删除确认框：URL 在浏览器里有书签时显示「同时从浏览器移除（N 处书签收藏）」+ 来源（如
  `Edge · Default`）+「记住我的选择」；`bookmarkDeleteMode` 为 `remove/keep` 时直接按设置执行。
- 删除结果提示：已同时移除 / 扩展离线已排队 / 未能通知扩展 三种状态。
- 设置区块：删除策略三选一（每次询问 / 同时移除书签 / 仅删本地）、扩展连接状态（已连接/未连接）、
  「打开扩展目录」、原有开关/自定义目录/立即同步。
- `bookmarks` 事件扩展：`added/deleted/renamed` 分别刷新列表并提示
  （「浏览器端取消了 N 个收藏，已从工具中移除」/「浏览器端更新了 N 个书签名称」）。
- 翻译键 zh/en 各新增 15 个。

## 6. 验证

| 项 | 结果 |
|---|---|
| 后端测试 | **269 / 269**（+39，1 个 symlink skip） |
| Flutter 测试 | **66 / 66**（+3：删除联动、扩展状态、浏览器端删除事件） |
| `flutter analyze` | 0 issue |
| `verify_bookmark_extension.py`（新，真后端子进程 + 模拟扩展） | **15 / 15 PASS** |
| `verify_bookmark_sync.py`（Phase 17 实机导入） | 7 / 7 PASS |
| `verify_shell.py` | 9 / 9 PASS |
| `verify_quick_panel.py` | 7 / 7 PASS |
| 扩展 `check_protocol.py` | 52 PASS，`node --check background.js` 通过 |
| Chrome 自动化加载冒烟 | 官方稳定版 Chrome 会忽略 `--load-extension` 命令行开关，无法纯命令行验证；改用扩展协议自检 + 设置页手动加载验证 |

`verify_bookmark_extension.py` 覆盖：启动导入、`removeFromBrowser` 入队、`/ping` 连接、
`/commands` 取删除命令、`/ack` 清空、反向改名（资源名更新 + 一条 bookmarks 事件）、
反向取消收藏（删除资源 + 清 seen）、重新收藏后再次导入、监听新增、浏览器文件只读、后端退出后端口关闭。

截图（`migration/screenshots/`）：

- `phase18-settings-extension.png`：设置里的删除策略 + 浏览器扩展「已连接」；
- `phase18-sites-list.png`：同步后的网站列表；
- `phase18-delete-dialog.png`：删除确认框里的「同时从浏览器移除（1 处书签收藏）」+「记住我的选择」。

## 7. 用户安装步骤（一次性）

1. 启动 Resource Hub（`resource_hub.exe`）；
2. Chrome 打开 `chrome://extensions`（Edge 为 `edge://extensions`）；
3. 打开右上角「开发者模式」；
4. 「加载已解压的扩展程序」→ 选择发布包里的 `bookmark-extension` 文件夹；
5. 允许「读取和更改您的书签」；
6. 回到工具设置 → 浏览器书签同步，看到「浏览器扩展：已连接」即成功。

Chrome/Edge 各加载一次；浏览器重装后重新加载。扩展只在工具运行时工作（本机回环端口），
工具关闭时浏览器侧操作会在下次启动时由只读导入/事件补齐。

## 8. 已知限制

- 扩展需要手动加载（未上架商店）；Chrome 对开发者模式扩展启动时可能提示，点「保留」即可。
- 本机回环端口 47821–47830 被占用时会退到临时端口，扩展发现不到 → 设置显示未连接
  （可关闭占用端口的程序后重启工具）。
- 浏览器端改名会同步名称，但**移动文件夹不改变分类**；浏览器端新增仍走文件监听（约 2–3 秒）。
- 工具里删除「非书签来源」的资源不会碰浏览器；若 URL 恰好有浏览器书签，确认框仍会询问。
- 同一 URL 在多个配置/文件夹里都有书签时，扩展会删除所有匹配项（确认框显示总数）。
- 扩展与工具通信仅本机回环，不加密、不联网；不校验来源（本机可信环境，个人工具场景）。

## 9. 复现

```powershell
# 后端
cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 前端
cd ..\app; flutter analyze; flutter test

# 扩展协议自检
cd ..\bookmark-extension; D:\miniconda3\python.exe check_protocol.py; node --check background.js

# 端到端（真后端 + 模拟扩展，不启动浏览器）
D:\miniconda3\python.exe migration\tools\verify_bookmark_extension.py
```
