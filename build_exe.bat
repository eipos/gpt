@echo off
setlocal
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name PDFWatermarkCleaner pdf_watermark_cleaner.py
echo.
echo Build complete: dist\PDFWatermarkCleaner.exe
pause
