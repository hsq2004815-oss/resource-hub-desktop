# Phase 4 — stdio JSON Lines 协议与双端客户端

- 日期：2026-10-17
- 新增：`backend/resource_hub_core/protocol.py`、`backend/main.py`、`app/lib/platform/backend_client.dart`
- 前置：`migration/phase3-business-layer.md`、`migration/adr/ADR-001-tray-hotkey-ownership.md`
- 原应用 `resource_hub.pyw` **未修改**

---

## 1. 结论

前后端通信已打通并**双端实测**：Dart 客户端启动真实 Python 子进程，通过管道完成中文数据的增、查、错误映射与关闭。

| 验证项 | 结果 |
|---|---|
| 后端单元 + 子进程测试 | **134 / 134 通过**（3.2 s） |
| Flutter 全量测试 | **18 / 18 通过**（11 widget + 7 端到端协议） |
| `flutter analyze` | 0 issue |
| 中文经真实管道往返 | 通过（`内部知识库` / `中文备注` 无损） |
| 帧格式 | 单行 JSON、LF 结尾、UTF-8，无 `\r\n`（已断言） |

**能力边界**：协议可用，但 Flutter 界面仍跑 Phase 2 的演示数据——UI 接线是 Phase 5。托盘与窗口显隐也未接入。

---

## 2. 为什么还是 JSON Lines

审计 §6.2 的结论未变，且 Phase 3/4 的实测进一步确认：

| 方案 | 取舍 |
|---|---|
| **stdio JSON Lines（选用）** | 零端口、零鉴权、零连接池；进程生命周期天然绑定；Windows 中文只需强制 UTF-8 |
| 本机 HTTP | 需要端口分配、回环监听、会话令牌、超时管理；当前全是毫秒级本地操作，收益为零 |
| 命名管道 | 能力更强，但 Windows 专属且客户端实现更重；等出现"长任务 + 进度推送 + 可取消"再升级 |

**唯一必须解决的问题**：Windows 默认 `cp936` 会把中文路径写成乱码。已在 `configure_stdio()` 里强制 UTF-8 并在子进程测试中断言。

---

## 3. 帧格式

一行一个 JSON 对象，UTF-8，`\n` 结尾。

**请求**（前端 → 后端）

```json
{"id": 1, "method": "resources.list", "params": {"mode": "folders"}}
```

**成功响应**

```json
{"id": 1, "ok": true, "result": {"items": [...], "total": 11, "visible": 11}}
```

**失败响应**

```json
{"id": 1, "ok": false, "error": {"code": "validation",
                                 "key": "enter_link_name", "detail": "..."}}
```

**事件**（后端 → 前端，无 `id`）

```json
{"event": "hotkey", "payload": {"action": "toggle"}}
```

### 为什么必须有事件帧

审计 §6.2 只设计了请求-响应。但**全局热键按下不是对任何请求的回复**——它是异步的、由另一个线程产生的。没有事件帧，Phase 5 只能靠轮询，既延迟又浪费。这是 ADR-001 §5 记录的缺口，本阶段补上。

事件不带 `id`，客户端按 `event` 字段路由；当前定义 `hotkey`（托盘事件在 Phase 5 加入）。

---

## 4. 方法表

| 方法 | 参数 | 结果 |
|---|---|---|
| `app.hello` | — | `protocolVersion` / `methods` / `dataStatus` / `loadError` / `baseDir` |
| `app.shutdown` | — | `{shutdown: true}`，随后进程退出 |
| `resources.list` | `mode`, `query?`, `category?`, `favoritesOnly?`, `labels?` | `items` / `total` / `visible` / `categories` |
| `resources.add` | `mode`, `name`, `target`, `category?`, `note?` | `{item}` |
| `resources.update` | `mode`, `id`, `name`, `target`, `category?`, `note?` | `{item}` |
| `resources.delete` | `mode`, `id` | `{deleted}` |
| `resources.favorite` | `mode`, `id`, `value?`（缺省则取反） | `{item}` |
| `resources.checkPaths` | `mode` | `supported` / `total` / `missing[]` / `missingCount` |
| `resources.drop` | `paths[]` | `added` / `skipped` / `invalid` |
| `resources.export` | `mode` | `{items}`（由前端负责写文件） |
| `resources.import` | `mode`, `items[]` | `imported` / `skipped` |
| `settings.get` | — | `{settings}` |
| `settings.set` | `settings` | 归一化后的 `{settings}` |
| `settings.probeHotkey` | `hotkeyId` | `{available}` |
| `hotkey.start` | — | `registered` / `label` / `reason` |
| `hotkey.stop` | — | `{stopped}` |

`mode` 只有 `"links"` 与 `"folders"`；其他值返回 `bad_request`。

`labels` 用于把当前语言的展示文案注入搜索（`{"uncategorized": "未分类", "favoriteMark": "★"}`），因为后端本身不做 i18n——这样"搜索未分类"仍能命中。

---

## 5. 错误码

