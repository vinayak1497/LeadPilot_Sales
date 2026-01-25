@echo off
cd /d C:\Users\Vinayak Umesh Kundar\Downloads\Build_and_grow\backup2
echo Starting Lead Finder service on port 8081...
echo.
set GOOGLE_MAPS_API_KEY=AIzaSyCuewETlqGHXfCLwKsrocgmhPa8Me1DrYI
set GOOGLE_API_KEY=AIzaSyCX2dqpeVgNyXALDLH4ri0FQSrrwLvomC8
set GOOGLE_CLOUD_PROJECT=build-with-ai-aug
set DATASET_ID=lead_finder_data
set TABLE_ID=business_leads
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'C:/Users/Vinayak Umesh Kundar/Downloads/Build_and_grow/backup2'); import os; os.chdir('C:/Users/Vinayak Umesh Kundar/Downloads/Build_and_grow/backup2/lead_finder'); import click; from __main__ import main; main(['--port', '8081'])"
pause
