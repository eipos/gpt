# PDF 水印清理工具（小白可用版）

> 仅用于你有合法处理权的文档（例如你自己的资料、公司授权文档）。

## 你最关心的：不用配环境，直接下载就能用

我已经把项目改成可以在 GitHub 自动打包 `exe`。

你只需要：

1. 打开仓库页面 → `Releases`
2. 下载 `PDFWatermarkCleaner.exe`
3. 双击运行（Windows）

如果 `Releases` 里还没有文件：

1. 打开仓库 `Actions` 页
2. 找到 `Build Windows EXE`
3. 点进去下载 Artifacts 里的 `PDFWatermarkCleaner-windows`
4. 解压后得到 `PDFWatermarkCleaner.exe`

---

## 软件怎么用（3步）

1. 点 **选择PDF**，打开你的文件。
2. 在预览页对水印位置 **随便涂几笔**（多涂一点更准）。
3. 点 **批量去除并导出**，保存新 PDF。

---

## 功能说明

- 支持中文界面。
- 支持斜着的水印（利用角度特征）。
- 支持和正文颜色接近的水印（利用颜色+方向+强度综合判断）。
- 支持图片里烧录的水印（按图像方式修复）。

> 注意：导出的 PDF 是“修复后的图片页”，不保留原始可编辑文字层。

---

## 我帮你做好的 GitHub 自动打包

仓库已包含：

- `.github/workflows/build-windows-exe.yml`（GitHub Actions 自动构建 Windows EXE）
- `build_exe.bat`（你也可以在本地 Windows 一键打包）

打标签发布时（例如 `v1.0.0`），会自动把 `PDFWatermarkCleaner.exe` 附到 Release。

---

## 本地开发（可忽略）

只有开发者才需要看这一段：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python pdf_watermark_cleaner.py
```
