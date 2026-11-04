# 2026-11-04 (pomeriggio) — L0: biblioteca strategica nel repo (PR #46, bozza)

**Claude Sonnet 5.5 — coordinatore tecnico** · solo dati e validazione: nessun collegamento col Brain, col journal, coi prompt, con soglie o limiti

Dopo l'OK dell'utente ("ok perfetto procedi") alla fase L0 dell'analisi: `backend/v3/knowledge/` con le 24 schede e le 30 fonti del pacchetto, **fissate con SHA-256** (mai scaricate a runtime; `.gitattributes -text`).

## Cosa fa
- `library.py`: caricatore rigido (chiavi esatte, tipi esatti, elenchi chiusi, `fullmatch` su cifre ASCII, URL solo https, date reali, testo libero senza backtick/graffe/URL/tag, unicità, riferimenti alle fonti). Nessuna scheda può dichiarare `proven_profitable`/`validated_on_bitget` veri o uno stato diverso da `research_only`; ogni feature richiesta è classificata a mano. 9 fasi di validazione con codici e ordine documentati; hash controllato **prima** del JSON; BOM, NaN/Infinity e chiavi duplicate rifiutati.
- Classificazione dei dati: **12 schede** si provano con le sole candele (S01–S09, S15, S20, S21), **2** con candele + funding/OI (S12, S23), **10** richiedono dati nuovi. `spread` e `fees` sono modellati, non misurati.
- Registro prove: 8 voci `analog` dal laboratorio del 9/10 (CI 37916437081, costi 16 bp), con le differenze scritte e 3 voci che dichiarano il **timeframe fuori scheda** (S07 4h; S05 e S21 1h). Una prova `analog` non cambia lo stato di una scheda.

## Verifica
Suite V3 **1215 → 1647 passed** (+432; 3 xfailed e 3 failed per `fastapi` mancante: invariati). Oracolo indipendente: JSON riletto nel test e confrontato campo per campo; tabella A/B/C e lacune scritta a mano; numeri del registro uguali a una copia a mano della tabella del documento. Un difetto isolato per ogni codice d'errore, in più posizioni; test di precedenza fra le fasi; testo ostile (unicode a larghezza piena, `\n` finale, bidi, tipi non hashable, `bool` per `int`). **Mutazione: 165/165 uccisi sul codice finale** (primo passaggio 165/167: i 2 sopravvissuti erano equivalenti, rimossi semplificando il codice). **Mio errore corretto in corsa:** lo strumento di scrittura aveva trasformato le sequenze `\uXXXX` dei test in caratteri invisibili letterali (bidi, zero-width, NBSP): riportati a escape; trovato anche un carattere non ASCII nel modulo (corretto). Un commit di codice con `[skip ci]` per svista, non ancora pubblicato, riscritto prima del push.

## Limiti
Contenuto delle schede da fonti esterne, non verificato punto per punto (video non visionati integralmente; verificata la pagina ufficiale dell'esperimento negativo Hummingbot: 334 trade, −1,538%). Prove `analog` ≠ prove delle schede. Nessuna short-list né selezione: **L1 (`strategy_id` nel journal) e L4 (short-list nel prompt del Brain) restano in attesa dell'OK esplicito dell'utente** (regola n. 3).

## Prossimo
- **Grok — P7** indicatori a barre chiuse (`v3/features/indicators.py`: EMA, ATR, ADX, RSI, MACD, Bollinger, Donchian, con prova di non-lookahead); prompt pronto: `claude/prompt-grok-p7-indicatori-2026-11-04.md` (punto di partenza `83dc447`).
- In attesa di Grok: **P6** walk-forward (`learning/walkforward.py`).
- Poi: P8 regime (parametri obbligatori), rilevatori delle schede a sole candele, laboratorio su storico BTC/ETH in CI.

⛔ Nessun merge/deploy · `DESK_MODE=paper` · Hawk/Bull non toccati · cervello intatto.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012yPu2eVVWT2jkKwTyuh3So
