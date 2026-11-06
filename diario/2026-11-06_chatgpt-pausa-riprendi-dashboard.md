# Checkpoint ChatGPT — 6 novembre 2026: dashboard Brain Pausa/Riprendi + banner perdita giornaliera

**Autore:** ChatGPT (GPT-6) · **Stato:** pacchetto locale verificato, NON applicato alla repository del codice, NON MERGERE/DEPLOY.
**Base dashboard:** PR #61, branch `work/v3-dashboard-chiudi-chatgpt-20261105`, SHA `a9044b6759da327b44da04f9e7f51e211d44e03f`.
**Freno giornaliero:** PR #57, commit `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421`.

## Realizzato in copia locale
- Endpoint PAPER `POST /api/v3/brain/pause` e `POST /api/v3/brain/resume`: stessa sessione, `Cache-Control: no-store`, heartbeat fresco e stessa run, `DESK_MODE=paper` obbligatorio; operano solo sul file `pause.flag` del runner, non sul journal.
- UI mobile con conferma inline e riscontro tramite heartbeat; comandi inattivi durante richieste in corso o con heartbeat scaduto; riprendi non supera blocchi giornalieri.
- Dashboard `daily_loss` dal battito scritto dal runner e25c8dd: mostra avviso `warn` e blocco `halt` con soglie lette da config, senza ricalcolare rischio né cambiare 35%/50%.
- Test a livello runner: la pausa lascia attivi monitor stop e comandi di chiusura; nessuna nuova chiamata AI. Il freno giornaliero continua anche con flag rimosso.
- Nessuna modifica a soglie 2% per trade, open risk 5%, capitale, leva, strategie, chiavi, memoria, runner.

## Verifica
- Suite V3 finale su worktree ibrido (PR61 + e25): **4399 passed in 324.41s** (0 falliti).
- Test dashboard nuovo+esistente dalla radice: **82 passed**; stessa suite da `/tmp`: **82 passed**.
- JSX: 4/4 file senza errori sintattici; 6/6 controlli JS puri. **Jest/React non eseguiti** per assenza `node_modules`; eseguire nella CI prima di integrare.
- Archivio di consegna: `SuperBot-V3-Pausa-Riprendi-Banner-2026-11-06.zip`, SHA-256 `1c7e83547b6716b6052bf0f0bf6fa31be494c9b086c2dce1f57399b4babe13b0`; rapporto `RAPPORTO_SuperBot_V3_Pausa_Riprendi_2026-11-06.md`, SHA-256 `470e5974eae39b23c95c9f5064aebab88b22e202650ff5a26e76f93bfe56793c`. Allegati nella chat ChatGPT del progetto, non nel repository.
- Integrazione NON effettuata su GitHub: PR #61 e PR #57 restano su linee separate. Nessun deploy, merge, reboot o accesso VPS.

## Prossimi passi
1. Applicare i 7 file del pacchetto su branch derivato PR61, poi preparare il branch d'integrazione con e25, controllare CI Jest e build.
2. Verificare le autorizzazioni file `pause.flag` condiviso da API+runner, `DESK_MODE=paper` anche nel backend FastAPI, e il feedback heartbeat dopo un click.
3. Eseguire verifica in VPS in modo controllato del timeout DeepSeek 30 s, senza cambiare parametri.
4. Fase C avvio Brain e fase D redeploy Falco/Toro **solo con OK esplicito dell'utente**.

Nessun segreto, saldo reale o dato live è stato inserito.