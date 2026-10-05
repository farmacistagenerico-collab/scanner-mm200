#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch una-tantum: aggiunge il tasto ⟳ AGGIORNA ORA alla vista statica."""
import io

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

VECCHIO = """  <div style="color:#64748b;font-size:12.5px;margin:10px 2px">
    Per aggiornarla in tempo reale: <code>python3 dashboard.py</code> e premi \u27f3 AGGIORNA ORA nella pagina servita.
  </div>"""

NUOVO = """  <div class="box" style="margin-top:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <button id="btn" onclick="aggiorna()"
      style="background:#0a7d3c;color:#fff;border:0;border-radius:10px;padding:12px 18px;
             font-size:15px;font-weight:800;cursor:pointer;letter-spacing:.3px">\u27f3 AGGIORNA ORA</button>
    <span id="statoServer" style="font-size:12.5px;color:#64748b">verifico il collegamento col server\u2026</span>
  </div>
  <div id="msg" style="font-size:12.5px;color:#7c2d12;margin:8px 2px 0"></div>"""

assert VECCHIO in s, "blocco di avviso non trovato"
s = s.replace(VECCHIO, NUOVO)

SCRIPT = """</div>
<script>
const BASI = ["", "http://localhost:8000", "http://127.0.0.1:8000"];
async function prova(metodo, base, percorso) {
  const r = await fetch(base + percorso, {method: metodo});
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
async function serverAttivo() {
  for (const b of BASI) { try { await prova("GET", b, "/api/stato"); return b; } catch (e) {} }
  return null;
}
async function aggiorna() {
  const b = document.getElementById("btn"), msg = document.getElementById("msg");
  b.disabled = true; b.textContent = "\u27f3 aggiornamento\u2026"; b.style.background = "#475569";
  msg.textContent = "";
  for (const base of BASI) {
    try {
      await prova("POST", base, "/api/aggiorna");
      msg.style.color = "#0a7d3c";
      msg.textContent = "Aggiornamento avviato: la vista si ricarica fra ~20 secondi.";
      setTimeout(() => location.reload(), 21000);
      return;
    } catch (e) {}
  }
  msg.style.color = "#b45309";
  msg.innerHTML = "Server non raggiungibile: questa \u00e8 la copia statica. Avvia <code>python3 dashboard.py</code> "
    + "e apri <code>http://localhost:8000</code> per usare il tasto.";
  b.disabled = false; b.textContent = "\u27f3 AGGIORNA ORA"; b.style.background = "#0a7d3c";
}
(async () => {
  const base = await serverAttivo();
  const el = document.getElementById("statoServer");
  el.innerHTML = base !== null
    ? "<b style='color:#0a7d3c'>\u25cf server attivo</b> \u2014 il tasto aggiorna i dati in tempo reale"
    : "<b style='color:#b45309'>\u25cf server non in esecuzione</b> \u2014 avvia <code>python3 dashboard.py</code> per usare il tasto";
})();
</script>
</body></html>\"\"\"
    percorso = os.path.join(OUT_DIR, "dashboard_statico.html")"""

VECCHIA_FINE = """</div></body></html>\"\"\"
    percorso = os.path.join(OUT_DIR, "dashboard_statico.html")"""

assert VECCHIA_FINE in s, "chiusura della vista statica non trovata"
s = s.replace(VECCHIA_FINE, SCRIPT)

io.open(P, "w", encoding="utf-8").write(s)
print("patch applicata")
