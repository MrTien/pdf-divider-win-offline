from __future__ import annotations

import shutil
import threading
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from PIL import Image

from converter import (
    ConversionCancelled,
    ConversionError,
    ConversionOptions,
    convert_pdf,
    default_output_dir,
    next_available_output_dir,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = PROJECT_ROOT / "test sample" / "生成3张图片.pdf"
TEST_TEMP_ROOT = PROJECT_ROOT / "tmp" / "tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def test_temp_dir() -> Iterator[str]:
    path = TEST_TEMP_ROOT / f"run-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class ConverterTests(unittest.TestCase):
    def test_default_output_dir(self) -> None:
        self.assertEqual(
            default_output_dir(Path(r"D:\资料\演示.pdf")),
            Path(r"D:\资料\演示_逐页图片"),
        )

    def test_next_available_output_dir_uses_number(self) -> None:
        with test_temp_dir() as temp:
            desired = Path(temp) / "结果"
            desired.mkdir()
            (Path(temp) / "结果_2").mkdir()
            self.assertEqual(next_available_output_dir(desired), Path(temp) / "结果_3")

    def test_validation_rejects_bad_settings(self) -> None:
        with self.assertRaises(ConversionError):
            ConversionOptions(SAMPLE_PDF, Path("out"), dpi=71).validated()
        with self.assertRaises(ConversionError):
            ConversionOptions(SAMPLE_PDF, Path("out"), image_format="GIF").validated()

    def test_cancel_before_start_leaves_no_output(self) -> None:
        with test_temp_dir() as temp:
            output = Path(temp) / "cancelled"
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(ConversionCancelled):
                convert_pdf(ConversionOptions(SAMPLE_PDF, output), cancel)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temp).glob(".*.tmp-*")), [])

    def test_corrupt_pdf_has_friendly_error(self) -> None:
        with test_temp_dir() as temp:
            bad_pdf = Path(temp) / "bad.pdf"
            bad_pdf.write_bytes(b"not a pdf")
            with self.assertRaisesRegex(ConversionError, "无法读取 PDF"):
                convert_pdf(ConversionOptions(bad_pdf, Path(temp) / "out"))

    def test_sample_exports_all_jpg_pages(self) -> None:
        progress: list[tuple[int, int, str]] = []
        with test_temp_dir() as temp:
            output = Path(temp) / "样例_逐页图片"
            result = convert_pdf(
                ConversionOptions(SAMPLE_PDF, output),
                progress_callback=lambda current, total, status: progress.append(
                    (current, total, status)
                ),
            )
            files = sorted(result.glob("*.jpg"))
            self.assertEqual(len(files), 4)
            self.assertEqual(files[0].name, "page-001.jpg")
            self.assertEqual(files[-1].name, "page-004.jpg")
            self.assertTrue(all(file.stat().st_size > 0 for file in files))
            with Image.open(files[0]) as image:
                self.assertEqual(image.size, (2000, 1125))
                self.assertEqual(image.mode, "RGB")
            self.assertEqual(progress[-1][0:2], (4, 4))

    def test_png_and_collision_numbering(self) -> None:
        with test_temp_dir() as temp:
            desired = Path(temp) / "png_结果"
            desired.mkdir()
            result = convert_pdf(
                ConversionOptions(
                    SAMPLE_PDF,
                    desired,
                    image_format="PNG",
                    dpi=72,
                )
            )
            self.assertEqual(result.name, "png_结果_2")
            files = sorted(result.glob("*.png"))
            self.assertEqual(len(files), 4)
            with Image.open(files[2]) as image:
                self.assertEqual(image.size, (960, 540))


if __name__ == "__main__":
    unittest.main()
