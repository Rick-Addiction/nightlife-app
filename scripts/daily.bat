@echo off
REM Roda o pipeline diario HEADLESS. E o que o Windows Task Scheduler chama.
set IG_HEADFUL=0
cd /d D:\MyProjects\nightlife-app
.venv\Scripts\python.exe -m nightlife.daily
