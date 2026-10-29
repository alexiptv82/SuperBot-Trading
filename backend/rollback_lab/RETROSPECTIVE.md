# Prova offline retrospettiva — rollback selettivo 12 ottobre

Data analisi: 29 ottobre 2026. **Solo dati PAPER archiviati** in `diario/analisi-run-2026-10-27/run_metrics.json`, con metodo e controlli descritti nell'audit `REPORT.md`. NON è replay controfattuale su candele 15m, non è live trading.

## Risultati riproducibili dagli archivi

| Portafoglio/run | Posizioni | Lordo USD | Fee USD | Netto USD | Win rate posizioni | Profit factor netto | Posizioni/giorno |
|---|---:|---:|---:|---:|---:|---:|---:|
| hawk #2 | 76 | 1293.74 | 203.03 | 1090.61 | 60.53% | 2.12 | 21.72 |
| hawk #3 | 38 | -179.20 | 105.39 | -284.87 | 26.32% | 0.54 | 10.51 |
| hawk #5 | 112 | 226.28 | 276.98 | -50.81 | 37.50% | 0.97 | 24.72 |
| bull #1 | 17 | 850.91 | 80.17 | 770.75 | 70.59% | 5.21 | 4.86 |
| bull #2 | 15 | -77.38 | 67.08 | -144.68 | 26.67% | 0.52 | 4.15 |
| bull #4 | 77 | 116.96 | 330.25 | -214.02 | 36.36% | 0.89 | 13.69 |

**Controlli di causalità:** le prime run negative Hawk #3 e Bull #2 erano già in perdita al LORDO, prima di sottrarre le fee. Il primo peggioramento avviene prima dei grandi interventi del 21–26 ottobre, quando soglia altcoin=70 e SL1.2xATR erano ancora gli stessi dei test positivi. Non si può quindi affermare che un mero ripristino della soglia o del coefficiente ATR sia una soluzione.

## Puntatori immutabili

- Deploy storico 12 ottobre: `a0afc63fccc16b0081bc6fdd49768506b9242f89`.
- Fine delle prime run positive: `5818aee1e587f103d222510e761b30e02776ff15` (NON unico codice eseguito in quella finestra).
- Versione runtime moderna documentata: `dc16e0169932c3885908625ce5be321a33b09a0f`.

## Riscontro sulle incompatibilità

Nel codice 12 ottobre, `backend/desk/cli.py` impone margini/minimi sulle proposte insufficienti e `load_state` può restituire un dizionario vuoto se il JSON non è valido. Il deploy storico non ha controlli e percorsi della VPS Singapore odierna, né i journal/cursor/outbox e i dati aggiornati. NON avviare vecchio codice sull'attuale directory dei dati.

## Verdetto fase 1

Il ripristino del comportamento 12 ottobre resta una **ipotesi da testare** e NON un rollback pronto. I dati confermano il guadagno del periodo iniziale ma **non** che il codice 12 ottobre avrebbe evitato le perdite successive. Per decidere servono almeno 15m point-in-time, parità degli snapshot, fee/fill/SL/TP e disponibilità AI riproducibili. Le candele 1h già archiviate non sono sufficienti a ricostruire la sequenza intrabar e non vanno suddivise artificialmente in 15m.

**Sviluppo isolato**: work/classics-12oct-selective-lab-20261029. **Nessun cambiamento** ai bot, conti, portafogli, trading, dashboard, Brain o VPS. Test o deploy operativi: non eseguiti.

AI: chatgpt (chat normale)

## Verifica automatica su GitHub Actions

Workflow offline **40815650805 = SUCCESS**. Eseguito su runner GitHub senza chiavi, SSH o VPS: 
- L'oggetto Git del file `backend/desk/signals.py` è **lo stesso identico blob** (`57b524e75593b0fe6f3a0712af1a0b2f14bd4a75`) in `a0afc63`, `7ced3a6`, `5818aee`, `18d145f` e `b4709d1` (12/10 fino alla prima crisi 16/10).
- Il blob in `dc16e01` è diverso (`869fc2ecb3bf6f4fffd7bcc86581d1f473e35627`). Il ritorno al file `signals.py` 12/10 da solo non ricrea il successo golden, perché la crisi è iniziata con lo stesso file.
- Le due guardie dell'Action confermano che i file operativi e di deploy originali non sono cambiati nel ramo di studio.
- Il backtest preesistente `deploy/scripts/desk_backtest.py` applica `tier=63` alle altcoin e `start_equity=100000` nel conto simulato, mentre la golden usava `tier=70` e conti PAPER da1000 USD. Inoltre `signals_pre_p1.py` è una versione 25/10, non la snapshot esatta 12/10. Non usarlo come prova fedele del rollback senza correggere separatamente tali condizioni e ricontrollare gestione e uscite.

Risultato: **prova di provenienza e retrospettiva superate**, non test di rendimento del rollback. Il replay A/B causale su identico feed 15m con modello dei fill e stessa configurazione originale resta non eseguito.

Nota infrastruttura: il branch di laboratorio nasce da `dc16e01` e non deve essere unito indiscriminatamente a `rule-pool` o distribuito. Nessuna nuova autorizzazione operativa richiesta o ricevuta.
