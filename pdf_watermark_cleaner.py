import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk


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

    def set_image(self, image_bgr: np.ndarray, preserve_mask: bool = False):
        self.image = image_bgr.copy()
        h, w = self.image.shape[:2]
        cw = max(self.winfo_width(), 1)
        ch = max(self.winfo_height(), 1)
        self.scale = min(cw / w, ch / h)
        rw, rh = max(1, int(w * self.scale)), max(1, int(h * self.scale))
        resized = cv2.resize(self.image, (rw, rh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.delete("all")
        ox = (cw - rw) // 2
        oy = (ch - rh) // 2
        self.offset = (ox, oy)
        self.create_image(ox, oy, image=self.photo, anchor="nw", tags="img")
        if (not preserve_mask) or self.mask is None or self.mask.shape != (h, w):
            self.mask = np.zeros((h, w), np.uint8)

        # 重绘已有涂抹轨迹，避免窗口缩放时样本丢失
        ys, xs = np.where(self.mask > 0)
        for y, x in zip(ys[::10], xs[::10]):
            sx = int(x * self.scale) + ox
            sy = int(y * self.scale) + oy
            self.create_oval(sx - 2, sy - 2, sx + 2, sy + 2, fill="#00e5ff", outline="")

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
        cv2.line(self.mask, p1, p2, 255, 14)
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
        self.title("PDF智能去水印工具（中文增强版）")
        self.geometry("1360x860")
        self.minsize(1160, 720)

        self._setup_style()

        self.input_pdf = None
        self.preview_page = None
        self.current_img = None
        self.last_preview_processed = None

        self.build_ui()

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabelframe", padding=8)
        style.configure("TButton", padding=(10, 6))
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 11, "bold"))

    def build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        header = ttk.Label(root, text="支持：涂抹样本 + 输入水印文字（可处理中/英文、倾斜水印）", style="Header.TLabel")
        header.pack(fill="x", pady=(0, 8))

        panel = ttk.Panedwindow(root, orient="horizontal")
        panel.pack(fill="both", expand=True)

        left = ttk.Frame(panel)
        right = ttk.Frame(panel)
        panel.add(left, weight=1)
        panel.add(right, weight=3)

        file_box = ttk.LabelFrame(left, text="文件与页面")
        file_box.pack(fill="x", pady=(0, 8))
        ttk.Button(file_box, text="选择PDF", command=self.choose_pdf).pack(fill="x", pady=3)
        self.pdf_label = ttk.Label(file_box, text="未选择文件", wraplength=280)
        self.pdf_label.pack(fill="x", pady=3)

        page_row = ttk.Frame(file_box)
        page_row.pack(fill="x", pady=3)
        ttk.Label(page_row, text="预览页码").pack(side="left")
        self.page_var = tk.IntVar(value=1)
        ttk.Entry(page_row, textvariable=self.page_var, width=6).pack(side="left", padx=6)
        ttk.Button(page_row, text="加载预览", command=self.load_preview).pack(side="left")

        mode_box = ttk.LabelFrame(left, text="去除策略")
        mode_box.pack(fill="x", pady=(0, 8))

        self.mode_var = tk.StringVar(value="混合模式")
        ttk.Label(mode_box, text="模式").pack(anchor="w")
        mode = ttk.Combobox(mode_box, textvariable=self.mode_var, values=["混合模式", "仅涂抹模式", "仅文字模式"], state="readonly")
        mode.pack(fill="x", pady=3)

        ttk.Label(mode_box, text="水印文字（可选，支持中文）").pack(anchor="w")
        self.watermark_text_var = tk.StringVar(value="")
        ttk.Entry(mode_box, textvariable=self.watermark_text_var).pack(fill="x", pady=3)

        param_box = ttk.LabelFrame(left, text="参数")
        param_box.pack(fill="x", pady=(0, 8))
        self.color_k_var = tk.DoubleVar(value=2.6)
        self.angle_tol_var = tk.DoubleVar(value=24)
        self.inpaint_var = tk.IntVar(value=4)

        self._add_slider(param_box, "颜色阈值 k", self.color_k_var, 1.2, 5.0)
        self._add_slider(param_box, "角度容差", self.angle_tol_var, 8, 45)
        self._add_slider(param_box, "修复半径", self.inpaint_var, 2, 9)

        action_box = ttk.LabelFrame(left, text="操作")
        action_box.pack(fill="x")
        ttk.Button(action_box, text="清空涂抹", command=self.clear_mask).pack(fill="x", pady=3)
        ttk.Button(action_box, text="预览当前页去水印", command=self.preview_current_page).pack(fill="x", pady=3)
        ttk.Button(action_box, text="批量去除并导出", command=self.run).pack(fill="x", pady=3)

        self.progress = ttk.Progressbar(left, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 4))
        self.status = ttk.Label(left, text="请选择 PDF 并在左图上涂抹，或输入水印文字。", wraplength=300)
        self.status.pack(fill="x")

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)

        tab_before = ttk.Frame(notebook)
        tab_after = ttk.Frame(notebook)
        notebook.add(tab_before, text="原始预览（可涂抹）")
        notebook.add(tab_after, text="去除后预览")

        self.canvas = ScribbleCanvas(tab_before, bg="#1f1f1f", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas.bind("<Configure>", self._on_resize)

        self.result_canvas = ScribbleCanvas(tab_after, bg="#1f1f1f", highlightthickness=0)
        self.result_canvas.pack(fill="both", expand=True, padx=4, pady=4)

    @staticmethod
    def _add_slider(parent, text, variable, min_v, max_v):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=text).pack(side="left")
        ttk.Scale(row, from_=min_v, to=max_v, variable=variable).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(row, textvariable=variable, width=6).pack(side="right")

    def _on_resize(self, _evt):
        if self.current_img is not None:
            self.canvas.set_image(self.current_img, preserve_mask=True)

    def set_status(self, text: str):
        self.status.config(text=text)
        self.update_idletasks()

    def choose_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF 文件", "*.pdf")])
        if not path:
            return
        self.input_pdf = Path(path)
        self.pdf_label.config(text=str(self.input_pdf))
        self.load_preview()

    def load_preview(self):
        if not self.input_pdf:
            messagebox.showwarning("提示", "请先选择 PDF")
            return
        try:
            page_idx = max(0, self.page_var.get() - 1)
            doc = fitz.open(self.input_pdf)
            if page_idx >= len(doc):
                raise ValueError(f"页码超出范围，最大 {len(doc)}")
            img = self._render_page(doc[page_idx], dpi=180)
            doc.close()
            self.preview_page = page_idx
            self.current_img = img
            self.canvas.set_image(img)
            self.result_canvas.set_image(img)
            self.set_status("请在原始预览页涂抹水印，或填写水印文字后点击“预览当前页去水印”。")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    @staticmethod
    def _render_page(page, dpi=200):
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def clear_mask(self):
        if self.current_img is not None:
            self.canvas.set_image(self.current_img)

    def build_model_from_scribble(self):
        mask = self.canvas.mask
        if mask is None or cv2.countNonZero(mask) < 30:
            return None

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

    def detect_mask_by_scribble_model(self, bgr: np.ndarray, model: WatermarkModel):
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        z = np.abs((lab - model.lab_mean) / model.lab_std)
        color_score = z.mean(axis=2)
        color_mask = color_score < float(self.color_k_var.get())

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        ang = (np.degrees(np.arctan2(gy, gx)) + 180) % 180

        diff = np.vectorize(self.angle_diff)(ang, model.angle_deg)
        orient_mask = diff < float(self.angle_tol_var.get())
        mag_mask = mag > np.percentile(mag, 50)

        mask = (color_mask & orient_mask & mag_mask).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=1)
        return mask

    def detect_mask_by_text(self, page, bgr: np.ndarray, text: str):
        h, w = bgr.shape[:2]
        mask = np.zeros((h, w), np.uint8)

        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_dir = line.get("dir", [1.0, 0.0])
                angle = np.degrees(np.arctan2(line_dir[1], line_dir[0]))
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    if text and text in span_text:
                        x0, y0, x1, y1 = span.get("bbox", [0, 0, 0, 0])
                        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                        rw = (x1 - x0) * 1.16
                        rh = (y1 - y0) * 1.9
                        rect = ((cx, cy), (max(3, rw), max(3, rh)), angle)
                        box = cv2.boxPoints(rect).astype(np.int32)
                        cv2.fillPoly(mask, [box], 255)

        if cv2.countNonZero(mask) > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            return cv2.dilate(mask, kernel, iterations=1)

        # 兜底：图像模板匹配（主要覆盖图片型水印或文本层缺失场景）
        template_mask = self._text_template_match(bgr, text)
        return template_mask

    @staticmethod
    def _load_font(size):
        candidates = [
            "msyh.ttc",
            "simhei.ttf",
            "simsun.ttc",
            "NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        for f in candidates:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _text_template_match(self, bgr, text):
        if not text.strip():
            return np.zeros(bgr.shape[:2], np.uint8)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        mask_all = np.zeros_like(gray)

        for font_size in [22, 28, 34]:
            font = self._load_font(font_size)
            canvas = Image.new("L", (max(120, len(text) * font_size * 2), font_size * 3), 0)
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 6), text, fill=255, font=font)
            t = np.array(canvas)
            if t.max() == 0:
                continue
            t = cv2.GaussianBlur(t, (3, 3), 0)
            for ang in range(-60, 61, 15):
                M = cv2.getRotationMatrix2D((t.shape[1] // 2, t.shape[0] // 2), ang, 1.0)
                rot = cv2.warpAffine(t, M, (t.shape[1], t.shape[0]))
                if rot.shape[0] >= gray.shape[0] or rot.shape[1] >= gray.shape[1]:
                    continue
                res = cv2.matchTemplate(gray, rot, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(res > 0.55)
                for y, x in zip(ys, xs):
                    mask_all[y:y + rot.shape[0], x:x + rot.shape[1]] = np.maximum(
                        mask_all[y:y + rot.shape[0], x:x + rot.shape[1]],
                        (rot > 20).astype(np.uint8) * 255,
                    )
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask_all = cv2.morphologyEx(mask_all, cv2.MORPH_OPEN, kernel, iterations=1)
        mask_all = cv2.morphologyEx(mask_all, cv2.MORPH_CLOSE, kernel, iterations=1)
        return cv2.dilate(mask_all, kernel, iterations=1)

    @staticmethod
    def _remove_tiny_components(mask: np.ndarray, min_area: int = 80):
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out = np.zeros_like(mask)
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_area:
                out[labels == i] = 255
        return out

    def build_combined_mask(self, page, bgr):
        mode = self.mode_var.get()
        text = self.watermark_text_var.get().strip()

        use_scribble = mode in ["混合模式", "仅涂抹模式"]
        use_text = mode in ["混合模式", "仅文字模式"] and bool(text)

        combined = np.zeros(bgr.shape[:2], np.uint8)

        if use_scribble:
            model = self.build_model_from_scribble()
            if model is not None:
                combined = cv2.bitwise_or(combined, self.detect_mask_by_scribble_model(bgr, model))

        if use_text:
            text_mask = self.detect_mask_by_text(page, bgr, text)
            combined = cv2.bitwise_or(combined, text_mask)

        if cv2.countNonZero(combined) < 20:
            raise ValueError("没有检测到足够的水印区域。请增加涂抹样本，或检查输入的水印文字。")

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=1)
        combined = self._remove_tiny_components(combined, min_area=90)
        return combined

    @staticmethod
    def restore_text_details(original_bgr, repaired_bgr, mask):
        # 为提升“文字还原感”：在非掩膜区保留原始高频细节，并对修复图做轻微锐化。
        blur = cv2.GaussianBlur(repaired_bgr, (0, 0), 1.2)
        sharp = cv2.addWeighted(repaired_bgr, 1.35, blur, -0.35, 0)
        keep = cv2.bitwise_not(mask)
        restored = cv2.bitwise_and(original_bgr, original_bgr, mask=keep) + cv2.bitwise_and(sharp, sharp, mask=mask)
        return restored

    def clean_page(self, page):
        bgr = self._render_page(page, dpi=220)
        mask = self.build_combined_mask(page, bgr)
        radius = int(self.inpaint_var.get())
        repaired_t = cv2.inpaint(bgr, mask, radius, cv2.INPAINT_TELEA)
        repaired_n = cv2.inpaint(bgr, mask, radius, cv2.INPAINT_NS)
        repaired = cv2.addWeighted(repaired_t, 0.6, repaired_n, 0.4, 0)
        repaired = self.restore_text_details(bgr, repaired, mask)
        return repaired, mask

    def preview_current_page(self):
        if not self.input_pdf or self.current_img is None:
            messagebox.showwarning("提示", "请先加载 PDF 预览")
            return

        try:
            doc = fitz.open(self.input_pdf)
            page = doc[self.preview_page]
            repaired, _ = self.clean_page(page)
            doc.close()
            self.last_preview_processed = repaired
            self.result_canvas.set_image(repaired)
            self.set_status("预览已更新。效果满意后可直接批量导出。")
        except Exception as e:
            messagebox.showerror("预览失败", str(e))

    def process_all(self, output_pdf: Path):
        src = fitz.open(self.input_pdf)
        out = fitz.open()

        self.progress["maximum"] = len(src)
        self.progress["value"] = 0

        for i, page in enumerate(src):
            repaired, _ = self.clean_page(page)
            rgb = cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB)

            h, w = rgb.shape[:2]
            out_page = out.new_page(width=w, height=h)
            png = cv2.imencode(".png", rgb)[1].tobytes()
            out_page.insert_image(fitz.Rect(0, 0, w, h), stream=png)

            self.progress["value"] = i + 1
            self.set_status(f"处理中：第 {i + 1}/{len(src)} 页")

        out.save(output_pdf)
        src.close()
        out.close()

    def run(self):
        if not self.input_pdf or self.current_img is None:
            messagebox.showwarning("提示", "请先加载 PDF")
            return

        if self.mode_var.get() == "仅文字模式" and not self.watermark_text_var.get().strip():
            messagebox.showwarning("提示", "仅文字模式下请填写水印文字")
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
                self.set_status(f"完成：{out_path}")
                messagebox.showinfo("完成", f"已导出：\n{out_path}")
            except Exception as e:
                messagebox.showerror("处理失败", str(e))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
