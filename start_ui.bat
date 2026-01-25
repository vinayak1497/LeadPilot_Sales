@echo off
cd /d C:\Users\avani\LeadPilot_DDoxers_2026
echo Starting SalesShortcut UI Client...
echo.
C:\Users\avani\LeadPilot_DDoxers_2026\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'C:/Users/avani/LeadPilot_DDoxers_2026'); from ui_client.main import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"
pause
