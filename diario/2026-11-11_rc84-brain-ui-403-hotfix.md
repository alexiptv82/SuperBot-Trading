# 11 novembre 2026 — INCIDENZA HTTP 403 dopo Brain UI: diagnosticata e riparata

**Segnalazione utente:** subito dopo il rilascio pubblico della correzione Brain Performance/Impostazioni, aprendo SuperBot appariva **403 Forbidden**.

**Causa tecnica effettiva confermata sulla VPS Singapore:** lo script di rilascio `deploy/scripts/rc84-brain-ui-public-paper-readonly-release.py` creava il frontend React con `BUILD.mkdir(mode=0o700)`. Dopo il rename a `/opt/superbot-web/build`, il webserver Nginx (www-data) non aveva il diritto di attraversare la directory. Il precedente rilascio GitHub Actions mostrava SUCCESS perché verificava il backend su localhost :8002 e i blocchi API, ma NON testava la leggibilità dei file statici sotto l'utente Nginx. **La build pubblica risultava quindi 403 nonostante backend sano.**

## Hotfix realmente eseguito

- **Workflow incidente [42992486460](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42992486460)**, `completed/success`, job 130428468477, 11/11/2026 ~09:07 UTC.
- Eseguito script dedicato e pin esatto `deploy/scripts/rc84-brain-ui-fix-nginx-403-once.sh`, ramo `work/rc84-brain-performance-settings-20261111`, SHA commit `0e7f79247c8663bb47f70e0e62d395cfbffca1fe`. Script con `--check` read-only seguito da `--repair` limitato a file frontend pubblici.
- L'audit ha verificato **SHA pubblicato** `d0c832620e9b237ce97305029bab5150d3f77489`, marker del rilascio, esistenza del rollback RC84, tre `pause.flag` e mandato Brain `approved=false`.
- Log diagnostici diretti: `RC84_403_ASSET_DIR_MODE_BEFORE=700`, `RC84_403_WWWDATA_INDEX_READABLE_BEFORE=False`, `RC84_403_DIAGNOSIS=PUBLIC_ASSETS_INACCESSIBLE`.
- Correzione **solo permessi frontend pubblici**: directory 0755, asset 0644, senza symlink; nessun contenitore riavviato.
- Log conferma post-correzione: `RC84_403_ASSET_DIR_MODE_AFTER=755`, `RC84_403_WWWDATA_INDEX_READABLE_AFTER=True`, `RC84_403_NGINX_STATIC_FILE_PERMISSIONS_REPAIRED=True`, `RC84_403_NO_SERVICE_RESTART_OR_TRADING_CHANGES=True`.
- **Limite di verifica:** è stata dimostrata la leggibilità del frontend con l'utente Nginx `www-data` sul VPS; l'accessibilità dall'app/browser dell'utente (via proxy, DNS, cache) resta da riconfermare dopo un refresh. Non dichiarare una prova end-to-end esterna mai fatta.

## Prevenzione di recidiva

- Il sorgente del rilascio su `work/rc84-brain-performance-settings-20261111` è stato corretto in commit `790dcb01431fd8469f50d113fe56d9e67a83e902`: crea asset con 0755, esplicitamente imposta cartelle 0755 e file statici 0644, verifica lettura `index.html` come www-data prima e dopo il passaggio a directory pubblica. **Questa modifica al codice non è stata ri-distribuita sul sito**: l'hotfix sul server era già eseguito; questa patch evita il ripetersi su futuri deploy.
- Non riattivare il precedente workflow di pubblicazione Brain UI senza includere il fix; il rilascio approvato e verificato è già online.

**Trading:** bot Falco/Toro/Brain sempre PAPER e PAUSED; mandato Brain non approvato, nessuna apertura trade, nessun segreto toccato. Vecchia RC84 e vecchia RC73 rimangono conservate come rollback. Le AI nuove non sono ancora collegate. Prossima conferma: l'utente riapre app, fa refresh e verifica la pagina e le schede Brain.
