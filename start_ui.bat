@echo off
cd /d C:\Users\Vinayak Umesh Kundar\Downloads\Build_and_grow\backup2
echo Starting SalesShortcut UI Client...
echo.
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'C:/Users/Vinayak Umesh Kundar/Downloads/Build_and_grow/backup2'); from ui_client.main import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"
pause
