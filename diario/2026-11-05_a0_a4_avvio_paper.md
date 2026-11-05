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

## 20:00 — Decisioni dell'utente, chiusura manuale, correzione sul ciclo

* Decisioni su S25 (metalli inclusi, margini 100/350, leva 15–35/15–45, nessun tetto di slot, posizioni non per giorni) e sul Brain (valori sì; ragionamento esteso richiesto; freni «allarghiamo»): vedi `STATO.md` voce 05/11 20:00.
* **Chiusura manuale:** classici PR #59 DRAFT (`work/classics-close-position-claude-20261105`); Brain commit `d3bfbdd` su #57 (`manual_close.py`, 49 test, mutazione 39/39). Pulsante nell'app: secondo giro per ChatGPT.
* PR #58 aggiornata: 62 test, mutazione 49/52, nessun tetto di posizioni.
* Correzione: il motore classico gira ogni 30 minuti, non ogni 15.
* Aperti: validità segnale, anti-inseguimento, regola della leva, uscite rapide di S25, numeri dei freni, ragionamento esteso, durata massima del Brain. Nessun deploy.

## 20:15 — Risposte dell'utente applicate; dashboard di ChatGPT

* S25 (#58 `d991a0e`): target 1,5 ATR, 12 ore, leva 15x, validità 1 ora, 0,5 ATR. 62 test, mutazione 49/52.
* Brain (#57 `5954f85`): decisioni ogni ora, ragionamento esteso (`thinking` enabled, sforzo high, 6000 token), 24 ore, tetto 0,75 $; 5678 test ok; mutazione 32/34. Parametri DeepSeek dalla documentazione, da provare dal vivo.
* Dashboard di ChatGPT applicata invariata (PR #60, `a5a0c14`); CI nuova `v3-dashboard-ci` verde (backend, Jest, build).
* Aperti: freni di rischio («20 %»: chiarimento chiesto), analisi dei tempi dei classici, misura costi del ragionamento. Nessun deploy.
* **Attenzione, due consegne della dashboard:** il checkpoint ChatGPT delle 19:50 (`diario/2026-10-30_work-ripresa-doppio-checkpoint.md`) descrive un pacchetto `SuperBot-Dashboard-Unificata-2026-11-05.zip` con 26 test backend, 7 frontend e un file CSS; quello applicato nella PR #60 è il pacchetto `SuperBot-V3-Dashboard-Unificata-consegna-2026-11-05.zip` (16 test backend, 5 Jest, 4 file) consegnato dall'utente. Il pacchetto con 26/7 non è arrivato a Claude: se lo si preferisce, va passato (verrebbe applicato in un commit a parte sullo stesso ramo).

## 20:40 — Pulsante «Chiudi» di ChatGPT applicato (PR #61)

* Consegna invariata (`73199f0`; la sua base v1 coincide con quella applicata); CI `v3-dashboard-ci` a 3 job verde: backend con fastapi (16 + 33 test, 0 saltati, prova con il runner vero), suite V3 3616 ok, Jest 34, build ok.
* Corretti in commit mio (`5b37464`): motivi di chiusura in parole, simbolo al posto dell'identificativo, intestazione non più «solo lettura». Errore mio sul formato del file CI, corretto (`df0459c`).
* Rilievo sul Brain: limite di attesa 30 s per chiamata e giro sequenziale dentro il tick con il ragionamento esteso (battito, chiusura manuale, uscite aspettano il giro). Nulla cambiato; misura nelle prime 24 ore (punto 5f del pacchetto), decisione all'utente. Aggiunto «Collegamento dell'app al Brain» (`3ccef61`).
* Aperti: freni di rischio («20 %»), consegna «26/7» mai arrivata, analisi tempi classici. Nessun deploy.
