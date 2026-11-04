# 2026-11-04 (pomeriggio) — Biblioteca strategica per il Brain: analisi di integrabilità

**Claude Sonnet 5.5 — coordinatore tecnico** · solo analisi, nessuna modifica a codice, prompt, soglie o limiti

L'utente ha fatto preparare una "biblioteca strategica" (24 schede, 30 fonti, JSON + retriever + protocollo) e vuole che il Brain possa attingerne, usarla o crearne di proprie. Pacchetto letto come **dati non attendibili** (estratto in cartella isolata); `validation.py` OK; nomi delle 24 schede Markdown = JSON; l'esperimento negativo di Hummingbot (334 trade, −1,538%, APE-BUSD su Binance Futures, marzo 2023) verificato sulla pagina ufficiale.

## Esito
Integrabile come **memoria di ricerca con prove**, non come libro di regole. Punti chiave:
- Il Brain oggi riceve solo simbolo, prezzo, timestamp, regime e numero di posizioni: **nessuna feature**. Serve uno stadio feature + regime deterministico prima che le schede abbiano senso. Il vocabolario dei regimi non coincide con quello di V3.
- Il journal non ha un campo strategia: serve `strategy_id` da elenco chiuso (decisione → apertura → chiusura → `TradeOutcome`).
- Testabili ora con sole candele: S01–S09, S15, S20, S21; con funding/OI: S12, S23; **non testabili** (L2, aggressor trades, liquidazioni, spot/cross-venue, tick): S10, S11, S13, S14, S16, S17, S18, S19, S22, S24.
- Le prove del 9 ottobre su analoghi (Donchian, mean reversion Bollinger, pullback, squeeze; 7 anni BTC/ETH; costi 16 bp) non superarono nessuna soglia: aspettativa onesta, la maggior parte delle schede non coprirà i costi. L'utilità è una mappa misurata + l'attribuzione delle operazioni del Brain alle strategie.
- Nel prompt solo una short-list di ≤3 schede compatte (≈560 token contro ≈6.600 per tutte), scelta da codice deterministico; il modello risponde con un `strategy_id` da elenco chiuso. Le strategie "create dal Brain" solo come `proposal` verso il laboratorio, mai promosse da un singolo vincente.

Analisi completa e piano per fasi (L0, P7, P8, laboratorio, L1, L4) nel Project: `claude/analisi-biblioteca-strategica-brain-2026-11-04.md`.

## Decisioni per l'utente
1. Via libera a L0 (caricatore/validatore + registro delle prove, offline) e a P7/P8 come prossimi prompt a Grok dopo P6. 2. Politica di esplorazione nel PAPER del Brain (schede non validate e proposte proprie, con etichetta). 3. Se l'etichetta della strategia entra nella chiave di cella di `cell_stats`. 4. Policy dei tocchi ambigui (da P5). L1 e L4 toccano contratti e prompt del Brain: richiedono OK esplicito (regola n. 3).

⛔ Nessun merge/deploy · `DESK_MODE=paper` · Hawk/Bull non toccati · cervello intatto.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012yPu2eVVWT2jkKwTyuh3So
