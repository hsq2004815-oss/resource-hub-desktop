# Resource Hub Desktop

一个适用于 Windows 的桌面资源管理工具，用来统一管理：

- 常用网站
- 本地文件夹
- 单个文件

它支持：

- 中英文切换
- 收藏 / 置顶
- 搜索与分类筛选
- 导入 / 导出 JSON 备份
- 本地路径检测
- 文件和文件夹拖拽添加
- 打包为独立 `.exe`

## 普通用户怎么用

如果只是想直接使用，不想安装 Python：

1. 打开 `release\ResourceHub-Ultimate-EXE-20260316`
2. 双击 `ResourceHubPython.exe`

这版是可直接运行的 EXE 版本，不需要额外安装 Python。

## 项目结构

- `resource_hub.pyw`：主程序源码
- `requirements-python.txt`：Python 依赖
- `build-resource-hub-python.ps1`：Windows EXE 打包脚本
- `start-resource-hub-python.bat`：源码版启动脚本
- `Install-ResourceHub-Python-Shortcut.vbs`：源码版桌面快捷方式脚本
- `Install-ResourceHub-Exe-Shortcut.vbs`：EXE 版桌面快捷方式脚本
- `sites.sample.json`：网站示例数据
- `folders.sample.json`：本地资源示例数据
- `release/`：已经打包好的可直接运行 EXE 版本

## 运行源码版

先安装依赖：

```powershell
python -m pip install -r requirements-python.txt
```

运行程序：

```powershell
python resource_hub.pyw
```

也可以直接双击：

- `start-resource-hub-python.bat`

## 打包 EXE

先安装依赖和打包工具：

```powershell
python -m pip install -r requirements-python.txt
python -m pip install pyinstaller
```

然后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build-resource-hub-python.ps1
```

打包产物默认会生成在：

- `dist\ResourceHubPython\ResourceHubPython.exe`

## 数据文件

程序运行时会读写：

- `sites.json`
- `folders.json`

这些真实运行数据文件默认不会提交到 Git。

仓库里的示例数据使用：

- `sites.sample.json`
- `folders.sample.json`

## 说明

- 拖入文件夹时，只会记录这个文件夹本身的路径
- 拖入文件时，只会记录这个文件本身的路径
- 不会把文件夹内部所有内容一次性导入

## License

MIT
