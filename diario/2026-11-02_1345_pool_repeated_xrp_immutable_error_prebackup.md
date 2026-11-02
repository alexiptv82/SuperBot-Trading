# 2026-11-02 13:45 Europe/Rome — Pool continua a fallire su XRP Donchian; preflight backup richiesto

## Evidenza dell'operatore (Termius 13:45)
Comando eseguito:
```
docker logs --since 2h --tail 120 superbot-pool 2>&1 | grep -E 'ERRORE|giro fatto|pool avviato' | tail -20
```
Output: errori ripetuti nei giri recenti, tutti con la stessa forma:
```
ERRORE giro fallito: ImmutableTradeError: trade chiuso modificato (exit_t): ('CTL_S2_top10', 1, 'paper', 'XRP/USDT:USDT', 1792461600000)
```
Non si vede alcun `giro fatto` tra le righe selezionate. Dalle verifiche precedenti: `POOL=running HEALTH=unhealthy`; ultimo `last_ok_ms=2026-10-22T02:45:20Z`; un record OPEN `R_S2_top10 / ADA/USDT:USDT / side=-1 / 2026-11-02T07:00:00Z`. Spiegazione coerente con `runner.run_once` (upsert trade a commit incrementali prima dell'errore nel controllo XRP). 

## Stato test e rilascio
- Due audit separati su VPS in sola lettura: 273/273 chiusi S2 compatibili; 18/18 chiusi S1 compatibili; zero differenze sulle 291 righe chiuse censite. Nessuna garanzia che siano uno snapshot simultaneo; nuovo preflight prima del deploy.
- PR #28 fix Donchian prossimo open entro max_hold: 69/69 CI già attestati, non ancora deployata/mergiata.
- Nessuna eliminazione o modifica del Journal, nessun reset, nessun ordine, niente restart/deploy, Falco e Toro invariati, Brain/Shadow pause invariati.
- Prossimo passo di sola lettura: verificare mount host effettivo del solo container `superbot-pool`, spazio libero, dimensione dati e policy restart. In seguito pianificare backup consistente dei file DB con sidecar WAL + cache candele, preferendo fermo mirato e autorizzato del solo Pool, con restore testato su copia. Non fermare i classici. 
AI: ChatGPT.
