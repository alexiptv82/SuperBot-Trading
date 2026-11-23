# 2026-11-23 — Priorità Brain Unico PAPER + dashboard

## Decisione del proprietario
- PRIORITÀ ASSOLUTA: avviare rapidamente il Brain Unico in PAPER e osservare profitto netto, perdite e drawdown. Limitare audit, ricerche e backup aggiuntivi che ritardano l'esperimento.
- Dashboard SuperBot aggiornata stile Falco/Toro: equity, PnL aperto/realizzato, posizioni e trade, profitti e perdite, decisioni AI, memoria, chiusura manuale singola, visualizzazione dell'apprendimento.
- DeepSeek è l'AI principale. Claude supporta revisioni del codice e analisi dei risultati; NON dichiarare Claude automaticamente collegato al runner senza reale integrazione e prove. Ridurre consumo di Claude.
- Loop di miglioramento: PAPER, metriche, una modifica controllata, nuovo PAPER. Valutare PnL netto di commissioni/costi, drawdown, payoff medio e profit factor. Le prime 72h sono test tecnico, non prova di redditività.
- La prova di decrittazione esterna col PC o Android resta incompleta, ma il proprietario accetta di RINVIARE quel requisito SOLO per il test PAPER. Backup locale/ripristino di prova e backup esterno cifrato già positivi da Termius. NON dichiarare la certificazione esterna completa.
- Restano obbligatori in PAPER: assenza di ordine reale, corretta modalità paper, exit sidecar sano, limite rischio, stop nuovi ingressi, pause e journal. Sicurezza avanzata e recoverability completa prima di eventuali soldi veri.
- Salvaguardare i dati storici. Falco/Toro tecnicamente conservati ma semanticamente non certificati: non usare i loro record non certificati per training.

## Evidenze GitHub verificate da ChatGPT
- Branch integration/brain-unico-20261119 head e4864d80cbe67f88c8a812f7b50e43a9e5a85d20 alla verifica; nuovo 00-precollaudo-completo.sh preparato, non ancora dimostrato eseguito in VPS.
- frontend/src/pages/BrainUnico.js ESISTE già, route /brain-unico home, refresh 30s, quattro API overview/status/trades/memory, PnL, posizioni, close controls, memoria. Build e deploy della dashboard attiva non ancora verificati su VPS.
- Config backend/v3/runner/runner_config_brain_unico_paper_b.json: 2000 USDT PAPER; perdita stimata allo stop per trade 1%; 4% rischio aperto; fino a quattro posizioni; stop nuove aperture perdita giornaliera 4%; leva 1-30x; 8 simboli; deepseek-flash; ciclo 60m; budget AI 0.75 USD/die. Nessuna garanzia di rendimento.
- Issue #124 P0 chiusa. Mandato della run nuova deve restare approved:false finché non arriva consenso esplicito successivo.

## Percorso operativo breve
1. Claude completa il pre-collaudo essenziale con script già pronto e consegna risultati PASS/FAIL; se permessi root mancanti, un solo comando specifico da Termius. Non aggiungere nuove fasi di audit o backup.
2. Con autorizzazione separata, predisporre deploy della dashboard già sviluppata, sua API sulla nuova run e test della chiusura manuale singola, salvando rollback. Non pubblicare modifiche web senza consenso.
3. Con pre-collaudo superato, dashboard verificata e consenso esplicito, autorizzare mandato e avviare 72h PAPER. Il pre-collaudo da solo non autorizza il mandato.
4. Registrare PnL netto, drawdown, medie win/loss, profit factor, rischio, trade per verso/simbolo, costo AI, decisioni NO_TRADE e memoria; poi test più lungo (es. 14 giorni) per giudizio preliminare, nessuna promessa di redditività.

Questo documento salva la decisione: non è autorizzazione automatica a deploy/merge/trading.