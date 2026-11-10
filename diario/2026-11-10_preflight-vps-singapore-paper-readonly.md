# 10 novembre 2026 — Preflight VPS Singapore, sola lettura, orientato alla ripartenza PAPER

**Esito: diagnostica VPS riuscita (lettura diretta dei log GitHub Actions); ripartenza NON autorizzata e NON eseguita.**

- Run verificato: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42891405554
- Data del run: 2026-11-10T20:03:23Z (21:03 Europe/Rome). Job `audit` SUCCESS, log letto direttamente con GitHub connector.
- Workflow: `.github/workflows/v3-vps-inventory.yml`, attivato una sola volta tramite `deploy/v3-inventory.trigger` su `main` commit `bd39f407bf4d58a209f08da568d754d510ee9622`.
- Prima del run, modificata SOLO la diagnostica `deploy/scripts/v3-vps-inventory.sh` (`main` commit `a24353b96dab096f1ee6acc05dbddc3ab3fb7627`) per aprire SQLite con `mode=ro&immutable=1`, evitando creazione di file sidecar; lo stato letto può essere non aggiornato se esiste WAL non checkpointato. Nessun runtime trading modificato.
- NESSUN deploy, merge, stop, restart, API a pagamento, ordine o cambio dati fatto dal workflow. Analisi di un solo run GitHub Actions.

## Osservazioni reali (solo stati e conteggi)
- Classici: `superbot-desk-hawk` e `superbot-desk-bull` **exited** da circa 8 giorni, ciascuno con `DESK_MODE=paper`, politica restart=`no`, `pause.flag` presente, `open_count=0`. Run numeri: Hawk 8, Bull 7.
- Entrambi: file `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md` presenti; stato leggibile. La presenza non sostituisce verifica d'integrità/ripristino.
- `superbot-brain-free` vecchio: container `exited`, `DESK_MODE=paper`, `pause.flag` presente, stato SQLite letto in snapshot con `mode=paper`, `paused=True`, `open_count=0` (snapshot potrebbe essere non aggiornato se WAL).
- `superbot` dashboard/API: container **running**, immagine RC73, `DESK_MODE=paper`; `superbot-v3-rc70-preview` ancora running. La dashboard **non** è garanzia che la logica delle tre strategie sia in esecuzione.
- Servizi `superbot-v3-falco-exit.service`, `superbot-v3-toro-exit.service` **active/running**: solo chiusure manuali, non operatività strategica. Nessun servizio Brain V3 attivo elencato dal filtro: non prova che non esistano worker con nomi diversi.
- `superbot-pool` e precedenti sidecar/Brain Free **exited**. `superbot-extbackup.service` **inactive/dead** (non prova ultimo backup riuscito).
- Il container `superbot` monta una cartella di run Brain V3 preparata; **non** è stato letto né certificato il suo journal, mandato, stato exit-worker o readiness runtime.
- Disco: 38 GB totali, 7,9 GB usati, **30 GB liberi**, 21% occupazione. Cartelle: classici 50 MB, Brain Free 452 MB, Brain Adaptive 13 MB, Pool 17 MB.

## Interpretazione e limiti
- **Verificato:** classici fermi senza posizioni aperte, storici presenti; dashboard PAPER online; servizi exit-only classici attivi.
- **NON verificato:** nessuna chiamata possibile a ordini LIVE Bitget (serve verifica effettiva di isolamento esecutore/credenziali, senza leggere segreti); configurazioni di rischio attuali; stato/mandato/journal del Brain V3; stop loop reale su VPS; snapshot locale con restore sullo stato attuale; integrità e usabilità del backup remoto age V2.
- PR #80 RC84 CI-green resta **DRAFT e non rilasciata**. Backend in VPS osservato RC73, non equivale alla PR RC84.
- Non mischiare sviluppo sicurezza del backup con ritorno a trading PAPER: per il riavvio serve SOLO il gate minimo (isolamento PAPER, snapshot locale recuperabile, assenza doppio owner delle chiusure, configurazioni e exit-worker coerenti) poi approvazione utente separata.
- L'autorizzazione ricevuta riguarda **preflight read-only**, NON autorizza avvio di bot, merge, deploy, reset, rotazioni credenziali, ordini o ripristini.
- Capitali di ripartenza desiderati, non attivati: Falco 1.000 USDT PAPER, Toro 1.000 USDT PAPER, Brain 2.000 USDT PAPER. Storici e memoria da preservare.
- Il punto successivo deve essere un gate mirato al Brain V3 e al percorso PAPER-only prima di una proposta concreta di rilascio; NO richieste di ulteriori test massivi non necessari.
