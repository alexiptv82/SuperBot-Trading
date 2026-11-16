# AI Arena — prima comparazione reale delle tre AI (16 novembre 2026, 21:05 Europe/Rome)

## Evidenza osservata
Sorgente: screenshot Termius fornito dall'utente. Esecuzione manuale su VPS Singapore della prova a pagamento `arena-three-ai-research-oneshot-20261116.py`. Non ci sono posizioni aperte, servizi modificati o file scritti dall'esperimento. Stato: `ARENA_TRIO RESULT=THREE_HISTORICAL_MODEL_CHOICES_RECORDED_NO_DEPLOY`, `ARENA_TRIO results=3/3`, `orders=0 files_written=0 services_changed=0`.

Il modello riceve una **fotografia storica** congelata di 25 mercati (23 crypto + XAUUSDT/XAGUSDT) con input uguale a tutte le AI, non dati di mercato live. Input origin SHA256: `fba771b33ad1935614df124d74c357b63d66694f47193abb65ed514c77ed4bdd`, input comune SHA256: `3c834a5659f3d32b63c2bb969b59778d5bf58b30dc2f8afcfec333ac863cb58e`, dimensione 11415 byte.

## Risposte reali

| Provider ricerca | Modello richiesto | Azione | Simbolo | Lato | Confidenza | Ragione dichiarata | Token ingresso | Token uscita |
|---|---|---|---|---|---|---|---:|---:|
| DeepSeek | `deepseek/deepseek-v4.1-flash-1017` | NO_TRADE | — | NONE | 0 | `BROAD_4H_DOWNTREND_NO_CLEAN_ALIGNMENT` | 6269 | 42 |
| Qwen | `qwen/qwen3.7-plus` | CANDIDATE | DOGEUSDT | LONG | 0.65 | `MOMENTUM_BREAKOUT_15M` | 8115 | 62 |
| MiniMax | `minimax/minimax-m3.1-flash` | NO_TRADE | — | NONE | 0 | `NO_MULTI_TIMEFRAME_ALIGNMENT` | 6383 | 30 |

OpenRouter per lo stesso esperimento: `DEEPSEEK_key_limit_usd=2 remaining_before_usd=1.989912`, `QWEN_key_limit_usd=2 remaining_before_usd=1.989912`, `MINIMAX_key_limit_usd=2 remaining_before_usd=1.999839523` (valori pre-chiamata; **non sono addebiti esatti**). Il test completato ha effettuato tre chiamate a pagamento, nessun ordine; i costi effettivi vanno recuperati dal provider.

## Interpretazione (ipotesi, non prova di profitto)
- Qwen individua un LONG di breve periodo su DOGEUSDT per breakout 15m, in disaccordo con due NO_TRADE che vedono una mancanza di allineamento sui timeframe superiori.
- Non significa che Qwen sia migliore: un solo campione, nessun risultato forward attribuibile, confidenza 0.65 NON calibrata. I motivi testuali sono codici sintetici, non spiegazioni esaustive.
- Il modello DeepSeek utilizzato via OpenRouter **non è verificato equivalente** al modello/parametri effettivi del Brain operativo. Non usare questa prova per giudicare i suoi risultati storici.
- I tre risultati sono una istantanea storica; non creare un LONG automatico o modificare gli altri bot in base a questa prova.

## Prossimo gate
1. Definire e implementare un **journal append-only** di prove shadow con campi timestamp dello snapshot, SHA input e prompt/policy, provider/model/parametri, proposta completa, metadati token, costo addebitato verificabile e numero chiamate; non registrare mai segreti. Possibile controllo in sola lettura della versione DeepSeek reale prima di chiamare i modelli di nuovo.
2. Campionare più mercati/regimi **fuori campione** e raccogliere controfattuali LONG/SHORT e NO_TRADE nel tempo; stessa regola di rischio/commissioni applicata a tutti. Misurare l'esito forward senza look-ahead e confrontare con sempre-SHORT e scelte casuali appaiate. Un candidato non basta a classificare i modelli.
3. Solo dopo integrare un comparatore PANEL nell'app e tre portafogli indipendenti PAPER da 2000 USDT ciascuno, previa verifica del sistema uscite e dei limiti di rischio. I 14 giorni PAPER **non sono iniziati**.

## Custodia
Ramo dedicato soltanto alla documentazione, nessun deploy/merge, nessuna modifica al Brain attuale o a Falco SHORT; Toro resta non prioritario. La proposta di collaborazione fra modelli resta da sperimentare **dopo** un confronto indipendente sufficiente.
