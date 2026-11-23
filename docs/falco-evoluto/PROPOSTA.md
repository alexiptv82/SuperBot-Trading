# Falco Evoluto vs Brain Scalp — proposta tecnica (23/11/2026)

Ramo `claude/falco-evoluto-20261123` (da `cd56fb71`). Solo PAPER. Nulla installato, nessuna run creata, nessun
mandato toccato. Falco originale, Toro, Brain RC1 e Arena invariati.

## 0. Stato reale verificato (utente `superbot-agent`, sola lettura)

| Componente | Stato |
|---|---|
| Brain RC1 uscite / runner | `active` dalle 06:38 UTC, 0 riavvii. Pausa e mandato NON leggibili senza root (run 0700) |
| Falco / Toro classici (desk V2) | nessun processo in esecuzione; dati `/opt/superbot-desk-data/{hawk,bull}` presenti (root) |
| `superbot-v3-falco-exit` / `-toro-exit` | `failed` dal 14/11 06:28 (exit-code 2), `disabled` |
| Vecchio Brain V3, Arena (3 uscite, 2 runner), bridge, relay Telegram | `active` |

## 1. Cosa esiste gia' e si riusa (niente nuova architettura)

| Bisogno | Esistente |
|---|---|
| SHORT di Falco | `backend/desk/signals.py` (punteggio 1h/4h/1d, RSI, momentum, volumi, ATR, pattern) + `brain.rules_decisions` |
| Regimi | `backend/v3/features/regime.py`: TREND_UP, TREND_DOWN, RANGE, EXPANSION, SHOCK, UNCERTAIN |
| Inversioni | `desk/trend_change.py` (incrocio EMA20/50 su 1h chiusa, contesto 4h), `v3/detectors/reversal.py` |
| Indicatori | `v3/features/indicators.py` (EMA, RSI, ATR, ADX, MACD, Bollinger, Donchian) |
| Portafoglio PAPER, journal, rischio, mandato, pausa | runner V3 (`runner/wiring.py`, `brain_f2/engine.py`, `risk.py`, `MandateFile`) |
| Analista sostituibile | `run_brain_cycle(analyst=...)`: oggi `MarketEntryAnalyst(DeepSeekL5Analyst)` |
| AI con budget registrato | `MeteredTransport` + `BudgetLedger` + `spending_gate` (per run) |
| Uscite | `runner/exits.py` + servizio uscite (proprietario unico) + monitor 1m |
| Laboratorio uscite | `ops/brain-unico/exits/` pre-registrato 21/11: BE, trailing, protezione, inversione |
| Confronto multi-run | `v3/arena/read_view.py` (N journal indipendenti, win rate, posizioni) |
| Chiusura manuale PAPER | bridge `close_bridge_server.py` (run configurabile da ambiente) |

**Scelta:** Falco Evoluto diventa una **seconda run V3** con un analista a regole derivato dal codice di Falco.
Cosi' i due portafogli hanno la STESSA contabilita' (EventJournal), le stesse commissioni (6 bp/lato) e
slippage (2 bp), lo stesso servizio uscite e la stessa dashboard: il confronto e' omogeneo per costruzione.
Il desk V2 (Falco originale) non viene modificato ne' riavviato: resta la fonte storica e il riferimento.

## 2. Falco Evoluto — moduli

1. **SHORT (originale):** porting fedele del punteggio `signals.read_symbol` lato SHORT e della soglia di
   `rules_decisions`, su candele CHIUSE. Limiti noti dall'audit del 12/11 (EMA200 4h di fatto EMA61 con 60 barre,
   trend 1d): restano documentati, non corretti in silenzio. Una correzione e' una scelta del proprietario.
2. **LONG (nuovo, indipendente, non S25):** apre solo se TUTTE: regime 4h `TREND_UP`, trend 1d rialzista,
   EMA20>EMA50 su 1h, RSI 1h 50–70, volume ≥ media, nessun segnale di inversione ribassista nell'ultima 1h chiusa,
   punteggio long ≥ soglia. Stessa formula di stop (1,2×ATR 1h) dello SHORT.
3. **Filtro di contesto (entrambi i lati):** NO_TRADE se regime `UNCERTAIN`/`SHOCK`, se 1h e 4h sono in
   disaccordo con punteggi vicini (scarto < 10), o se il lato e' contrario a regime 4h + trend 1d concordi.
   NO_TRADE e' sempre registrato nel journal con il motivo.
4. **AI raramente (semi-automatico):** DeepSeek tramite `MeteredTransport` con **budget proprio** della run.
   Chiamata solo quando: (a) LONG e SHORT entrambi ≥ soglia con scarto < 10; (b) il regime 4h e' cambiato
   nell'ultima candela chiusa; (c) inversione 1h contro il lato proposto. L'AI puo' solo **confermare il lato
   proposto dalle regole o dire NO_TRADE** (mai inventare simboli, leva o stop). AI non disponibile o budget
   esaurito → NO_TRADE. Ogni chiamata e' nel journal (`brain_decision`) e nel registro spesa.
