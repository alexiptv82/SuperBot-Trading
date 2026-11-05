# 05/11 — Fase A (A0–A4): il Brain PAPER assemblato e provato offline

Autore: Claude Sonnet 5.5 (coordinatore). Nessun deploy, nessun avvio. Dettagli in `STATO.md` (voce 05/11 18:30) e nel Project: `claude/avanzamento-fase-a-brain-paper-2026-11-05.md`, `claude/pacchetto-rilascio-a4-brain-paper-2026-11-05.md`.

* PR #56 (A0) e #57 (A1–A4, ramo `work/v3-a1-exits-claude-20261105`, HEAD `f8300d1`), entrambe DRAFT.
* Moduli: `backend/v3/runner/` (`exits`, `feed`, `monitor`, `contracts`, `cycle`, `runner`, `config`, `metering`, `wiring`).
* Verifica: suite V3+Brain 5577 PASS (3 `fastapi` preesistenti); mutazione 30/30, 33/33, 30/30, 26/26, 26/26, 28/28; una prova end-to-end.
* Mandato: senza `mandate.json` approvato dall'utente il Brain non apre e non spende.
* Da confermare dall'utente: universo (8 simboli), tetto DeepSeek 0,60 $/giorno, costi, uscite, limiti di rischio, firma del mandato, maintenance.
* Da verificare alla prima chiamata reale (VPS, sola lettura): campi dei contratti Bitget, granularità `1H/4H`, modello DeepSeek `deepseek-flash` e `thinking`, campo `usage`, prezzi.
* Aperto: B dashboard (ChatGPT), C avvio e D Falco/Toro long: solo con OK esplicito.

## 19:00 — D: long S25 per Falco e Toro (offline, spenta di default)

* PR #58 DRAFT su `rule-pool` (ramo `work/classics-long-s25-claude-20261105`, commit `b8e4933`): `backend/desk/long_s25.py` + 17 righe in `cli.py` dietro `DESK_LONG_S25=1`. Nessun deploy.
* 57 test nuovi, mutazione 46/49 (3 equivalenti); test classici esistenti: stesso elenco di 63 fallimenti prima e dopo (ereditati dal codice del 13/10).
* Da confermare: tetto 3/1, oro e argento esclusi, finestra 1 ora, tolleranza 0,5 ATR. Deploy solo con OK esplicito.

