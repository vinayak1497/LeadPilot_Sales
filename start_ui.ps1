# SalesShortcut - Start UI Client
$projectPath = 'C:\Users\avani\LeadPilot_DDoxers_2026'
$pythonExe = "$projectPath\.venv\Scripts\python.exe"

Write-Host 'Starting UI Client on port 8000...' -ForegroundColor Green

& $pythonExe -c "import sys; sys.path.insert(0, '$projectPath'); from ui_client.main import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"