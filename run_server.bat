@echo off
echo Göktürkçe Doğrulama Aracı Sunucusu Başlatılıyor...
cd /d "%~dp0pipeline\product"
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
