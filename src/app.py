from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from converter import (
    ConversionCancelled,
    ConversionError,
    ConversionOptions,
    convert_pdf,
    default_output_dir,
)


APP_NAME = "PDF逐页图片工具"


class PdfExporterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("720x510")
        self.root.minsize(680, 490)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.pdf_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.format_var = tk.StringVar(value="JPG")
        self.dpi_var = tk.StringVar(value="150")
        self.quality_var = tk.StringVar(value="92")
        self.status_var = tk.StringVar(value="请选择一个 PDF 文件")
        self.progress_var = tk.DoubleVar(value=0)

        self._messages: queue.Queue[tuple] = queue.Queue()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._last_output: Path | None = None
        self._close_after_cancel = False
        self._controls: list[tk.Widget] = []

        self._configure_style()
        self._build_ui()
        self._update_quality_state()
        self.root.after(100, self._poll_messages)

    def _configure_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Subtitle.TLabel", foreground="#555555")
        style.configure("Status.TLabel", foreground="#333333")
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=(28, 22, 28, 20))
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)

        ttk.Label(container, text=APP_NAME, style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            container,
            text="将 PDF 的每一页导出为独立图片，全程在本机离线完成。",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 22))

        ttk.Label(container, text="PDF 文件").grid(row=2, column=0, sticky="w", pady=6)
        pdf_entry = ttk.Entry(container, textvariable=self.pdf_var)
        pdf_entry.grid(row=2, column=1, sticky="ew", padx=(12, 8), pady=6)
        pdf_button = ttk.Button(container, text="选择…", command=self._choose_pdf)
        pdf_button.grid(row=2, column=2, sticky="ew", pady=6)

        ttk.Label(container, text="输出文件夹").grid(row=3, column=0, sticky="w", pady=6)
        output_entry = ttk.Entry(container, textvariable=self.output_var)
        output_entry.grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=6)
        output_button = ttk.Button(container, text="更改…", command=self._choose_output_parent)
        output_button.grid(row=3, column=2, sticky="ew", pady=6)

        settings = ttk.LabelFrame(container, text="图片设置", padding=(16, 12))
        settings.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(16, 14))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)
        settings.columnconfigure(5, weight=1)

        ttk.Label(settings, text="格式").grid(row=0, column=0, sticky="w")
        format_combo = ttk.Combobox(
            settings,
            textvariable=self.format_var,
            values=("JPG", "PNG"),
            state="readonly",
            width=9,
        )
        format_combo.grid(row=0, column=1, sticky="ew", padx=(8, 18))
        format_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_quality_state())

        ttk.Label(settings, text="DPI").grid(row=0, column=2, sticky="w")
        dpi_combo = ttk.Combobox(
            settings,
            textvariable=self.dpi_var,
            values=("72", "96", "150", "200", "300", "600"),
            width=9,
        )
        dpi_combo.grid(row=0, column=3, sticky="ew", padx=(8, 18))

        ttk.Label(settings, text="JPG 质量").grid(row=0, column=4, sticky="w")
        self.quality_spinbox = ttk.Spinbox(
            settings,
            from_=1,
            to=100,
            textvariable=self.quality_var,
            width=9,
        )
        self.quality_spinbox.grid(row=0, column=5, sticky="ew", padx=(8, 0))

        progress_frame = ttk.Frame(container)
        progress_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 12))
        progress_frame.columnconfigure(0, weight=1)
        ttk.Label(progress_frame, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew")

        actions = ttk.Frame(container)
        actions.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        self.open_button = ttk.Button(
            actions,
            text="打开输出目录",
            command=self._open_last_output,
            state="disabled",
        )
        self.open_button.grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(
            actions,
            text="取消",
            command=self._cancel,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, padx=(8, 8))
        self.start_button = ttk.Button(
            actions,
            text="开始转换",
            command=self._start,
            style="Accent.TButton",
        )
        self.start_button.grid(row=0, column=2)

        ttk.Label(
            container,
            text="提示：已有同名目录时会自动创建带编号的新目录，不会覆盖旧文件。",
            style="Subtitle.TLabel",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(22, 0))

        self._controls = [
            pdf_entry,
            pdf_button,
            output_entry,
            output_button,
            format_combo,
            dpi_combo,
            self.quality_spinbox,
        ]

    def _choose_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="选择 PDF 文件",
            filetypes=(("PDF 文件", "*.pdf"), ("所有文件", "*.*")),
        )
        if not filename:
            return
        pdf_path = Path(filename)
        self.pdf_var.set(str(pdf_path))
        self.output_var.set(str(default_output_dir(pdf_path)))
        self.status_var.set("已选择 PDF，可以开始转换")

    def _choose_output_parent(self) -> None:
        pdf_text = self.pdf_var.get().strip()
        initial = Path(pdf_text).parent if pdf_text else Path.cwd()
        parent = filedialog.askdirectory(title="选择保存位置", initialdir=initial)
        if not parent:
            return
        if pdf_text:
            self.output_var.set(str(Path(parent) / f"{Path(pdf_text).stem}_逐页图片"))
        else:
            self.output_var.set(str(Path(parent) / "PDF_逐页图片"))

    def _update_quality_state(self) -> None:
        if not hasattr(self, "quality_spinbox"):
            return
        state = "normal" if self.format_var.get() == "JPG" else "disabled"
        self.quality_spinbox.configure(state=state)

    def _parse_options(self) -> ConversionOptions:
        try:
            dpi = int(self.dpi_var.get().strip())
        except ValueError as error:
            raise ConversionError("DPI 请输入 72 到 600 之间的整数。") from error
        try:
            quality = int(self.quality_var.get().strip())
        except ValueError as error:
            raise ConversionError("JPG 质量请输入 1 到 100 之间的整数。") from error

        return ConversionOptions(
            pdf_path=Path(self.pdf_var.get().strip()),
            output_dir=Path(self.output_var.get().strip()),
            image_format=self.format_var.get(),
            dpi=dpi,
            jpeg_quality=quality,
        ).validated()

    def _set_running(self, running: bool) -> None:
        for control in self._controls:
            if control is self.quality_spinbox:
                continue
            if isinstance(control, ttk.Combobox) and control is self._controls[4]:
                control.configure(state="disabled" if running else "readonly")
            else:
                control.configure(state="disabled" if running else "normal")
        if running:
            self.quality_spinbox.configure(state="disabled")
        else:
            self._update_quality_state()
        self.start_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def _start(self) -> None:
        try:
            options = self._parse_options()
        except ConversionError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.root)
            return

        self._last_output = None
        self.open_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("正在准备转换…")
        self._cancel_event = threading.Event()
        self._set_running(True)

        self._worker = threading.Thread(
            target=self._run_conversion,
            args=(options,),
            name="pdf-converter",
            daemon=True,
        )
        self._worker.start()

    def _run_conversion(self, options: ConversionOptions) -> None:
        try:
            result = convert_pdf(
                options,
                cancel_event=self._cancel_event,
                progress_callback=lambda current, total, status: self._messages.put(
                    ("progress", current, total, status)
                ),
            )
            self._messages.put(("done", result))
        except ConversionCancelled:
            self._messages.put(("cancelled",))
        except ConversionError as error:
            self._messages.put(("error", str(error)))
        except Exception as error:
            self._messages.put(("error", f"发生未预期错误：{error}"))

    def _poll_messages(self) -> None:
        try:
            while True:
                message = self._messages.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _, current, total, status = message
                    self.progress_var.set((current / total * 100) if total else 0)
                    self.status_var.set(status)
                elif kind == "done":
                    self._finish_success(Path(message[1]))
                elif kind == "cancelled":
                    self._finish_cancelled()
                elif kind == "error":
                    self._finish_error(message[1])
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._poll_messages)

    def _finish_success(self, output_dir: Path) -> None:
        self._worker = None
        self._last_output = output_dir
        self._set_running(False)
        self.open_button.configure(state="normal")
        self.progress_var.set(100)
        self.status_var.set(f"转换完成：{output_dir.name}")
        if self._close_after_cancel:
            self.root.destroy()
            return
        if messagebox.askyesno(
            APP_NAME,
            f"转换完成。\n\n输出位置：\n{output_dir}\n\n是否立即打开？",
            parent=self.root,
        ):
            self._open_path(output_dir)

    def _finish_cancelled(self) -> None:
        self._worker = None
        self._set_running(False)
        self.progress_var.set(0)
        self.status_var.set("转换已取消，临时文件已清理")
        if self._close_after_cancel:
            self.root.destroy()

    def _finish_error(self, message: str) -> None:
        self._worker = None
        self._set_running(False)
        self.progress_var.set(0)
        self.status_var.set("转换失败")
        if self._close_after_cancel:
            self.root.destroy()
            return
        messagebox.showerror(APP_NAME, message, parent=self.root)

    def _cancel(self) -> None:
        if self._worker and self._worker.is_alive():
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status_var.set("正在取消并清理临时文件…")

    def _open_last_output(self) -> None:
        if self._last_output and self._last_output.exists():
            self._open_path(self._last_output)

    def _open_path(self, path: Path) -> None:
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as error:
            messagebox.showerror(APP_NAME, f"无法打开输出目录：{error}", parent=self.root)

    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno(
                APP_NAME,
                "转换仍在进行。是否取消转换并退出？",
                parent=self.root,
            ):
                return
            self._close_after_cancel = True
            self._cancel()
            return
        self.root.destroy()


def enable_windows_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def _run_test_conversion(arguments: list[str]) -> int:
    if len(arguments) != 3:
        return 2
    try:
        convert_pdf(
            ConversionOptions(
                pdf_path=Path(arguments[1]),
                output_dir=Path(arguments[2]),
            )
        )
    except (ConversionError, ConversionCancelled):
        return 1
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--test-convert":
        return _run_test_conversion(sys.argv[1:])

    enable_windows_dpi_awareness()
    root = tk.Tk()
    PdfExporterApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
