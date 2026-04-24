@echo off
chcp 65001 > nul
cd /d %~dp0
echo ========================================
echo   営業リスト作成アプリ 起動中...
echo ========================================
echo.
python -c "import flask, requests, bs4, openpyxl" 2>nul
if errorlevel 1 (
    echo [初回セットアップ] ライブラリをインストールします...
    python -m pip install -q flask requests beautifulsoup4 openpyxl lxml
    echo.
)
echo.
echo ▼ ブラウザで下のURLを開いてください：
echo.
echo     http://localhost:5000
echo.
echo 終了するときは、このウィンドウで Ctrl+C を押してください
echo ========================================
echo.
python app.py
pause
