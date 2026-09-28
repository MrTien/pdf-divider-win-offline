from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium
from PIL import Image


ProgressCallback = Callable[[int, int, str], None]


class ConversionError(RuntimeError):
    """A user-facing PDF conversion error."""


class ConversionCancelled(RuntimeError):
    """Raised when the user requests cancellation."""


@dataclass(frozen=True)
class ConversionOptions:
    pdf_path: Path
    output_dir: Path
    image_format: str = "JPG"
    dpi: int = 150
    jpeg_quality: int = 92

    def validated(self) -> "ConversionOptions":
        pdf_path = Path(self.pdf_path).expanduser()
        output_dir = Path(self.output_dir).expanduser()
        image_format = self.image_format.upper()

        if not pdf_path.is_file():
            raise ConversionError("请选择存在的 PDF 文件。")
        if pdf_path.suffix.lower() != ".pdf":
            raise ConversionError("所选文件不是 PDF 文件。")
        if image_format not in {"JPG", "PNG"}:
            raise ConversionError("图片格式只能选择 JPG 或 PNG。")
        if not 72 <= self.dpi <= 600:
            raise ConversionError("DPI 必须在 72 到 600 之间。")
        if not 1 <= self.jpeg_quality <= 100:
            raise ConversionError("JPG 质量必须在 1 到 100 之间。")
        if output_dir == pdf_path or output_dir.is_file():
            raise ConversionError("输出位置必须是文件夹路径。")

        return ConversionOptions(
            pdf_path=pdf_path,
            output_dir=output_dir,
            image_format=image_format,
            dpi=self.dpi,
            jpeg_quality=self.jpeg_quality,
        )


def default_output_dir(pdf_path: Path) -> Path:
    pdf_path = Path(pdf_path)
    return pdf_path.parent / f"{pdf_path.stem}_逐页图片"


def next_available_output_dir(desired: Path) -> Path:
    desired = Path(desired)
    if not desired.exists():
        return desired

    index = 2
    while True:
        candidate = desired.with_name(f"{desired.name}_{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _rgb_on_white(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        rgba.close()
        return background
    return image.convert("RGB")


def _friendly_open_error(error: Exception) -> ConversionError:
    message = str(error).lower()
    if "password" in message or "encrypted" in message or "security" in message:
        return ConversionError("此 PDF 需要密码，当前版本暂不支持加密 PDF。")
    return ConversionError("无法读取 PDF。文件可能已损坏、格式异常或受到密码保护。")


def convert_pdf(
    options: ConversionOptions,
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    """Convert all PDF pages and atomically publish the completed output folder."""

    options = options.validated()
    cancel_event = cancel_event or threading.Event()
    progress_callback = progress_callback or (lambda _current, _total, _status: None)
    staging_dir: Path | None = None
    document = None

    try:
        try:
            document = pdfium.PdfDocument(str(options.pdf_path))
        except Exception as error:
            raise _friendly_open_error(error) from error

        total_pages = len(document)
        if total_pages < 1:
            raise ConversionError("PDF 中没有可转换的页面。")

        parent = options.output_dir.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            staging_dir = parent / f".{options.output_dir.name}.tmp-{uuid.uuid4().hex[:10]}"
            staging_dir.mkdir()
        except OSError as error:
            raise ConversionError(f"无法创建输出目录，请检查写入权限：\n{parent}") from error

        extension = "jpg" if options.image_format == "JPG" else "png"
        number_width = max(3, len(str(total_pages)))
        # Avoid a floating-point ceil turning 2000 pixels into 2001 at 150 DPI.
        render_scale = options.dpi / 72.0 - 1e-12
        progress_callback(0, total_pages, f"准备转换，共 {total_pages} 页")

        for page_index in range(total_pages):
            if cancel_event.is_set():
                raise ConversionCancelled("转换已取消。")

            page_number = page_index + 1
            try:
                page = document[page_index]
                try:
                    bitmap = page.render(scale=render_scale)
                    try:
                        image = bitmap.to_pil()
                        try:
                            image.load()
                            output_file = staging_dir / (
                                f"page-{page_number:0{number_width}d}.{extension}"
                            )

                            if cancel_event.is_set():
                                raise ConversionCancelled("转换已取消。")

                            if options.image_format == "JPG":
                                rgb_image = _rgb_on_white(image)
                                try:
                                    rgb_image.save(
                                        output_file,
                                        format="JPEG",
                                        quality=options.jpeg_quality,
                                        optimize=True,
                                        progressive=True,
                                        dpi=(options.dpi, options.dpi),
                                    )
                                finally:
                                    if rgb_image is not image:
                                        rgb_image.close()
                            else:
                                image.save(
                                    output_file,
                                    format="PNG",
                                    optimize=True,
                                    dpi=(options.dpi, options.dpi),
                                )
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            except ConversionCancelled:
                raise
            except Exception as error:
                raise ConversionError(f"第 {page_number} 页转换失败：{error}") from error

            progress_callback(
                page_number,
                total_pages,
                f"正在转换第 {page_number} / {total_pages} 页",
            )

        if cancel_event.is_set():
            raise ConversionCancelled("转换已取消。")

        final_dir = next_available_output_dir(options.output_dir)
        while True:
            try:
                staging_dir.rename(final_dir)
                staging_dir = None
                break
            except FileExistsError:
                final_dir = next_available_output_dir(options.output_dir)
            except OSError as error:
                raise ConversionError(f"无法发布转换结果，请检查输出目录：\n{final_dir}") from error

        progress_callback(total_pages, total_pages, "转换完成")
        return final_dir
    finally:
        if document is not None:
            document.close()
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
