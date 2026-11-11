# 11 novembre 2026 — QUATTRO NUOVI servizi V3 PAPER su Singapore AVVIATI, ma tutti PAUSED

**Risultato reale e verificato:** [GitHub Actions run 42983236458](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42983236458), stato completed / conclusion success, job 130398307737 success, alle 07:57:11–07:57:47 UTC del 2026-11-11 (circa 08:57 Europe/Rome). Letti i log reali del job.

**Ambito autorizzato:** avvio controllato dei quattro NUOVI servizi delle tre run PAPER **con pause presenti**. Questa operazione NON equivale ad autorizzazione per rimuovere `pause.flag`, approvare il mandato, fare trade, spostare la web pubblica o fare merge.

## Evidenze da output sulla VPS
- `RC84_PAPER_IDENTITIES_AND_UNAPPROVED_MANDATE=PASS`.
- `RC84_WORKERS_DRY_RUN=PASS`; quattro unità inizialmente non installate e pause presenti.
- `RC84_NEW_FALCO_TORO_BRAIN_PAUSED_HEARTBEATS=PASS`.
- `RC84_BRAIN_EXIT_SINGLE_OWNER_HEALTHY=PASS`.
- `RC84_FOUR_NEW_PAPER_SERVICES_ACTIVE_PAUSED=True`.
- `RC84_FOUR_NEW_PAPER_SERVICES_NOT_ENABLED=True` — unità non abilitate all'avvio automatico del server; possono comunque essere riavviate da systemd in caso di errore mentre il server è acceso.
- `RC84_BRAIN_MANDATE_STILL_UNAPPROVED=True`.
- `RC84_NO_STRATEGY_CYCLES_OR_PAPER_TRADES=True`.
- `RC84_NO_LEGACY_OR_PUBLIC_WEB_CHANGES=True`.

## Servizi installati e attivi SOLO in nuove directory
- `superbot-v3-paper-falco.service`, conto PAPER 1.000 USDT in `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111`.
- `superbot-v3-paper-toro.service`, conto PAPER 1.000 USDT in `/opt/superbot-v3-paper-runs/classic-bull-paper20261111`.
- `superbot-v3-paper-brain-exit.service`: proprietario unico chiusure/stop Brain V3 su `/opt/superbot-v3-paper-runs/brain-v3-paper20261111`, heartbeat sano e lease su quella directory.
- `superbot-v3-paper-brain-runner.service`: motore di decisioni Brain in modalità split con sidecar uscite indipendente; **nessun ciclo decisionale** per pausa + mandato non approvato.

Tutti i comandi di avvio delle unità impongono `DESK_MODE=paper` anche se l'ambiente AI suggerisse altro. Si è verificato che le nuove run hanno pause e metadati corretti, classici 1.000 USDT con 0 posizioni, Brain 2.000 USDT e leva 20–50x nel profilo run, journal coerente, mandato `approved=false`. Preflight legato alla checkout RC84 pinned `0e29a73a36f668643da4088178bacb8616a45ac0`.

Script `deploy/scripts/v3-rc84-start-new-paper-workers-paused.sh` e quattro template service versionati su `work/paper-restart-prep-20261110` commit pinned `691759b7ff9876b7dfb39811c186962873262a2a`. Workflow dedicato su `main` `.github/workflows/v3-paper-workers-paused-once.yml` trigger `deploy/v3-paper-workers-paused.trigger` commit `42f0a9a61b4460803f64d9fdd4a9a545184ba8b1`. Un solo workflow per questa fase, con fallback che in caso di fallimento avrebbe fermato e rimosso SOLO le quattro unità nuove.

## Stato rimasto invariato
- Dashboard **pubblica** ancora RC73 su `superbot` e le unità precedenti di chiusura Falco/Toro restano attive ma su dati legacy separati. La preview RC84 è loopback-only (backend :18004, Nginx :18081) e READ-ONLY, verificata nel run 42971823320.
- PR #80 RC84 resta Draft NON mergiata. Nessun comando Bitget live, reset, creazione nuove posizioni PAPER, modifica ai vecchi storici.
- Nessun AI-key è stato stampato o migrato in questa fase; i file ambiente delle nuove unità sono facoltativi esclusivamente per l'avvio in pausa. Prima di togliere una pausa bisogna controllare che Falco/Toro abbiano Claude disponibile e Brain abbia il provider DeepSeek, evitando un fallback indesiderato.
- Backup locale RC77 dei classici era già verificato come coincidente con lo storico al 10/11; backup remoto age V2 resta un filone separato.

## Prossimi passi brevi
1. Preparare il **collegamento controllato** della dashboard RC84 pubblica alle nuove run, garantendo login, mount corretti, nessuna regressione della chiusura manuale Falco/Toro, e test Brain Chiudi ora solo con sidecar sano. Questo **richiede approvazione separata al deploy web produttivo**.
2. Verificare presenza/uso delle credenziali AI **senza mostrare valori** e contatore costo, insieme a PAPER nel runtime. I servizi sono attivi ma ancora in pausa: la verifica non è autorizzazione a chiamare modelli.
3. Solo dopo consenso distinto dell'utente: approvare mandato Brain con policy hash corretta, rimuovere pause sulle tre run e osservare i primi trade PAPER (NO_TRADE lecito; startup cooldown 15–30 minuti). Nessun passaggio a LIVE, mai.