| code | 含义 | 是否带 `key` |
|---|---|---|
| `bad_request` | 参数类型/取值不合法，或 JSON 解析失败 | 否 |
| `validation` | 业务校验失败（空名称、非法 URL、路径不存在） | 是 |
| `duplicate` | 目标已存在 | 是 |
| `not_found` | id 不存在 | 是 |
| `corrupt_data` | 数据文件损坏，已停止读写 | 是（`data_corrupt`） |
| `unknown_method` | 方法名不存在 | 否 |
| `internal` | 后端缺陷；详细堆栈写 stderr | 可能 |

`key` 是旧文案表的键（`enter_link_name`、`duplicate_folder_path`、`select_first_link` 等），前端 `t.t(key)` 直接渲染。**后端不返回自然语言**，否则语言切换会断链（Phase 3 §6 的设计决定）。

`data_corrupt` 是本次新增的键——旧应用没有这个场景（它直接覆盖了）。Phase 5 需要在 `app_strings_ext.dart` 补中英文案。

---

## 6. 实现要点

### 6.1 编码

```python
reconfigure_out(encoding="utf-8", errors="replace", newline="\n")
```

三件事缺一不可：UTF-8 防乱码、`newline="\n"` 防 CRLF、`errors="replace"` 防单条脏数据炸掉整个流。

Dart 侧**显式**用 `utf8.encode` / `utf8.decoder`，不依赖 `Process.start` 的默认编码（那是 `systemEncoding`，中文 Windows 上是 cp936）。

### 6.2 线程安全

热键回调在 `ResourceHubHotkey` 线程上触发，可能同时主线程正在写响应。`FrameWriter` 用一把锁包住"整行写入 + flush"，保证不会出现半行交错。

### 6.3 损坏数据的状态机

```
启动 → load()
        ├─ 正常      → dataStatus: "ok"
        └─ 解析失败  → dataStatus: "corrupt"，文件原样保留
```

`corrupt_data` 状态下：`app.hello` 仍可调用（前端据此提示用户），所有 `resources.*` 返回 `corrupt_data`，**任何写入都不会发生**。这是 ADR-001 D3 在协议层的落地——旧应用在这种情况下会用示例数据覆盖用户文件。

### 6.4 错误不杀循环

任何 handler 抛异常都转成 `internal` 错误帧，循环继续。但**内部异常必须写 stderr 并带堆栈**——见 §7 第 1 条，这条是踩坑后补的。

---

## 7. 开发中发现的缺陷

| # | 缺陷 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | `app.shutdown` 调用了已改名的方法，抛 `AttributeError`，被兜底 `except Exception` 吞成 `internal` 错误帧——**关闭请求静默失效** | `test_shutdown_stops_the_loop` 断言"shutdown 后不再处理后续请求"失败 | 修正调用；并给 `internal` 分支补 `traceback.print_exception(file=sys.stderr)` |
| 2 | `JsonLinesServer.serve_forever` 里 `if not self._handle_line(...): break` 是死逻辑（函数恒返回 True） | 代码走查 | 简化为直接检查停止标志 |

第 1 条值得记住：**宽泛的 `except Exception` 会把编程错误伪装成运行时错误**。如果没有那条断言"shutdown 之后不应该再有响应"，这个 bug 会一路带到 Phase 5，表现为"关不掉后端进程"。

---

## 8. 测试

| 文件 | 用例 | 覆盖 |
|---|---|---|
| `backend/tests/test_protocol.py` | 30 | 帧格式、id 回显（含字符串 id）、空白行、未知方法、参数校验、全部错误码映射、损坏数据状态、事件帧形状、settings 往返、hotkey 禁用分支 |
| `backend/tests/test_protocol_subprocess.py` | 2 | 真实子进程：中文往返、无 CRLF、stderr 无内部错误、stdin 关闭即退出 |
| `app/test/backend_client_test.dart` | 7 | Dart 客户端对真实进程：hello、首运行示例数据、中文往返、结构化错误、未知方法、settings 往返、`close()` 后调用报 `StateError` |

Dart 测试在没有 Python 时自动 skip，不阻塞纯 UI 开发。

---

## 9. 已知限制 → Phase 5 入口

| 限制 | 说明 |
|---|---|
| 无流式进度 | 当前所有操作都是毫秒级；`resources.drop` 大目录也只在结束时返回 |
| 无请求取消 | 同上，暂无必要 |
| 事件只有 `hotkey` | 托盘菜单事件、窗口显隐事件在 Phase 5 接入后追加 |
| 无版本协商 | `app.hello` 返回 `protocolVersion`，但客户端尚未据此拒绝不兼容的后端 |
| `data_corrupt` 无文案 | 需要在 `app_strings_ext.dart` 补中英 |
| 后端未打包 | 现在靠 `python backend/main.py` 运行；Phase 6 用 PyInstaller 打成 exe |

### Phase 5 的接线顺序（建议）

1. 启动时 spawn 后端 → `app.hello` → 按 `dataStatus` 决定是否进入只读告警态
2. 用 `resources.list` 替换 `lib/demo/`，先只做只读展示
3. 逐个接写入方法，每接一个跑一遍审计 §5.4 的手工清单
4. 接 `hotkey.start` 与事件流，验证"热键 → 窗口显隐"
5. 接托盘，验证"关闭到托盘 + 二次启动唤醒"
