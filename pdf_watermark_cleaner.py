import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import fitz
import numpy as np
from PIL import Image, ImageTk


@dataclass
class WatermarkModel:
    lab_mean: np.ndarray
    lab_std: np.ndarray
    angle_deg: float


class ScribbleCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.last = None
        self.image = None
        self.photo = None
        self.mask = None
        self.scale = 1.0
        self.offset = (0, 0)

    def set_image(self, image_bgr: np.ndarray):
        self.image = image_bgr.copy()
        h, w = self.image.shape[:2]
        cw = max(self.winfo_width(), 1)
        ch = max(self.winfo_height(), 1)
        self.scale = min(cw / w, ch / h)
        rw, rh = int(w * self.scale), int(h * self.scale)
        resized = cv2.resize(self.image, (rw, rh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.delete("all")
        ox = (cw - rw) // 2
        oy = (ch - rh) // 2
        self.offset = (ox, oy)
        self.create_image(ox, oy, image=self.photo, anchor="nw", tags="img")
        self.mask = np.zeros((h, w), np.uint8)

    def screen_to_img(self, x, y):
        if self.image is None:
            return None
        ox, oy = self.offset
        ix = int((x - ox) / self.scale)
        iy = int((y - oy) / self.scale)
        h, w = self.mask.shape
        if ix < 0 or iy < 0 or ix >= w or iy >= h:
            return None
        return ix, iy

    def draw_brush(self, x1, y1, x2, y2):
        p1 = self.screen_to_img(x1, y1)
        p2 = self.screen_to_img(x2, y2)
        if p1 is None or p2 is None:
            return
        cv2.line(self.mask, p1, p2, 255, 12)
        self.create_line(x1, y1, x2, y2, fill="#00e5ff", width=6, capstyle="round", smooth=True)

    def on_press(self, event):
        self.last = (event.x, event.y)

    def on_drag(self, event):
        if self.last is None:
            return
        self.draw_brush(self.last[0], self.last[1], event.x, event.y)
        self.last = (event.x, event.y)

    def on_release(self, _event):
        self.last = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF水印清理工具（仅用于授权文档）")
        self.geometry("1200x760")
        self.minsize(1000, 650)

        self.input_pdf = None
        self.preview_page = None
        self.current_img = None

        self.build_ui()

    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Button(top, text="选择PDF", command=self.choose_pdf).pack(side="left")
        self.pdf_label = ttk.Label(top, text="未选择文件")
        self.pdf_label.pack(side="left", padx=8)

        ttk.Label(top, text="预览页码:").pack(side="left", padx=(30, 4))
        self.page_var = tk.IntVar(value=1)
        ttk.Entry(top, textvariable=self.page_var, width=6).pack(side="left")
        ttk.Button(top, text="加载预览", command=self.load_preview).pack(side="left", padx=6)

        self.color_k_var = tk.DoubleVar(value=2.8)
        self.angle_tol_var = tk.DoubleVar(value=22)
        self.inpaint_var = tk.IntVar(value=5)

        ttk.Label(top, text="颜色阈值k:").pack(side="left", padx=(30, 2))
        ttk.Entry(top, textvariable=self.color_k_var, width=5).pack(side="left")
        ttk.Label(top, text="角度容差:").pack(side="left", padx=(10, 2))
        ttk.Entry(top, textvariable=self.angle_tol_var, width=5).pack(side="left")
        ttk.Label(top, text="修复半径:").pack(side="left", padx=(10, 2))
        ttk.Entry(top, textvariable=self.inpaint_var, width=5).pack(side="left")

        ttk.Button(top, text="清空涂抹", command=self.clear_mask).pack(side="left", padx=(16, 6))
        ttk.Button(top, text="批量去除并导出", command=self.run).pack(side="left")

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(0, 6))
        self.status = ttk.Label(self, text="请先选择PDF，然后在预览页水印上涂抹。")
        self.status.pack(fill="x", padx=10)

        self.canvas = ScribbleCanvas(self, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, _evt):
        if self.current_img is not None:
            self.canvas.set_image(self.current_img)

    def choose_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF 文件", "*.pdf")])
        if not path:
            return
        self.input_pdf = Path(path)
        self.pdf_label.config(text=str(self.input_pdf))
        self.load_preview()

    def load_preview(self):
        if not self.input_pdf:
            messagebox.showwarning("提示", "请先选择PDF")
            return
        try:
            page_idx = max(0, self.page_var.get() - 1)
            doc = fitz.open(self.input_pdf)
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=180)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            else:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            self.preview_page = page_idx
            self.current_img = img
            self.canvas.set_image(img)
            self.status.config(text="在水印上涂抹几笔后，点击“批量去除并导出”。")
            doc.close()
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    def clear_mask(self):
        if self.current_img is not None:
            self.canvas.set_image(self.current_img)

    def build_model(self):
        mask = self.canvas.mask
        if mask is None or cv2.countNonZero(mask) < 30:
            raise ValueError("请先在水印区域涂抹足够多的像素")

        lab = cv2.cvtColor(self.current_img, cv2.COLOR_BGR2LAB)
        ys, xs = np.where(mask > 0)
        sampled = lab[ys, xs].astype(np.float32)
        mean = sampled.mean(axis=0)
        std = sampled.std(axis=0) + 1.0

        pts = np.column_stack([xs, ys]).astype(np.float32)
        pts = pts - pts.mean(axis=0)
        cov = np.cov(pts.T)
        vals, vecs = np.linalg.eig(cov)
        principal = vecs[:, np.argmax(vals)]
        angle = np.degrees(np.arctan2(principal[1], principal[0]))

        return WatermarkModel(mean, std, float(angle))

    @staticmethod
    def angle_diff(a, b):
        d = abs(a - b) % 180
        return min(d, 180 - d)

    def detect_mask(self, bgr: np.ndarray, model: WatermarkModel):
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        z = np.abs((lab - model.lab_mean) / model.lab_std)
        color_score = z.mean(axis=2)
        color_mask = color_score < self.color_k_var.get()

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        ang = (np.degrees(np.arctan2(gy, gx)) + 180) % 180

        diff = np.vectorize(self.angle_diff)(ang, model.angle_deg)
        orient_mask = diff < self.angle_tol_var.get()
        mag_mask = mag > np.percentile(mag, 60)

        mask = (color_mask & orient_mask & mag_mask).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=1)
        return mask

    def process_all(self, output_pdf: Path):
        model = self.build_model()
        src = fitz.open(self.input_pdf)
        out = fitz.open()

        self.progress["maximum"] = len(src)
        self.progress["value"] = 0

        for i, page in enumerate(src):
            pix = page.get_pixmap(dpi=200)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            else:
                bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            m = self.detect_mask(bgr, model)
            repaired = cv2.inpaint(bgr, m, self.inpaint_var.get(), cv2.INPAINT_TELEA)
            rgb = cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB)

            h, w = rgb.shape[:2]
            p = out.new_page(width=w, height=h)
            png = cv2.imencode('.png', rgb)[1].tobytes()
            p.insert_image(fitz.Rect(0, 0, w, h), stream=png)

            self.progress["value"] = i + 1
            self.status.config(text=f"处理中：第 {i + 1}/{len(src)} 页")
            self.update_idletasks()

        out.save(output_pdf)
        src.close()
        out.close()

    def run(self):
        if not self.input_pdf or self.current_img is None:
            messagebox.showwarning("提示", "请先加载PDF预览")
            return

        out_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF 文件", "*.pdf")],
            initialfile=f"{self.input_pdf.stem}_clean.pdf",
        )
        if not out_path:
            return

        def worker():
            try:
                self.process_all(Path(out_path))
                self.status.config(text=f"完成：{out_path}")
                messagebox.showinfo("完成", f"已导出：\n{out_path}")
            except Exception as e:
                messagebox.showerror("处理失败", str(e))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
