# PDF 水印清理工具（Windows 可打包 EXE）

> 仅用于你有合法处理权的文档（例如公司内部模板、你本人生成的 PDF）。

这是一个支持中文界面的桌面工具：

- 先打开 PDF，并在预览页对水印“涂抹几笔”做示例。
- 程序会自动学习该水印的颜色分布与倾斜角度特征。
- 对整份 PDF 批量检测并修复（包含烧录进图片中的水印）。
- 输出新的 PDF。
- 支持打包成免安装单文件 `exe`，可在 Windows 直接双击运行。

## 核心思路

1. 从用户涂抹区域提取水印像素的 `LAB` 颜色统计（均值/方差）。
2. 用 `PCA` 估计水印主方向（多数斜水印有效）。
3. 在每页中结合：
   - 颜色相似度
   - 梯度方向接近程度（利用斜水印特性）
   - 梯度强度阈值
   生成候选水印掩膜。
4. 用 OpenCV `inpaint` 修复掩膜区域。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
python pdf_watermark_cleaner.py
```

## 打包为 Windows 单文件 EXE

在 Windows 下执行：

```bat
build_exe.bat
```

或者手动：

```bat
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name PDFWatermarkCleaner pdf_watermark_cleaner.py
```

产物路径：

- `dist\PDFWatermarkCleaner.exe`

## 参数说明

- `颜色阈值k`：越大越宽松，能匹配更接近颜色的水印。
- `角度容差`：越大越允许角度偏差。
- `修复半径`：inpaint 半径，越大修复越强但可能损失细节。

## 注意事项

- 这是图像级修复方案，输出 PDF 为重建后的图像页，不保留原始可编辑文字层。
- 若水印与正文颜色/纹理过于接近，请先在代表性区域多涂几笔，并微调参数。