5. **Uscite:** sezione 3.

## 3. Protezione dinamica dei profitti — IMPLEMENTATA (questo ramo)

`runner/exits.py` + `runner/monitor.py`, politica **schema 2** (lo schema 1 di oggi resta identico; Brain RC1
usa il proprio codice installato e non cambia):

- **Break-even corretto per i costi:** stop a ingresso + (2 × commissione + slippage stop) solo dopo +`be_at_r` R.
- **Trailing legato al rischio iniziale:** da +`trail_at_r` R, stop a `trail_dist_r` R dal miglior prezzo.
  R = distanza dallo stop iniziale, che e' gia' 1,2×ATR: il trailing segue quindi la volatilita' d'ingresso.
- **Protezione di quota:** da +`protect_at_r` R blocca `protect_frac` dell'escursione favorevole.
- Aggiornamento solo a **candela chiusa** (nessuno sguardo dentro la candela), stop **mai** all'indietro,
  ripresa identica dopo un buco del feed, uscita `stop` con `stop_kind` (break_even/trailing/protect).
- **Nessuna chiusura legata all'ora** (non esiste ne' nel desk ne' in V3); resta la durata massima per posizione.
- Test: `backend/tests/test_v3_exit_protection.py` (14), incluso il confronto con i 6 bracci pre-registrati del
  laboratorio (stesse uscite, stesso prezzo, stessa candela).

**Non ancora:** chiusure parziali e riduzione dell'esposizione quando il trend si indebolisce. Il journal V3 oggi
chiude solo posizioni intere: servono un evento di chiusura parziale e il suo trattamento in riepilogo, esiti e
scoreboard (fase 2). Fino ad allora la "protezione di quota" e il trailing coprono la stessa esigenza.

**Parametri proposti per Falco Evoluto (da approvare):** take-profit 3R, break-even a +1,0R, trailing da +1,5R a
1,0R, durata massima 24 h. Motivo: lo stop non si sposta prima di 1R (richiesta "non troppo presto"); il trailing
parte quando il trade ha gia' coperto il rischio. Brain Scalp: politica attuale (TP 2R, 24 h) oppure la stessa,
a scelta del proprietario. Il laboratorio continua a misurare i bracci alternativi sulle stesse entrate.

## 4. Brain Scalp

Non esiste un "Brain Scalp" attivo (il pacchetto `brain_scalp` di ottobre non e' mai stato collegato). Due opzioni:
- **A.** usare Brain RC1 cosi' com'e' (ciclo 60 min, profilo B). Ha gia' una storia: il confronto non parte insieme.
- **B. (consigliata)** nuova run V3 `brain-v3-scalp-paper-*` con lo stesso codice di RC1, 2.000 USDT, avviata
  INSIEME a Falco Evoluto. Eventuali differenze "scalp" (ciclo 15 min, durata massima piu' breve) sono parametri
  da approvare. RC1 resta intatta e in pausa.

## 5. Confronto

- Stessi 8 simboli (quelli di Brain), stesso periodo, stesse commissioni e slippage, funding come oggi.
- Decisioni indipendenti: nessuna sincronizzazione delle aperture.
- Metriche per portafoglio: rendimento %, P&L netto, drawdown massimo (equity a candela chiusa), rapporto
  rendimento/drawdown, profit factor, vinti/persi, risultati separati LONG/SHORT, spesa AI.
- Dashboard: pagina "Confronto" in sola lettura che riusa `arena/read_view.py` per due run (+ drawdown e
  LONG/SHORT). La chiusura manuale singola resta disponibile per ciascun portafoglio tramite bridge.

## 6. Fasi

1. **Fatto:** protezione dei profitti nel runtime (questo commit).
2. Analista Falco Evoluto (SHORT originale + LONG + filtri) con test su vettori fissi.
3. Arbitro AI raro con budget proprio e test (AI giu' → NO_TRADE).
4. Pagina Confronto + metriche (drawdown, LONG/SHORT).
5. Preparazione delle due run (cartelle, configurazioni, unita') con un unico comando root, mandati `approved:false`.
6. Avvio del confronto solo con l'approvazione finale del proprietario.

## 7. Decisioni richieste al proprietario

1. Brain Scalp: opzione A o B (e, se B, eventuali parametri scalp).
2. Parametri d'uscita di Falco Evoluto (sezione 3) e se applicarli anche a Brain Scalp.
3. SHORT originale: porting fedele con i limiti noti, oppure con le correzioni gia' preparate il 12/11.
4. Budget AI giornaliero di Falco Evoluto (proposta: 0,20 USD) e provider (DeepSeek, gia' configurato).
5. Leva e margine di Falco Evoluto su 1.000 USDT (proposta: profilo B scalato: rischio 1 %/trade, rischio aperto
   4 %, margine per posizione 20 %, totale 50 %, minimo 800).
