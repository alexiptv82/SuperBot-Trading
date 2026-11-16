# Brain AI Arena — Esito JSON NO_TRADE 2/2 e prossimo controllo OPEN sintetico

**Data:** 16 novembre 2026. **Ramo:** `work/arena-synthetic-open-offline-20261116`.

## Evidenze dell'utente (screenshot Termius ore 14:13)

La prova `arena-provider-json-compat-20261116.py` è finalmente riuscita con entrambe le AI:

- `ARENA_JSON_COMPAT SELFTEST=PASS_OFFLINE` — 0 chiamate, 0 segreti letti, 0 ordini.
- **Qwen** `qwen/qwen3.7-plus`: `PASS_NO_TRADE_EIGHT_FIELDS`, `finish_reason=stop`, 170 input token / 37 output token, `field_issues=[]`, `missing_fields=[]`, 0 extra, `reasoning_present=false`.
- **MiniMax** `minimax/minimax-m3.1-flash`: `PASS_NO_TRADE_EIGHT_FIELDS`, `finish_reason=stop`, 338 input / 62 output token, nessun campo mancante o errato, `reasoning_present=false`.
- `passed=2/2`, `orders=0`, `services_changed=0`, `RESULT=BOTH_PROVIDER_FORMATS_PASSED_NO_DEPLOY`.
- Limite residuo chiave prima delle chiamate: Qwen circa 1.99910848 USD; MiniMax circa 1.99995125 USD. **Non è il saldo effettivo del conto**, in precedenza utente ha dichiarato una ricarica complessiva di 10 USD.

Questo risultato certifica l'**interoperabilità per NO_TRADE con dati sintetici e ragionamento disabilitato**, non la qualità del modello sul mercato, non decisioni OPEN, non gestione del rischio, non l'uso di reasoning o la durata di 14 giorni.

## Prossima prova — OPEN soltanto come formato

Aggiunto `deploy/scripts/arena-synthetic-open-format-20261116.py`:
- `--selftest`: controlli completamente locali senza chiavi, API o ordini. Prova i casi OPEN sintetici, rifiuto di tipi sbagliati/boolean, prezzi e stop inadeguati, campi aggiunti e mancanza di dati.
- `--probe`: solo dopo conferma interattiva `SI`, una richiesta a Qwen + una a MiniMax, **nessun retry**, con lo stesso controllo di credenziali root-only (0600/0700) e chiave limitata a 2 USD. Chiede di riprodurre un oggetto JSON già fornito, **non di decidere un trade**.
- Qwen riceve esempio **LONG** fittizio `entry=100 stop=99 lev=20 confidence=0.8`; MiniMax riceve **SHORT** fittizio `entry=100 stop=101 lev=20 confidence=0.8`. Entrambe senza posizioni reali, senza feed e senza prezzi veri. L'esempio PAPER non viene tradotto in una richiesta di rischio, ordine o journal.
- Configurazioni verificate: Qwen `json_schema` con `reasoning.enabled=false`, MiniMax `json_object` e `temperature=0`, senza forcing schema.
- La validazione impone tutti gli otto campi di tipo corretto e valori fittizi coerenti: le uscite sono `PASS_SYNTHETIC_OPEN_FORMAT` o codici e nomi campi senza stampare risposte AI o chiavi.
- **Un PASS non autorizza operazioni e non convalida i trade su dati reali**. Il vero collaudo deve unire feed candela chiusa, `ArenaL5Analyst`, origin Qwen/MiniMax, mandato rischio, 2.000 USDT PAPER, protezione 450 USDT, event journal, 3 exit worker e una UI verificata.

## Vincoli invariati

- La run DeepSeek attuale **non** viene resettata o interrotta.
- Falco SHORT intatto e da preservare: archivio GitHub esistente; il backup **effettivo dei dati/strategia installati sulla VPS** resta ancora da completare prima di una pausa.
- Toro non modificato.
- AI Arena non parte finché tre runner PAPER, journaling, rischio ed exit non sono pronti e collaudati, con T0 concordato.
- Universo di ricerca: 23 cripto per capitalizzazione + oro XAUUSDT + argento XAGUSDT, stessi candidati per tutte e tre le AI, selezione approfondita limitata in base al budget. Attualmente il selettore 25 strumenti è un prototipo isolato, non connesso ai runner.
- Nessuna chiamata API, merge, deploy, pausa, restart, test GitHub Actions o trasferimento di dati di mercato è stata effettuata dalla **scrittura di questo script**.

## Test ancora da eseguire

Il nuovo `--selftest` deve essere eseguito prima di `--probe` sulla VPS o in checkout isolata, perché la stesura del codice e la revisione statica non costituiscono superamento dei test. Nessuna richiesta API viene lanciata dal codice GitHub finché l'utente non esegue espressamente `--probe` e risponde `SI`.
