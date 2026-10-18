# Resource Hub 迁移文档索引

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
| [`adr/ADR-001-tray-hotkey-ownership.md`](adr/ADR-001-tray-hotkey-ownership.md) | 托盘/热键归属、导入导出入口、数据覆盖风险 |
| [`adr/ADR-002-native-shell-ownership.md`](adr/ADR-002-native-shell-ownership.md) | Windows 壳层归属（runner vs 后端） |

## 架构一句话

Flutter 负责 UI 与 Windows 壳层（托盘、窗口、对话框、拖拽、单实例）；
Python 后端负责数据读写、全局热键、导入导出与路径操作，二者用 stdio JSON Lines 通信。

## 验证入口

```powershell
# 后端 172 个测试
cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .

# 前端 analyze + 60 个测试
cd ..\app; flutter analyze; flutter test

# 实机壳层（关窗→托盘、热键、二次启动、拖拽)
cd ..; D:\miniconda3\python.exe migration\tools\verify_shell.py

# 实机快速面板（三组热键、窗口变身、Esc 还原、托盘内唤醒）
D:\miniconda3\python.exe migration\tools\verify_quick_panel.py

# 打包 + 干净环境验证
powershell -NoProfile -File .\build-flutter-release.ps1
D:\miniconda3\python.exe migration\tools\verify_release.py
```

产物：`release\ResourceHub-Desktop-20261017-1835\`（Flutter exe + `backend\` 冻结后端）。
原 `resource_hub.pyw` 未修改，仍可独立运行（回滚路径）。
