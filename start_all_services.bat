@echo off
echo ========================================
echo SalesShortcut - Starting All Services
echo ========================================
echo.
echo Starting UI Client on port 8000...
start "UI Client - Port 8000" cmd /k "cd /d C:\Users\avani\LeadPilot_DDoxers_2026 && .\start_ui.bat"
timeout /t 2 /nobreak > nul

echo Starting Lead Finder on port 8081...
start "Lead Finder - Port 8081" cmd /k "cd /d C:\Users\avani\LeadPilot_DDoxers_2026 && .\start_lead_finder.bat"
timeout /t 2 /nobreak > nul

echo.
echo ========================================
echo All services starting!
echo ========================================
echo.
echo Services:
echo   UI Client:        http://localhost:8000
echo   Lead Finder:      http://localhost:8081
echo.
echo Open your browser to: http://localhost:8000
echo.
pause
