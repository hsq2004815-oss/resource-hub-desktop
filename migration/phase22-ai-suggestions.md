# Phase 22 — AI 分类建议（DeepSeek 兼容接口，实验性）

- 日期：2026-10-18
- 触发：用户计划后期加入 DeepSeek 的 AI 能力，帮忙整理文件夹和网站；讨论后确定第一版只做
  **未分类资源的分类建议**，且必须由用户确认后才写入。
- 结论：新增可选的「AI 整理」：调用 DeepSeek（或任意 OpenAI 兼容端点）为未分类的网站/文件夹
  生成分类建议 → 审查列表 → 勾选后应用。默认关闭，API Key 用 Windows DPAPI 加密保存。

## 1. 设计原则

| 原则 | 做法 |
|---|---|
| 只建议、不自动改 | `ai.suggestCategories` 只读取、只返回建议；应用走正常的 `resources.update`，由用户点「应用所选」 |
| 默认关闭 | `aiEnabled=false`；设置里明确开关 |
| 隐私最小化 | 链接只发 URL + 名称；文件夹只发名称 + **上级目录名**，绝不发完整本地路径；批量上限 40（可调 1–60） |
| 密钥不落明文 | 单独文件 `.resourcehub-ai-key`，Windows DPAPI（用户作用域）加密 + base64；`settings.json` 里永远没有 key；文件已加 `.gitignore` |
| 失败不影响主程序 | 没有 key/没网/超时/解析失败都只报错，其余功能照常离线可用 |
| 不信任模型输出 | 严格校验：id 必须在本次发送批次里、资源仍为未分类、分类名非空且 ≠ `__uncategorized__`、长度 ≤40；理由截断 200 |
| 防 prompt injection | 网页标题等只作为 JSON 数据传入；模型只能回 JSON 数组，后端校验后才展示，无权调用任何工具 |

## 2. 后端

- 新模块 `backend/resource_hub_core/ai.py`：
  - `AiKeyStore`：DPAPI（`CryptProtectData`/`CryptUnprotectData`，`CRYPTPROTECT_UI_FORBIDDEN`）
    + base64，原子写入 `<app_dir>/.resourcehub-ai-key`；损坏/跨用户会视为未配置。
  - `AiClient`：`POST {baseUrl.rstrip('/')}/chat/completions`，`Authorization: Bearer <key>`；
    body `{model, temperature: 0.1, max_tokens: 1500, messages:[system, user]}`；
    system 要求只返回 `[{"id","category","reason"}]` 并优先复用现有分类；user 是待分类项 JSON。
    解析时容忍 ```json 围栏与前后废话（取第一个 `[` 到最后一个 `]`），失败抛 `AiError`。
  - 同步调用（协议服务一次处理一个请求）：最多阻塞 60s，UI 有"正在请求…"状态；这是刻意取舍，
    避免引入后台任务/多线程协议复杂度。
- `settings.py`：`aiEnabled=false`、`aiBaseUrl=https://api.deepseek.com`、`aiModel=deepseek-chat`；
  URL 只接受 http/https、空/非法回退默认；模型空回退默认。
- `protocol.py`：
  - `ai.status` → `{enabled, configured, baseUrl, model}`
  - `ai.setKey` `{apiKey}` → 空字符串清除；返回 `{configured}`
  - `ai.suggestCategories`（`{limit}` 可选，默认 40，clamp 1–60）→
    `{model, requestCount, existingCategories, suggestions:[{mode,id,name,target,note,currentCategory,suggestedCategory,reason}]}`
  - 错误码：`ai_disabled` / `ai_not_configured` / `ai_request_failed`（detail 安全、不含 key）。
  - 未分类判定用 `models.UNCATEGORIZED`；links 先、folders 后，保留存储顺序；没有未分类项时直接返回空结果、不发 HTTP。

## 3. Flutter

