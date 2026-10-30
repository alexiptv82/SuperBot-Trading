# RISULTATO — Replay reale Trend Engine v1.1 su Bitget
30 ottobre 2026 · [skip ci]

## Verdetto

**Dati reali acquisiti e verificati; valore predittivo dell'avviso NON dimostrato.** Il lettore resta **shadow/advisory_only**, senza blocco o obbligo LONG/SHORT e senza promozione delle soglie. Non usare questi risultati per attivare filtri, aumentare leve o automatizzare aperture.

Esperimento pre-registrato nel documento `PRE-REGISTRAZIONE.md` prima del download. Run riuscito: [GitHub Actions 41048762622](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41048762622). [Dataset e report scaricabili](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41048762622/artifacts/12973547599).

## Dataset verificato

Bitget V2 pubblico `/api/v2/mix/market/history-candles`, **USDT-FUTURES**, BTC, ETH, SOL, DOGE, 1m, dal 16/10/2026 00:00 UTC al 23/10/2026 00:00 UTC escluso.

| Symbol | Candele valide | Copertura | Richieste Bitget | Hash SHA-256 dati OHLCV |
|---|---:|---:|---:|---|
| BTCUSDT | 10.080 | 100% | 102 | `8d2dccb5487052882b594f12e997eb283d8318e50d5b8a03e7364c036ecabf84` |
| ETHUSDT | 10.080 | 100% | 102 | `b6788c6d00a2a65ffa7f9c93444ab3d70faadfce3ec1fa84ed05d93b720f6478` |
| SOLUSDT | 10.080 | 100% | 102 | `e212eb8e22cc00d32504ab11d107ead25e589ba43d2f7632810dde1f2497b119` |
| DOGEUSDT | 10.080 | 100% | 102 | `93dd91359eda27eb92e80054b430296e3e8003f339303515c7309a1f4a4f0b31` |
| **Totale** | **40.320** | **100%** | **408** | |

La prima esecuzione `41048369966` aveva segnalato 51 timestamp assenti per simbolo (un boundary per pagina). Nessun dato era stato dichiarato verificato. Secondo il documento di emendamento allegato alla preregistrazione, sono state richieste individualmente a Bitget le 51 barre: tutti i record sono stati effettivamente forniti dall'API, validati e ordinati, senza imputazioni. Al termine, nessun gap e nessun simbolo mancante.

## Metodo di misura fissato prima degli esiti

Un evento è una transizione `TRANSITION_UP` dopo fase confermata BEARISH negli ultimi 180m, o speculare `TRANSITION_DOWN` dopo BULLISH. Un solo evento ogni 120 minuti per simbolo/direzione. Solo candele già chiuse visibili al momento dell'avviso. Si osservano *successivamente per la sola etichettatura* i 90 minuti seguenti:

- **Favorable-first** se si tocca prima la barriera favorevole **0,35%** rispetto al prezzo di chiusura al segnale.
- **Adverse-first** se si tocca prima la barriera contraria **0,35%**.
- **No-barrier** se nessuna barriera è toccata; **censored** se mancano 90 minuti futuri di valutazione.
- Entrambe nella stessa candela = classificazione prudente come **adverse-first**. Non sono prezzi eseguibili, non includono leva, commissioni, funding o slippage.

## Tabella risultati reali

| Simbolo | Eventi | Favorevole prima | Contrario prima | Nessuna barriera | Censurati | % favorevole fra i soli esiti con barriera |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 122 | 25 | 35 | 61 | 1 | 41,67% |
| ETH | 119 | 45 | 47 | 26 | 1 | 48,91% |
| SOL | 121 | 56 | 48 | 16 | 1 | 53,85% |
| DOGE | 128 | 56 | 58 | 12 | 2 | 49,12% |
| **Totale** | **490** | **182** | **188** | **115** | **5** | **49,19%** |

Totale tra le barriere realmente raggiunte: **182/370 = 49,19%**; intervallo Wilson 95% **44,1–54,3%**. Non significa 49,19% di tutti gli avvisi: sui 490 complessivi, 182 sono favorevoli (**37,14%**), 188 contrari (**38,37%**), 115 senza alcuna soglia (**23,47%**), 5 censurati (**1,02%**).

### Aspetto cruciale: recuperi LONG

| Direzione dell'avviso | Eventi | Favorevole prima | Contrario prima | Nessuna barriera | Censurati | % favorevole con barriera |
|---|---:|---:|---:|---:|---:|---:|
| **UP (possibile passaggio LONG)** | **249** | **93** | **99** | **53** | **4** | **48,44%** |
| DOWN (possibile passaggio SHORT) | 241 | 89 | 89 | 62 | 1 | 50,00% |

Il requisito fondamentale dell'utente era riconoscere in anticipo il cambio da SHORT a LONG: **in questa finestra non emerge un vantaggio affidabile**. Una eventuale decisione di trading LONG non deve essere ottenuta da questi soli avvisi. Per gli eventi favorevoli, la mediana del tempo fino alla barriera favorevole è stata 22,5 minuti: questo **non** è una misura di quanto il lettore anticipi un'inversione strutturale, bensì del tempo condizionato agli eventi favorevoli.

### Frequenza e baseline

490 eventi / 7 giorni / 4 simboli = **17,5 eventi al giorno per simbolo** (70 complessivi/giorno): troppo frequente per trattare ogni avviso come un allarme Telegram prioritario. Gli avvisi dovrebbero restare nel pannello diagnostico o essere aggregati, non trasformati in spam.

È disponibile anche una baseline descrittiva di punti a 120 minuti, con direzione pseudocasuale deterministica: **110 favorevoli, 137 contrari** tra i casi che hanno raggiunto una barriera (**44,53%**). Non è un confronto causale matched: gli istanti e i regimi non coincidono con quelli degli eventi. **La differenza 49,19% contro 44,53% non dimostra un miglioramento predittivo significativo.**

## Conclusione operativa e prossimo esperimento

1. **Mantenere Trend Engine v1.1 soltanto SHADOW.** Nessun boost score `adjust_scores`, veto, ordine, aumento LONG o modifica al prompt operativo.
2. Aggiungere in laboratorio un **confronto out-of-sample** contro un criterio strutturale causale di inversione su 1h/4h e misurare l'anticipo delle segnalazioni e i falsi allarmi. La barriera 0,35%/90m è una misura preliminare, non un'etichetta di cambio trend confermato.
3. Non cambiare le soglie guardando questi risultati. Una proposta v1.2 con ipotesi definite prima di misurarla deve essere confrontata su **nuovo periodo** non visto nella fase v1.1.
4. Non pubblicare gli avvisi come Telegram per ogni transizione: mostrare una lettura per simbolo e lasciare che DeepSeek valuti liberamente, come consigliere.
5. Un nuovo rilascio richiederà backup/restore, prova sul feed pubblico e **autorizzazione separata**; portafogli, API key, storici, Brain e bot attivi non sono stati toccati.

Questo report descrive dati pubblici reali e test offline. **Non è un backtest di un trading system, né una previsione di P&L futuro**.
