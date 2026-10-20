# Phase 27 — 每站点浏览器 + 网站图标（v1.2.0）

**日期**：2026-10-20
**版本**：v1.2.0

## 需求

1. 收藏的网站来自 Chrome 和 Edge 两个浏览器，希望打开时能自己选浏览器：
   - 主界面能设置「这个网站默认用哪个浏览器打开」；
   - 快速面板里临时换一个浏览器打开；
   - 新导入的书签记住它来自哪个浏览器。
2. 列表里全是通用链接图标，希望换成每个网站自己的图标（favicon）。

## 方案

### 站点浏览器

- 后端从注册表 `SOFTWARE\Clients\StartMenuInternet` 读已安装浏览器（Chrome / Edge / Firefox /
  Brave / Opera / Vivaldi / 360 / QQ / 搜狗等），只给 UI 提供 `id / name / path`，不新增依赖；
  过滤掉 `iexplore`（打不开现代网页）。
- `sites.json` 增加可选字段 `browser`（浏览器 id，空 = 系统默认）。旧数据没有这个字段，
  照样读取；空值不写进 JSON，保持旧格式兼容。
- `resources.open` 支持 `browser` 参数：显式传入就用它，否则用站点保存的值；都为空走系统默认。
  指定浏览器时直接 `Popen([exe, url])`，避免 `ShellExecute` 抢走前台。
- 书签同步按 profile 标签（`Chrome · Default` / `Edge · Default`）推断来源，写入 `browser`。
- Flutter：详情面板「打开方式」下拉保存默认；快速面板右键菜单只作用于这一次打开；
  `browsers.list` 在启动时加载一次。

### 网站图标

- 后端新增 `favicons.py`：
  - 读站点主页，按 `apple-touch-icon` → 大尺寸 PNG → ICO → `/favicon.ico` 的顺序尝试；
  - 校验文件头，PNG / JPEG / GIF / WebP 直接缓存；ICO 里如果是内嵌 PNG 直接取出，否则解析
    BMP DIB（32/24/8/4/1 bpp、调色板、AND 掩码、alpha），用标准库 `zlib` 重编码为 PNG
    （Flutter 不认 ICO）；
  - 每站一个文件，存在 `favicons/<sha1(host)>.png`，`favicons/index.json` 记录 host → 文件名。
- 协议：`favicons.map` 返回缓存表；`favicons.refresh` 立即返回缓存表并在后台线程抓缺失的站点，
  完成后推 `favicons` 事件。抓取不阻塞 UI，失败不写缓存、下次启动重试。
- Flutter：全局 `FaviconIndex`（host → 绝对路径）+ `SiteIcon` 组件；卡片 18px、表格 14px、
  快速面板 16px、详情面板 22px，没有图标时退回原来的通用图标。
- 隐私：只在启动 / 新增链接后访问**用户收藏的网站自身**，没有第三方图标服务；图标缓存后离线可用。
  README 的「不联网」表述已同步修正。

## 验证

- 后端 359 个测试（新增 `test_browsers.py` 8 个、`test_favicons.py` 7 个，协议 / 书签 / service
  用例若干），Flutter 81 个测试（新增站点图标 3 个、右键选浏览器 / 详情下拉 2 个），
  `flutter analyze` 干净。
- 真实站点抓取：GitHub、DeepSeek、小众软件、QQ、网易云、知乎、B 站、百度等 12 站全部拿到图标，
  ICO 转 PNG 正常；OpenAI / chatgpt.com 返回 403，保留通用图标。
- 实机：全新打包后端 `favicons.refresh` 立即返回、后台事件补齐 4 个图标；稳定安装目录重启后
  28 条链接中 21 个显示站点图标，列表 / 网格 / 快速面板 / 详情均生效。

## 说明 / 限制

- 浏览器只做注册表自动扫描，暂不支持手动指定任意 exe 路径。
- 图标只抓一次，站点换图标后需要删掉 `favicons/index.json` 重新抓；没有做定时刷新。
- 没有单独的图标开关（隐私说明已写明只访问收藏站点本身）。
- 指定浏览器打开走 `Popen`，个别情况下窗口不一定抢到前台；默认浏览器路径保持原有行为。
