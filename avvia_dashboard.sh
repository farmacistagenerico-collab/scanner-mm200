#!/usr/bin/env bash
# ============================================================
#  Avvio della dashboard punteggi live (macOS / Linux)
#  Uso:  ./avvia_dashboard.sh   oppure   bash avvia_dashboard.sh
#  Si apre il browser su http://localhost:8000 con il tasto
#  "AGGIORNA ORA".
# ============================================================
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[!] Python 3 non trovato: installalo (Python 3.10+) e riprova."
  exit 1
fi

if ! python3 -c "import yfinance, pandas, numpy, scipy" >/dev/null 2>&1; then
  echo "Installo le dipendenze (una volta sola)..."
  python3 -m pip install -q yfinance pandas numpy scipy
fi

echo
echo "Avvio la dashboard su http://localhost:8000  (premi AGGIORNA ORA nella pagina)"
echo "Per chiudere: CTRL+C"
echo
exec python3 dashboard.py
