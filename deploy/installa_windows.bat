@echo off
REM ============================================================
REM  Avvio automatico su Windows (Task Scheduler).
REM  Crea un'attività che avvia la dashboard all'accesso,
REM  con la finestra nascosta.
REM  Eseguire UNA VOLTA con doppio click (non serve come amministratore).
REM ============================================================
setlocal
cd /d "%~dp0.."

for /f "delims=" %%i in ('cd') do set CARTELLA=%%i
for /f "delims=" %%i in ('where python') do set PYEXE=%%i& goto :trovato
echo [!] Python non trovato nel PATH.
pause
exit /b 1
:trovato

echo Cartella progetto: %CARTELLA%
echo Python: %PYEXE%
echo.

schtasks /Create /F /TN "Dashboard Piazza Affari" /SC ONLOGON ^
  /TR "cmd /c cd /d \"%CARTELLA%\" && \"%PYEXE%\" dashboard.py --no-browser --porta 8000 >> \"%CARTELLA%\output\dashboard.log\" 2>&1"

if errorlevel 1 (
  echo.
  echo [!] Creazione non riuscita. In alternativa:
  echo     - premi WIN+R, digita  shell:startup  e incolla lì un collegamento a avvia_dashboard.bat
  pause
  exit /b 1
)

schtasks /Run /TN "Dashboard Piazza Affari"
echo.
echo Fatto: la dashboard parte all'accesso e ora è stata avviata.
echo Apri il browser su  http://localhost:8000
echo Per rimuoverla:  schtasks /Delete /TN "Dashboard Piazza Affari" /F
pause
