"""Supporto per le prove RC82/RC84 su stop, DCA, claim e chiusure, che NON riguardano il motore dei segnali.

Dalla fase 2 il ciclo apre solo con una tendenza 4h verificabile (signals.read_symbol). Queste prove alimentano il ciclo
con una o due candele 15m (non bastano per una lettura): ``known_4h_trend`` fornisce la lettura minima che il ciclo
vedrebbe con dati completi (tendenza 4h nota, punteggi a zero, nessun lato), cosi' la prova arriva a cio' che deve
dimostrare (stop, DCA, claim, chiusure in pausa) senza cambiare alcun comportamento operativo.
"""
from desk.signals import Reading


def known_4h_trend(monkeypatch, cli, state="UP"):
    def read(sym, arr, now_ms=None, **_kw):
        price = float(arr[-1][4]) if len(arr) else 0.0
        return Reading(symbol=sym, price=price, side=0, facts={
            "trend4h_state": state, "trend4h_why": "", "ema50_200_4h": "su" if state == "UP" else "giu",
            "trend1d_state": "UNKNOWN", "trend_state": "CONTINUATION_" + state, "daily_trend": ""})
    monkeypatch.setattr(cli, "read_symbol", read)


def with_history(rows, n=90, bar_ms=900_000):
    """Antepone ``n`` candele 15m piatte, contigue e PIU' VECCHIE della prima riga, al prezzo d'apertura della prima riga.
    Servono solo a superare la soglia di 80 candele con cui il ciclo calcola una lettura: sono anteriori all'apertura delle
    posizioni delle prove (on_bar le ignora), non cambiano l'ultima riga (prezzo operativo, stop_feed) ne' gli stop."""
    if not rows:
        return rows
    first = rows[0]
    t0, px = int(first[0]), float(first[1])
    pad = [[t0 - (n - i) * bar_ms, px, px, px, px, 1.0] for i in range(n)]
    return pad + [list(r) for r in rows]
