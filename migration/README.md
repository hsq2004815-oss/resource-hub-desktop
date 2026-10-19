# 抽屉 Drawer 迁移文档索引

把 `resource_hub.pyw`（Python Tkinter，单文件）迁移为 **Flutter 前端 + Python 后端**的完整记录。
按顺序阅读：

| 文档 | 内容 |
|---|---|
| [`phase1-audit.md`](phase1-audit.md) | 原应用审计、功能清单、回归测试方案、风险；§9 是接手复核勘误 |
| [`phase2-design-system.md`](phase2-design-system.md) | Material 3 设计系统、组件库、真实缺陷记录 |
| [`phase3-business-layer.md`](phase3-business-layer.md) | 无 UI 业务层拆分、故意保留的旧行为 |
| [`phase4-ipc-protocol.md`](phase4-ipc-protocol.md) | stdio JSON Lines 协议：帧格式、方法表、错误码 |
| [`phase5-ui-wiring.md`](phase5-ui-wiring.md) | 前端接真实后端、启动失败处理 |
| [`phase5b-shell-integration.md`](phase5b-shell-integration.md) | 托盘 / 热键显隐 / 拖拽 / 文件对话框 / 导入导出 / 开机启动 / 单实例 |
| [`phase6-packaging.md`](phase6-packaging.md) | 打包产物、构建方式、干净环境验证、已知风险 |
| [`phase7-ui-top-layout.md`](phase7-ui-top-layout.md) | 顶部布局重构（紧凑应用栏、统一表面色、添加资源对话框、列表/网格切换） |
| [`phase8-drag-reorder.md`](phase8-drag-reorder.md) | 手动拖动排序：数组顺序即顺序、一次性迁移、列表/网格拖拽、撤销、按时间重排 |
| [`phase9-folder-preview.md`](phase9-folder-preview.md) | 右侧详情面板：文件夹 mind map、懒加载展开、缩放/平移、添加为资源 |
| [`phase10-no-top-bar.md`](phase10-no-top-bar.md) | 删除内容区 56px 顶部栏，设置入口移到工作区工具栏 |
| [`phase11-toolbar-cleanup.md`](phase11-toolbar-cleanup.md) | 工具栏精简：导出/导入移入「更多」菜单 |
| [`phase12-controls-polish.md`](phase12-controls-polish.md) | 新增资源按钮按 M3 重做、分类筛选收窄 |
| [`phase13-list-surface.md`](phase13-list-surface.md) | 列表视图去掉白色面板，使用网格视图同款页面底色 |
| [`phase14-row-white.md`](phase14-row-white.md) | 列表行恢复白色高亮（页面底色不变） |
| [`phase15-add-icon.md`](phase15-add-icon.md) | 新增资源改为圆形加号图标按钮（文字进 tooltip） |
| [`phase16-quick-panel.md`](phase16-quick-panel.md) | 快捷键直达树状图：窗口变身 480×600 HUD、三组可配置热键、网站树/文件夹树、输入过滤 |
| [`phase17-bookmark-sync.md`](phase17-bookmark-sync.md) | 浏览器书签自动同步：只读 Chrome/Edge 本地书签、文件夹做分类、只新增、启动导入 + 监听、设置开关与自定义目录 |
| [`phase18-bookmark-extension.md`](phase18-bookmark-extension.md) | 双向书签同步：浏览器扩展 + 本机回环桥，工具删除→浏览器取消收藏，浏览器删除/改名→工具同步 |
| [`phase19-context-menu.md`](phase19-context-menu.md) | 资源管理器右键菜单：右键文件夹添加到资源库并弹窗选中；设置里可开关（Win11 在「显示更多选项」） |
| [`phase20-rename.md`](phase20-rename.md) | 产品改名「常用资源工具」→「抽屉 Drawer」：仅显示名（标题/托盘/菜单文案/扩展名/快捷方式），exe 与数据路径不变 |
| [`phase21-grid-reorder.md`](phase21-grid-reorder.md) | 网格拖动排序重做：拖动中卡片实时让位 + 180ms 动画 + 虚线占位，松手才保存（对齐列表视图手感） |
| [`phase22-ai-suggestions.md`](phase22-ai-suggestions.md) | AI 分类建议（实验性）：DeepSeek/OpenAI 兼容端点、仅建议不自动改、DPAPI 加密 key、审查后应用 |
| [`phase23-mindmap-drag.md`](phase23-mindmap-drag.md) | 思维导图拖动修复：连线层吞掉指针（内容矩形内全拖不动）+ 拖动重建整树导致发涩；命中测试、node 拖动平移、notifier/布局缓存 |
| [`phase24-quick-panel-maximized.md`](phase24-quick-panel-maximized.md) | 快速面板尺寸修复：主窗口最大化时快捷键会弹出全屏大小的面板；`IsZoomed` 处理 + 关闭后恢复最大化 |
| [`phase25-chrome-account-bookmarks.md`](phase25-chrome-account-bookmarks.md) | Chrome 书签同步修复：登录账号后书签写在 `AccountBookmarks`，旧代码只读 `Bookmarks`；两种文件合并读取 |
| [`adr/ADR-001-tray-hotkey-ownership.md`](adr/ADR-001-tray-hotkey-ownership.md) | 托盘/热键归属、导入导出入口、数据覆盖风险 |
| [`adr/ADR-002-native-shell-ownership.md`](adr/ADR-002-native-shell-ownership.md) | Windows 壳层归属（runner vs 后端） |

