# PDF逐页图片工具 - 维护交接

## 1. 项目现状

- 私有仓库：<https://github.com/MrTien/pdf-divider-win-offline>
- 目标平台：Windows 10/11 64 位。
- 运行方式：Tkinter 中文界面，PDFium 离线渲染，Pillow 输出 JPG/PNG。
- 默认参数：JPG、150 DPI、质量 92。
- 当前测试样例：`test sample/生成3张图片.pdf`，共 4 页。
- 便携版由 PyInstaller `onedir` 模式构建；`dist/` 是本地产物，不进入 Git。

## 2. 新环境快速启动

前置条件只有 Windows 64 位和 Python 3.12。进入项目根目录后：

```powershell
.\dev.ps1
```

脚本会将固定版本依赖放到项目内的 `.dev-packages/`，不会修改项目源码，也不要求全局安装依赖。

常用命令：

```powershell
.\dev.ps1 run    # 启动开发版 GUI，默认动作
.\dev.ps1 test   # 运行单元测试和样例完整转换
.\dev.ps1 build  # 生成 dist\PDF逐页图片工具 便携目录
```

## 3. 代码地图

- `src/app.py`：Tkinter 界面、后台工作线程、进度消息、取消和关闭窗口流程。
- `src/converter.py`：参数校验、PDFium 逐页渲染、图片编码、临时目录与最终发布。
- `tests/test_converter.py`：样例转换、PNG/JPG、取消、损坏文件和重名编号测试。
- `PDF逐页图片工具.spec`：PyInstaller 打包定义，明确排除不需要的 NumPy/psutil。
- `build.ps1`：安装隔离构建依赖、打包并复制说明与完整第三方许可证。

## 4. 必须保持的行为

1. 转换期间只处理一页，避免大 PDF 占用过多内存。
2. 先写入隐藏的 `.目标名.tmp-随机值` 目录；成功后才改名为正式输出目录。
3. 取消或失败必须删除本次临时目录，不能留下看似完整的结果。
4. 已存在输出目录时使用 `_2`、`_3` 等新名称，禁止覆盖用户文件。
5. 页码至少三位，从 `page-001` 开始；超过 999 页时自动扩展位数。
6. JPG 透明区域合成白色背景并输出 RGB；PNG 保持无损。
7. DPI 仅允许 72–600，JPG 质量仅允许 1–100。
8. GUI 更新只能发生在 Tk 主线程；工作线程通过队列传递进度和结果。

## 5. 测试与验收

提交前至少运行：

```powershell
.\dev.ps1 test
.\dev.ps1 build
```

样例默认转换的验收条件：

- 生成 4 张图片，名称为 `page-001.jpg` 到 `page-004.jpg`。
- 150 DPI 时页面尺寸为 2000×1125，模式为 RGB。
- 首页、中间页、末页无黑块、乱码、裁切或方向错误。
- 转换目录内不存在 `.tmp-*` 残留。
- 最终 `PDF逐页图片工具.exe` 可在没有 Python 的 Windows 64 位机器上启动。

应用内保留了 `--test-convert <pdf> <output>` 自动验收入口。它不属于普通用户界面，用于确认打包后的 EXE 能真实调用其内置运行库完成转换。

## 6. 构建与发布

`build.ps1` 首次运行会下载固定版本的 PyInstaller、pypdfium2 和 Pillow 到 `.build-packages/`。构建结果位于：

```text
dist\PDF逐页图片工具\
```

发布时必须复制整个文件夹，不能只复制 EXE。便携目录应包含：

- `PDF逐页图片工具.exe`
- `_internal/`
- `使用说明.txt`
- `THIRD_PARTY_NOTICES.txt`
- `licenses/`

`.build-packages/`、`build/`、`dist/`、`.dev-packages/` 都是可再生目录，已在 `.gitignore` 中排除。

## 7. 常见维护点

- 修改默认 DPI 或 JPG 质量：同时更新 `src/app.py` 的默认值、`使用说明.txt` 和相关测试。
- 升级 pypdfium2/Pillow：同步修改 `requirements.txt`，完整执行测试并重新视觉抽查三页。
- 升级 PyInstaller：修改 `requirements-build.txt`，确认 `_internal/pypdfium2_raw` 和 PDFium DLL 被正确打包。
- 若包体突然变大：检查是否误带入 `numpy`；当前 spec 已明确排除它。
- 若中文路径失败：优先检查是否把 `Path` 转成了非 Unicode 的外部命令参数；当前实现直接通过 Python/PDFium 处理 Unicode 路径。

## 8. Git 约定

- 默认分支：`main`。
- 仓库只跟踪源码、测试、构建定义、说明和测试 PDF，不跟踪生成的便携包。
- 提交信息使用简短英文祈使句，例如 `Add page range export`。
- 功能修改不得跳过 `dev.ps1 test`；发布修改还必须执行 `dev.ps1 build`。
