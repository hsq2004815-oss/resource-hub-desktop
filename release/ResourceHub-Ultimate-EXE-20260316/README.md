# Link Hub

Link Hub 是一个常用网址桌面工具，适合把常打开的网站集中保存、搜索、分类和快速打开。

## 如何使用

- 双击 `LinkHub.exe` 或 `start-link-hub.bat` 打开工具
- 双击 `Install-Desktop-Shortcut.vbs` 创建桌面快捷方式
- 数据默认保存在同目录下的 `sites.json`

## 支持功能

- 新增网站名称、网址、分类和备注
- 点击列表直接管理并打开网站
- 搜索、分类筛选、编辑、删除
- 自动记录每条链接的加入时间
- 中英文切换
- 导出和导入 JSON 备份

## 分享给别人

推荐直接把 `dist\LinkHub-Share.zip` 发给别人。对方解压后：

- 双击 `LinkHub.exe` 即可运行
- 如果需要桌面图标，双击 `Install-Desktop-Shortcut.vbs`

默认分发包里的 `sites.json` 是干净的示例数据，不会带上你当前电脑里的个人收藏。

## 重新生成分发包

如果你后面还想继续发给别人，可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\package-linkhub.ps1
```

生成结果会在：

- `dist\LinkHub-Share`
- `dist\LinkHub-Share.zip`

## 开发文件

- `LinkHub.ps1`：桌面主程序
- `LinkHubLauncher.cs`：EXE 启动器源码
- `build-linkhub.ps1`：生成图标并编译 `LinkHub.exe`
- `package-linkhub.ps1`：生成可分享分发包