## 架构一句话

Flutter 负责 UI 与 Windows 壳层（托盘、窗口、对话框、拖拽、单实例）；
Python 后端负责数据读写、全局热键、导入导出与路径操作，二者用 stdio JSON Lines 通信。

## 验证入口

```powershell
# 后端 329 个测试
cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 前端 analyze + 75 个测试
cd ..\app; flutter analyze; flutter test

# 实机壳层（关窗→托盘、热键、二次启动、拖拽)
cd ..; D:\miniconda3\python.exe migration\tools\verify_shell.py

# 实机快速面板（三组热键、窗口变身、Esc 还原、托盘内唤醒）
D:\miniconda3\python.exe migration\tools\verify_quick_panel.py

# 实机快速面板尺寸（普通 / 最大化窗口下都必须是 480×600 HUD；Phase 24）
D:\miniconda3\python.exe migration\tools\verify_quick_panel_size.py --build release\ResourceHub-Desktop-20261019-0650

# 实机浏览器书签同步（临时复制发布包 + 假浏览器配置，不碰真实数据目录）
D:\miniconda3\python.exe migration\tools\verify_bookmark_sync.py

# 实机资源管理器右键菜单（注册表 + --add-folder；会临时改数据并还原）
D:\miniconda3\python.exe migration\tools\verify_context_menu.py

# AI 分类建议端到端（mock OpenAI 服务 + 真后端；不需要真实 key）
D:\miniconda3\python.exe migration\tools\verify_ai_suggest.py

# 端到端双向书签同步（真后端 + 模拟扩展，不启动浏览器）
D:\miniconda3\python.exe migration\tools\verify_bookmark_extension.py

# 实机思维导图拖动（临时复制发布包 + 像素位移断言；旧包可复现"内容区拖不动"）
D:\miniconda3\python.exe migration\tools\verify_mind_map_drag.py --build release\ResourceHub-Desktop-20261018-2215

# 浏览器扩展协议自检（不需要浏览器）
cd bookmark-extension; D:\miniconda3\python.exe check_protocol.py

# 打包 + 干净环境验证
powershell -NoProfile -File .\build-flutter-release.ps1
D:\miniconda3\python.exe migration\tools\verify_release.py
```

产物：`release\ResourceHub-Desktop-20261017-1835\`（Flutter exe + `backend\` 冻结后端）。
原 `resource_hub.pyw` 未修改，仍可独立运行（回滚路径）。
