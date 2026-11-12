# 12 novembre 2026 05:06 Roma — Confronto REALMENTE completato, SOL e BTC pronti con candele allineate

## Evidenza diretta utente (screenshot Termius), orario UTC 04:05:29.911

Comando eseguito sulla VPS Singapore con `curl` pinned + controllo Git hash `a51ee5ba737edb3e8f2c637577994eb369f1f04f` e `python3 -I rc84-compare.py`. Script `deploy/scripts/rc84-bitget-live-vs-history-aligned-readonly.py`, commit main pinned `55c465bf458ecd0e8aa3a75fe64e7bbfd01ec039`. Uscita finale `RC84_COMPARE_ONLY_PUBLIC_READS=PASS`, `RC84_COMPARE_DONE=TRUE`.

| Fonte | Mercato | Barre | Minimo | Consecutive sino all'ultima chiusa | Age | Ready |
|---|---|---:|---:|---:|---:|---|
| /api/v2/mix/market/history-candles | SOL 15m | 3000 | 2893 | 3000 | 0 | TRUE |
| /api/v2/mix/market/candles | SOL 15m | 2975 | 2893 | 2975 | 0 | TRUE |
| history-candles | SOL 1H | 760 | 733 | 760 | 0 | TRUE |
| candles | SOL 1H | 759 | 733 | 759 | 0 | TRUE |
| history-candles | BTC 15m | 3000 | 2893 | 3000 | 0 | TRUE |
| candles | BTC 15m | 2975 | 2893 | 2975 | 0 | TRUE |

`errors:[{code:NO_NEW_CANDLES,http:200,page:16}]` per 15m e pagina 5 per SOL 1H compare **solo dopo** aver ottenuto già la storia richiesta: fine paginazione, NON mancanza del feed. Lo storico reale è sufficiente e aggiornato, senza ridurre le soglie o inventare barre. La differenza dal primo script (SOL 15m solo 1200, SOL 1H HTTPError, BTC stale di 1 bar) dimostra l'errore dei confini temporali non allineati, non una carenza strutturale di dati disponibili su Bitget.

Documentazione Bitget v2: `startTime` e `endTime` vanno arrotondati alla griglia timeframe, endpoint storia massimo 200 per richiesta (https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market). Lo stesso screenshot precedente conferma BTC e ETH metadata `maxLever=150`, superiore alla vecchia soglia parser <=125.

## Situazione bot e interventi

In screenshot utente delle 05:05 sono visibili:
```sh
for d in classic-hawk-paper20261111 classic-bull-paper20261111 brain-v3-paper20261111; do
  touch "/opt/superbot-v3-paper-runs/$d/pause.flag"
done
```
Il terminale è tornato al prompt, quindi l'utente **ha effettivamente eseguito** il comando di pausa delle nuove entrate PAPER. Non equivale a chiusura posizioni o stop dei servizi di uscita, né conferma che flag permangano indefinitamente: verify VPS al rilascio.

La PR [Draft #85](https://github.com/alexiptv82/SuperBot-Trading/pull/85), ramo `work/rc84-fix-classic-divergence-brain-market-20261111`, HEAD `83b970c797b1765be0307c99ded1b8d368e379b1` **NON distribuita**, ora contiene:
- Correzione `backend/v3/lab_tools/fetch_candles.py` **dell'intera paginazione**: ogni `startTime` e `endTime` allineati su timeframe, max 200 candele per pagina e un bar di sovrapposizione, `_row` mantiene controllo qualità e scarta forming; nessun dato interpolato. Il precedente tentativo di recuperare SOLO ultima candela era incompleto, sostituito dalla correzione di tutte le pagine.
- Test nuovi `backend/tests/test_v3_lab_fetch_candles.py`: simulazione 3000 bar in più pagine, bound inclusivo o esclusivo, barra realmente non disponibile; simulazione tecnica locale Python della logica ha superato quattro combinazioni di bound inclusivi/esclusivi (3000 o 2999 su 3000 con start esclusivo) senza buchi, e no fake recent candle. **Non è l'esecuzione di pytest del repo!**
- Parser `contracts.py` valori Bitget maxLever <=200 (BTC ETH 150): il limite operativo Brain max 50x resta immutato.
- New entries S25 per entrambi DISABLED di default, gestione 12h S25 pregresse conservata. Originali LONG/SHORT ancora previsti; fallback condiviso va riconsiderato per vera diversificazione.
- Heartbeat Brain persistente `last_cycle` con errori e conteggi per riconoscere zero decisioni e dati invalidi.

**Stato serio:** GitHub Actions [pausa #43095712678](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43095712678) e [probe #43096514061](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43096514061) ancora QUEUED al check; **nessun test CI completo e nessun deploy della patch**. PR Draft soltanto. L'utente ha autorizzato riparazioni e eventuale RESET PAPER dopo backup verificato; non attivare LIVE, non deployare senza test/rollback, Fable OFF.

## Prossimi passi

1. Eseguire suite offline REALI mirate di `test_v3_lab_fetch_candles.py`, `test_v3_runner_feed_monitor.py`, `test_v3_runner_contracts.py`, `test_v3_runner_runner.py`, `test_long_s25.py`, più verifiche owner exit e parsing Claude JSON. GitHub Actions attualmente bloccate/queued: evitare di generare run superflue e cercare esecuzione locale di codice pinned/offline.
2. Backup storico e verifica stato attuale pause/servizi exit, eventualmente reset PAPER autorizzato senza toccare LIVE e con audit di integrità.
3. Deploy progressivo solo dopo pass, osservare almeno 1 giro Brain con chiamata DeepSeek valida oppure NO_TRADE **motivato**, e comportamento Falco/Toro effettivamente differenziato.
4. Verificare Telegram e logging, non forzare ingressi o ridurre i vincoli di rischio.

**La disponibilità pubblica del feed è verificata. Il funzionamento effettivo del nuovo Brain non è ancora verificato.**