- 「更多」菜单新增 **AI 整理建议**（`Icons.auto_awesome_outlined`）：
  - 未启用/未配置 → 状态栏提示去设置；
  - 请求中 → 状态栏"正在请求 AI 建议…"；
  - 结果为空 → "没有需要整理的未分类资源"；
  - 有建议 → 打开审查对话框（按网站/文件夹分组、默认全选、显示 `原分类 → 建议分类` 与理由），
    底部「应用所选（N）」，兜底「取消」；只有点应用后才逐条 `resources.update`，完成后刷新两个列表并提示
    "已应用 N 条 AI 分类建议"。
- 设置新增「AI 整理（实验）」区块：开关、API 地址、模型、API Key（密文输入 + 「保存密钥」）、
  配置状态（已配置/未配置）。密钥通过 `onSetAiKey` 交给后端保存，不经过 settings.json。
- `BackendClient.call` 增加可选 per-call timeout；`ai.suggestCategories` 用 75s（后端 AI 上限 60s）。
- AI 错误在 UI 里映射成中文提示（`ai_error_*`），网络错误详情会显示在状态栏。

## 4. API / Prompt 形状

```
POST http://127.0.0.1:PORT/chat/completions
Authorization: Bearer sk-...
{
  "model": "deepseek-chat",
  "temperature": 0.1,
  "max_tokens": 1500,
  "messages": [
    {"role":"system","content":"... 只返回 JSON 数组 [{id,category,reason}]；优先复用这些分类: [...]"},
    {"role":"user","content":"[{\"id\":\"<uuid>\",\"kind\":\"link\",\"name\":\"PyPI\",\"url\":\"https://pypi.org/\"},{\"id\":\"<uuid>\",\"kind\":\"folder\",\"name\":\"Logos\",\"parent\":\"Projects\"}]"}
  ]
}
```

- 模型回复被解析成 `[{"id","category","reason"}]`；超时/网络/HTTP/JSON 错误分别映射到安全 detail。
- 成本：1000 条分类大概几毛钱以内（按 DeepSeek 价格），只处理未分类项、有缓存/批量上限，正常使用很便宜。

## 5. 验证

| 项 | 结果 |
|---|---|
| 后端测试 | **326 / 326**（+46 AI 模块、+9 设置；1 个 symlink skip） |
| Flutter 测试 | **73 / 73**（+3：AI 审查后应用、无 key 提示、设置开关与保存 key） |
| `flutter analyze` | 0 issue |
| `verify_ai_suggest.py`（新实机脚本，mock OpenAI 服务 + 真后端子进程） | **14 / 14 PASS** |
| 真实网络调用 | 未用真实 key 调用（无凭据）；接口形状/鉴权头/隐私 payload/错误路径已用 mock 全覆盖 |

`verify_ai_suggest.py` 覆盖：hello 方法表、默认关闭、未启用/未配置错误、设置持久化、DPAPI 写 key
（文件不含明文）、未分类项批量建议、bogus id 被过滤、鉴权头、prompt 不含完整本地路径、应用建议后分类正确、
清除 key 后不可用、网络失败 → `ai_request_failed`（detail 不含 key）。

截图：`migration/screenshots/phase22-ai-settings.png`（设置里的 AI 区块）、
`phase22-ai-menu.png`（「更多」菜单入口）、`phase22-ai-dialog.png`（真实程序 + mock 端点返回的
审查对话框：分组、默认全选、`→ 建议分类`、理由、「应用所选（N）」；右上角是模型名）。
真实 API 手动验证方法：设置里启用 AI、填 DeepSeek API Key 和 `https://api.deepseek.com`、模型
`deepseek-chat` → 保存密钥 → 更多 → AI 整理建议。

## 6. 已知限制 / 后续

- 同步请求：AI 调用期间（最多 60s）后端不处理其他协议请求；HUD 热键可能延迟，属已知取舍。
- 只处理未分类项；不做相似/重复检测、语义搜索、自动改名（后续 Phase 可加）。
- 云端会收到链接 URL 与名称；文件夹只发名称/上级目录名。隐私敏感可把 `aiBaseUrl` 换成
  本地 Ollama 等 OpenAI 兼容端点。
- 模型输出可能有误，所以只展示建议、必须人工勾选；误点也可撤销/改分类。
- Key 是 Windows 用户作用域（DPAPI），换 Windows 用户/换机器需重新填。
