
# SuperBot / TORO — ULTIMO TENTATIVO LONG (Supertrend 15M + 1H)
Data congelamento: 13 novembre 2026. Stato: PRE-REGISTRAZIONE; NESSUN BACKTEST DEL CANDIDATO ESEGUITO e NESSUN DEPLOY.

## Motivo della scelta, una sola ipotesi
L'utente richiede un ultimo tentativo dopo il NO-GO della strategia Bollinger (PR #96), il LONG Mirror 15m (PR #93), il Toro gemello (PR #94) e il fallimento del gate dati Binance/Bitget (PR #98; il segnale funding P non è stato direttamente testato). Donchian è già stato studiato nei laboratori; sul timeframe 4H tende ad avere trade poco frequenti e di lunga durata, lontani dall'obiettivo utente di incassare e liberare slot. La pubblicazione BinHV45 5M mostra +22,53% dichiarato dal suo autore su Bybit SPOT, non verificato su Bitget Futures; stop 3% di prezzo a 20x significa ~60% del margine esposto prima delle fee. Non copiare codebase o performance dichiarate.

**Unico candidato nuovo scelto**: Supertrend trend-following 15M/1H ispirato alla logica descritta dall'autore pubblico tanishmundra-codes/crypto_supertrend. L'esperimento NON autorizza tre strategie in sequenza; il risultato negativo fermerà la ricerca LONG rules-only di questa iniziativa. Non presentare una nuova versione come vecchio protocollo PR #97.

## Regole di ingresso congelate
Solo LONG, NO_TRADE ammesso; candele futures Bitget USDT 15m chiuse; timeframe 1h aggregato unicamente da 4 candele 15m contigue completate.
1. Supertrend(ATR Wilder 10, multiplier 3.0) su ultima candela 1H *già chiusa* = UP.
2. Supertrend(10,3) su ultima candela 15M chiusa passa da DOWN a UP rispetto alla precedente.
3. CLOSE 15m > EMA200 del close 15m.
4. RSI14(15m), Wilder, in fascia 45–75 inclusi.
5. Volume della candela 15m di segnale >= 1,2 x media volume delle precedenti 20 barre 15m CHIUSE (escludere volume trigger dalla media).
EMA200 alfa 2/201, ATR14 aggiuntivo per stop. Warmup >=250 candele 15m e >=50 candele complete 1h; OHLCV ordinati contigui/validi. Tutte queste scelte sono specifiche dell'esperimento, NON parametri ottimizzati su risultati, e non necessariamente identici ai default dell'autore.

Ingresso storico SOLO alla OPEN della candela 15M successiva alla conferma, mai stessa chiusura; un solo trade per asset fino alla chiusura del precedente. Gap o 1h non ancora chiusa -> NO_TRADE, nessuna interpolazione.

