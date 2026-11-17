# AI Arena — Preflight costi e comparabilità prima dei 14 giorni (17-11-2026)

## Scopo

La PR #102 contiene tre runner PAPER, uno per DeepSeek, Qwen e MiniMax. Le configurazioni iniziali di tutte e tre le AI hanno **8 simboli**, `cycle_minutes=60`, `daily_cap_usd=0.75`, `max_tokens=6000`. Il sistema dovrà poi valutare ~25 criptovalute per capitalizzazione **più oro e argento** ove esistano contratti/feed correttamente supportati. Nessuna modifica delle dimensioni dell'universo o dei limiti AI va effettuata sulla VPS senza prova di validità e decisione esplicita.

Il preflight `python -m backend.v3.arena.readiness_cli` **non** chiama modelli, non legge segreti, non avvia servizi, non scrive journal. Confronta solo le configurazioni versionate in GitHub, e deve rifiutare sempre di dichiarare il trial pronto senza prove runtime. `exit status 2` = gate non soddisfatto, non equivale a crash.

## Proiezione di sensibilità, NON spesa effettiva

Ipotesi volutamente visibile: tutti gli 8 simboli sono senza posizioni aperte e vengono valutati a ogni ciclo, 24 volte al giorno = **192 potenziali chiamate AI al giorno per modello**. In realtà il runner salta simboli con posizioni aperte e può rifiutare altre decisioni; token usati e prezzi applicati differiranno.

| Modello | Prezzi configurati (input / output, USD per 1M token) | Costo stimato in scenario da 2.500 token input + 1.000 output per chiamata | Cap configurato |
| --- | --- | ---: | ---: |
| DeepSeek | $0.30 / $1.20 | $0.3744/giorno | $0.75/giorno |
| Qwen | $2.00 / $8.00 | $2.496/giorno | $0.75/giorno |
| MiniMax | $2.00 / $8.00 | $2.496/giorno | $0.75/giorno |

**Questi non sono i prezzi reali verificati di OpenRouter:** sono quelli dei file `configs/*.json` della PR #102; per Qwen/MiniMax possono essere molto conservativi. Lo scenario medio non è una previsione della durata del budget. Il report emette anche gli scenari da 100 token output e da 6.000, tenendo conto che eventuali token di ragionamento possono rientrare nel limite output.

Se tutte e tre analizzassero 27 strumenti ogni 60 minuti, il massimo teorico sarebbe **648 valutazioni al giorno per modello**, a parità di condizioni. Il modello non va confuso con la frequenza degli stop: gli exit worker devono continuare a lavorare indipendentemente dalle chiamate AI.

## Requisiti di verificabilità prima dell'attivazione PAPER

1. **Universo:** fonte point-in-time della top 25 per capitalizzazione, simboli effettivamente supportati dal feed (candele multi-timeframe, volatilità, regole di mercato, prezzo minuti), e conferma distinta per eventuali strumenti oro/argento. L'esistenza di un ticker non è prova che sia tradabile in PAPER da questo runner; mai inventare un simbolo.
2. **Comparabilità:** stesso insieme e ordine di strumenti, capitali da 2.000 USDT, rischio e T0 per tutte le AI; registrare ragioni di esclusione delle valute e le versioni dei modelli.
3. **Budget:** verificare listini correnti di ciascun provider, supporto reale ai parametri di reasoning, uso token misurato o un test sintetico no-cost, sicurezza su ritentativi/richieste concorrenti e massimo spendibile (al livello di chiave e ledger). Non alzare cap senza consenso.
4. **VPS:** exit worker sani per tre run, bridge socket accessibile dall'effettivo UID/GID web, journal e registro motivazioni integri, backup e RESTORE riusciti; la dashboard non può sostituire dati mancanti con numeri fittizi.
5. **Samsung:** build dell'app esistente e test su schermo telefono; nessun link esterno/seconda app.
6. **Test indipendenti:** `pytest -q backend/v3/arena/test_readiness.py` e `python -m backend.v3.arena.readiness_cli` (quest'ultimo restituisce 2 finché i gate sono incompleti). Non usare GitHub Actions se i test locali sono sufficienti.

**Stato:** nuovo preflight e test aggiunti ma non ancora eseguiti nell'ambiente di Cloud/VPS. Questa patch non cambia alcun limite operativo, prezzo, simbolo, strategia o UI e non avvia il trial.
