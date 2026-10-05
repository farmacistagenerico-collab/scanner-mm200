@echo off
REM ============================================================
REM  Avvio della dashboard punteggi live (Windows)
REM  Doppio click su questo file. Si apre il browser su
REM  http://localhost:8000 con il tasto "AGGiorna ora".
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python non trovato. Installalo da https://www.python.org/downloads/
  echo     ^(durante l'installazione spunta "Add Python to PATH"^)
  pause
  exit /b 1
)

python -c "import yfinance, pandas, numpy, scipy" >nul 2>nul
if errorlevel 1 (
  echo Installo le dipendenze ^(una volta sola^)...
  python -m pip install -q yfinance pandas numpy scipy
)

echo.
echo Avvio la dashboard su http://localhost:8000  (premi AGGIORNA ORA nella pagina)
echo Per chiudere: CTRL+C in questa finestra.
echo.
python dashboard.py
pause
