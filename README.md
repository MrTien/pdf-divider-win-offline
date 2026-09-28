# PDF逐页图片工具

Windows 10/11 64 位本地离线小工具，用于将 PDF 的每一页导出为独立的 JPG 或 PNG 图片。

## 快速开始

开发者首次运行直接执行：

```powershell
.\dev.ps1
```

脚本会把依赖安装到项目内的 `.dev-packages`，然后启动程序。其他常用入口：

```powershell
.\dev.ps1 test   # 运行全部测试
.\dev.ps1 build  # 构建 Windows 便携版
```

需要接手维护时，请先阅读 [HANDOFF.md](HANDOFF.md)。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python src/app.py
```

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## 构建便携版

```powershell
.\build.ps1
```

构建结果位于 `dist\PDF逐页图片工具`。将整个文件夹复制到其他 Windows 10/11 64 位电脑即可使用；目标电脑无需安装 Python。

默认输出到 PDF 旁的 `原文件名_逐页图片` 文件夹。若目录已存在，会自动选择 `_2`、`_3` 等新名称，不会覆盖旧结果。