## Uscite del replay e costi; niente profit guardian ottimizzato
Stop iniziale = linea Supertrend15 al segnale - 0,25 x ATR14(15m). Stop deve essere < prezzo ingresso; distanza non corretta con leva target fissa. Take-profit completo a 2R, R = entry-stop; NO DCA, NO partial, NO modifica trailing dopo ingresso in questo primo test. Uscita temporale PRIMARIA a **12 ore (48 candele 15m)**, alla chiusura della 48ª candela (se le candele iniziano dall'entry, contabilizzare coerentemente il tempo e verificare in test).
Se stop e TP nella stessa candela, stop prevale; stop gap usa prezzo peggiore min(open, stop). TP prudente richiede HIGH > TP*(1+0.0001); uscite su prezzi osservabili, non assumere maker fill su semplice tocco.
Fee+slippage STRESS STANDARD: **16 basis point sul nozionale round-trip**, ossia taker 6bp per lato e slippage 2bp per lato; funding storico Bitget oltre 90gg non disponibile -> assunzione stress 1bp per evento di 8h LONG, scenario avverso separato 3bp. **COSTO STRESS = 30bp round trip** per altcoin, criterio GO sulla performance aggregata. Nessun claim di modello fee come funding realmente pagato.

## Universo e contaminazione storica
Cinque simboli fissati: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
Finestra fissa di ELIMINAZIONE: ultime 365 giornate di candele 15m chiuse con cutoff 2026-11-13 16:00:00 UTC (dal 2025-11-13 16:00 UTC). Test in modo rigoroso con 1H già chiuse e array as-of.
La storia è **stata in parte osservata in PR#93/#94/#96**, quindi questi risultati sono *ricerca eliminatoria retrospettiva*, NON prova out-of-sample indipendente. Anche se l'eliminazione passa, sono necessari **30 giorni forward SHADOW** dal 14 novembre 2026, prima di qualsiasi scelta operativa.

## Metriche e controlli
Salvare ogni singolo trade con simbolo, signal/end timestamp, regime 1h as-of, ST/RSI/EMA/volume, ATR, entry/stop/TP, motivo uscita, MAE/MFE, funding previsto, fee e slippage, PnL netto USDT e bp nozionale, equity/DD, SHA256 dei file OHLCV, codice e versione specifica. Salvare tutti i segnali rifiutati e segnale per mese, media durata trade e uso degli slot.
Controllo random: 1.000 semi prefissati, medesimo simbolo e mese, stessa numerosità, stesse regole di uscita/costi e distribuzione di rischio. Lo stesso set di parametri è applicato a tutti i cinque asset; niente retuning.
Baseline informativa: LONG Mirror PR#93, con avvertenza che exit, periodo e costi non sempre corrispondono; non dichiarare confronto causale perfetto.

## Soglie immutabili del gate ELIMINATORIO (TUTTE)
1. Almeno 150 trade chiusi su 365g; >=50 nell'ultimo terzo cronologico.
2. Expectancy media netta >0 su 2/3 iniziali, su 1/3 finale e sul totale (16bp roundtrip + funding stress 1bp/evento).
3. Profit factor netto aggregato >1,15 e maximum portfolio drawdown simulato <15% con sizing prudente.
4. Almeno 3 dei 5 simboli positivi netti; nessun simbolo produce oltre il 50% del profitto aggregato positivo.
5. Expectancy dei segnali oltre il 95° percentile del controllo random matched su 1.000 estrazioni, segnale completo prima del calcolo.
6. Expectancy aggregata positiva con 30bp roundtrip, mantenendo funding.
7. Test unitari anti-lookahead, calcolo 1H chiusa, casi gap/stop+TP stessa barra, replay deterministico e SHA dei dati.

Se UNO solo fallisce: **NO-GO E STOP alla ricerca di ulteriori varianti price-only di Toro in questa iniziativa**, senza cambiare filtri/timeframe/target/slippage/asset dopo il risultato. Se tutti PASS: nessun deploy automatico, solo 30 giorni SHADOW con parametri congelati; eventuale PAPER richiede consenso e test separato.

## Rischio futuro proposto, non configurazione attuale
Toro 1000 USDT, fino a 5 slot non forzati; massimo 200 USDT margine per posizione; rischio ipotizzato 12 USDT/trade, massimo 24 USDT di rischio aperto aggregato, anche quando restano slot liberi; stop tecnico decide sizing/leva, non viceversa, leva massima 45x NON un obiettivo minimo. Fee, gap e slippage riservati. Protezione equity PAPER 450 e limiti perdita giornalieri richiedono audit specifico prima di futura attivazione. Non trasferire ordini market di repo esterni nel bot.

## Isolamento
NO MERGE, NO DEPLOY, NO VPS stage modifications, NO ordini su Bitget, NO LIVE, NO GitHub Actions necessarie; SOLO nuovo ramo di laboratorio e script offline/dati di mercato pubblici con directory research. Falco SHORT originale intoccabile; Brain PAPER intoccabile; nessuna pausa/unpause classici/Brain; non sovrascrivere hotfix Brain locali.
Fonte concettuale esterna: https://github.com/tanishmundra-codes/crypto_supertrend . Esecuzioni e statistiche degli autori terzi NON sono prove Bitget.
