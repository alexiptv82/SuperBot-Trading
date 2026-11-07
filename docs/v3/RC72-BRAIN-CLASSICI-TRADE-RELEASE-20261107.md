# RC72 — Brain nella stessa schermata Classici e Trade (7 novembre 2026)

**Mandato utente, basato su screenshot dell'app aggiornata RC71:** usare Brain come **terzo portafoglio nella pagina Classici e nella pagina Trade**, con estetica e funzioni di consultazione uguali a Falco e Toro. Eliminare la scheda BRAIN duplicata della barra inferiore. Mantenere separati contabilità, posizioni, storia e decisioni AI e conservare l'archivio dei Brain precedenti.

## Modifiche applicate

- Menu PAPER inferiore: tab BRAIN rimossa; `/brain` è un collegamento compatibile che porta a `/classic?portfolio=brain`.
- Pagina **Classici**: selettore `Falco | Toro | Brain`; Brain utilizza lo stesso stile di card equity/KPI/stato/operazioni aperte, valore del portafoglio quando verificato, P&L netto realizzato, margine, giorno UTC, capitale iniziale e budget AI se noto. L'equity non verificata resta `—`; non si confonde il book contabile con PnL latente non verificato.
- Pagina **Trade**: selettore dei tre portafogli, stessa lista e filtri (simbolo, LONG/SHORT, aperti/vincenti/perdenti), prezzi e leva quando disponibili. Brain è alimentato esclusivamente dalla nuova run V3; storico paginabile e contatori esatti vincenti/perdenti via API `/api/v3/brain/trades?limit=&offset=`. La schermata non inventa prezzi quando mancano.
- Analisi Brain e osservazione Falco/Toro: sotto il Brain nella pagina Classici tramite pannello espandibile; panoramica V3 dedicata ancora accessibile. Vecchio archivio accessibile da `/brain/archive`; nessun record cancellato.
- Con `V3_CUTOVER_READONLY=1` il frontend disabilita avvio, pausa e chiusure dove possibile; backend rimane fail-closed HTTP 423 per tutte le mutazioni di trading. Non si avviano worker.

## Test e pubblicazione

- [CI React/backend #42375307040](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42375307040): **82/82 test frontend, 83/83 backend, build production PASS**. Eseguiti anche test UI ulteriori per i tre tab e filtri, con successive CI GREEN.
- [Rilascio web controllato #42375609712](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42375609712): **SUCCESS**, nuovo front/back web sul normale HTTPS `https://superbot-trading.duckdns.org/`. Il runtime proviene dal commit `180a05b47caa0af98394a06710e7075f71404c52`; la successiva documentazione/audit non cambia la release già installata. Dry-run preflight, build, backup database app + integrity check, rollback precedente e smoke HTTPS.
- [Audit indipendente postdeploy #42375852716](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42375852716): **PASS** su VPS reale: web running, build esatta, API Brain storica con offset, auth JWT e hash password invariati, HTTPS e login protetti, chiusure singole/totali rifiutate (423), `DESK_MODE=paper`, `TRADING_MODE=paper`, Telegram spento, Brain advisory disabilitato. Vecchio web `superbot-rc72-previous`/vecchia build disponibili per rollback.
- **Posizioni legacy invarianti:** Falco 6, Toro 2 PAPER ancora aperte; contenitori classici stopped/restart=no/paused. Unit exit-only installate ma **DISABLED+INACTIVE**; Brain nuovo run 2.000 PAPER pausato, nessun trading riavviato.
- Il backup locale RC69 dei volumi 38+36 file e il backup SQLite app RC72 sono preservati. Non è stato eseguito alcun backup off-host.

## Gate successivo (richiede collaudo dal telefono)

L'utente deve aprire l'app ufficiale, verificare `Classici → Brain` e `Trade → Brain`, i contatori, lo storico e la sparizione del tab Brain dalla barra. Il dispositivo potrebbe mantenere temporaneamente un vecchio bundle/cache: provare con Chrome sul dominio e aggiornamento della pagina. **Non chiudere i trade** finché non è confermato il collaudo e non si attivano soltanto i worker exit-only PAPER con nuovo checkpoint. Nessun merge né avvio bot eseguito in RC72.
