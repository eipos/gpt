# PDF 智能去水印工具（中文 + EXE 直接下载）

> 仅用于你有合法处理权的文档。

## 新版重点（效果增强）

- ✅ 新增 **水印文字输入**：可直接输入水印内容做检测（支持中文）。
- ✅ 支持 **倾斜水印** 检测：文字模式会读取文本方向信息并扩展掩膜。
- ✅ 支持 **混合模式**：涂抹样本 + 文字内容联合检测，效果更稳。
- ✅ 新增 **去除后预览页**，可先看效果再批量导出。
- ✅ UI 重构：双栏布局、参数滑杆、模式切换、交互提示更清晰。
- ✅ 修复“加载失败 OpenCV resize 断言”问题：窗口缩放/极端尺寸下也不会因宽高为 0 崩溃。
- ✅ 去除效果进一步优化：双算法修复融合（Telea + NS）+ 小噪声连通域过滤，减少漏检和误修复。

## 小白直接用（不用配环境）

1. 去 GitHub 仓库 `Releases` 下载 `PDFWatermarkCleaner.exe`
2. 双击直接运行（Windows）

如果 Releases 还没有文件：

1. 去仓库 `Actions`
2. 运行或打开 `Build Windows EXE`
3. 下载 Artifacts 里的 `PDFWatermarkCleaner-windows`

## 使用步骤

1. 选择 PDF。
2. 选择模式：
   - 混合模式（推荐）
   - 仅涂抹模式
   - 仅文字模式
3. 可选：输入水印文字（如“机密”“内部资料”）。
4. 在原始页对水印涂抹几笔（混合/涂抹模式建议做）。
5. 点 **预览当前页去水印**，满意后点 **批量去除并导出**。

## 说明

- 文字模式优先利用 PDF 文本层（可识别旋转方向），对“同一文字重复水印”更有效。
- 若文本层缺失，会尝试图像模板匹配作为兜底。
- 导出 PDF 为重建后的图像页，不保留原始可编辑文字层。

## 本地开发（可忽略）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python pdf_watermark_cleaner.py
```
