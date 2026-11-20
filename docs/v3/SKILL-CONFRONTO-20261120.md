# Skill di trading: confronto con e senza (20/11/2026, offline)

Metodo: per ogni tema l'analisi SENZA skill e' stata scritta e salvata prima di leggere qualunque testo della skill; poi la skill e' stata letta e l'analisi completata. Nessuno script eseguito. Costo misurato come dimensione del SKILL.md caricato (~4 caratteri per token).

## Analisi SENZA skill (scritte prima di leggere qualunque SKILL.md)

## A. Restituzione dei profitti (exit)
A1 Politica d'uscita del Brain: stop fisso, take profit 2R, timeout 24 h; nessun trailing, nessun break-even, nessun take profit parziale. Un trade che arriva a +1,8R e torna allo stop chiude a -1R: la restituzione e' strutturale.
A2 Il runtime non registra MFE/MAE; il builder li ricostruisce solo in modo approssimato dalle candele. Senza MFE non si misura la restituzione.
A3 Metriche da produrre prima di cambiare qualcosa: per trade chiuso giveback_R = MFE_R - R realizzato; quota di stop che avevano toccato >= 1R; distribuzione del tempo al MFE.
A4 Il feed a 1 m del monitor degli stop riceveva una candela in ritardo (difetto corretto offline): uscite fino a 1 minuto tardive -> parte delle "chiusure tardive".
A5 Proposte da valutare in controfattuale sulle candele attestate (etichettatore opportunity), pre-registrate: break-even a +1R, trailing ATR, take profit parziale. Nessun cambio di parametri senza il proprietario.

## B. Rischio di una posizione con leva
B1 Perdita allo stop = rischio scelto, indipendente dalla leva; la leva cambia margine e distanza dalla liquidazione.
B2 Profilo attuale: max_loss_fraction 4,29 % per trade (circa 86 USDT su 2.000): alto rispetto alla proposta v2 (1-1,5 %).
B3 Rischio aperto massimo 12 % = circa 3 posizioni piene, ma le 8 cripto sono fortemente correlate a BTC: il rischio effettivo e' quasi di una sola posizione grande. La correlazione non e' modellata.
B4 Costi: 16 bp round-trip stimati; il funding dei perpetual non e' modellato; slippage su stop in gap non modellato.
B5 Il PAPER non limita la perdita al margine (loss_exceeds_margin) mentre un isolato reale si': divergenza PAPER/reale nei gap.
B6 Vincolo perdita/margine 21,4 % + leva minima 20 escludono molte combinazioni (gia' nello studio v2).

## C. Dataset Builder e leakage
C1 Gia' presenti: feature as-of, etichette dalla prima candela dopo la decisione, split cronologico con purging sullo span delle etichette (24 h), walk_forward, assert_no_leakage, ordine di scrittura degli snapshot.
C2 embargo_ms di default 0: con feature autocorrelate un embargo > 0 e' prudente.
C3 Bias di selezione: le posizioni aperte (open_censored) sono escluse -> sovrarappresentate le posizioni chiuse in fretta.
C4 Molti confronti (celle strategia x regime x lato) con intervalli bootstrap senza correzione per test multipli: rischio di falsi positivi.
C5 Simboli decisi allo stesso istante sono campioni correlati: i conteggi "300 esempi" sovrastimano l'informazione effettiva.

## CON exit-strategies (letta dopo, SKILL.md soltanto: ~9,6 KB, ~2.400 token; references non necessarie)
Nuovi spunti applicabili:
A6 Time stop solo "se non in profitto": il nostro timeout 24 h chiude anche i trade in utile; da misurare quanti timeout erano in utile e quanto hanno reso dopo.
A7 Uscita su inversione del segnale: il motore Brain trasforma CLOSE/MODIFY_STOP in NO_TRADE (close_modify_not_executable_r1), quindi il Brain non puo' agire quando la sua tesi si inverte: canale strutturale di restituzione dei profitti. Trovato grazie alla skill.
A8 Chandelier (massimo di 22 barre - 2,5 ATR) e attivazione del trailing solo dopo il primo take profit: parametri concreti da usare come bracci controfattuali pre-registrati.
Non applicabile o sbagliato per futures USDT-M a leva: esempi PumpFun/market cap/bonding curve; liquidity exits per token Solana; "hard stop -20 %" (con 20-50x e' oltre la liquidazione); dipendenza pandas_ta.
Errori del baseline corretti: nessuno.

## CON risk-management + position-sizing (~18,8 KB, ~4.700 token)
Nuovi spunti applicabili:
B7 Riferimenti di settore per il limite di perdita giornaliero: 3-5 % del conto; il nostro HALT e' al 50 % (WARN 35 %), circa 10 volte piu' largo. Mancano anche: limite settimanale, riduzione dopo N perdite consecutive, risposta graduata al drawdown dal picco (oggi solo il pavimento 450 = -77,5 % da 2.000). Solo proposte: le soglie sono del proprietario.
B8 Metriche di rischio da aggiungere alla dashboard/collaudo: VaR e CVaR storici giornalieri, drawdown dal picco, serie di perdite.
B9 Sizing normalizzato alla volatilita': il nostro rischio per trade e' fisso ma la distanza dello stop la sceglie il modello; un tetto stop/ATR (o size ~ 1/ATR) evita stop anomali troppo stretti (costi) o larghi.
B10 Kelly frazionario (0,25x) come TETTO solo dopo un edge misurato e significativo (scoreboard positivo fuori campione); oggi Kelly non e' calcolabile: nessun edge attestato. Il 4,29 % per trade e' nella fascia "aggressiva" che la skill riserva a edge misurati: conferma B2.
Non applicabile o sbagliato per futures a leva: limiti per capitalizzazione dei token, rug pull, smart contract, bridge, MEV 1-3 %, PumpFun; sizing vincolato da pool AMM; "esposizione totale 50-80 % del portafoglio" e' una nozione spot: con la leva va espressa in MARGINE (nostro tetto 55 %) e in rischio aperto, non in nozionale. La formula fixed fractional della skill ignora i costi: il nostro risk.py li include (16 bp), quindi qui il progetto e' piu' corretto della skill.
Errori del baseline corretti: nessuno.

## CON walk-forward-validation (~9 KB, ~2.300 token)
Nuovi spunti applicabili:
C6 Embargo concreto: >= 2 volte l'orizzonte dell'etichetta; con etichette a 24 h l'embargo va a 48 h (oggi default 0, gia' segnalato in C2 ma senza valore). Finestre indicative per 15m-1h: train 14-30 giorni, test 3-7.
C7 Test multipli: Deflated Sharpe Ratio / PBO con num_trials = numero di celle e varianti provate (anche quelle scartate) da registrare; conferma C4 con un metodo preciso.
C8 Funding ogni 8 h sui perpetual: effetto di microstruttura sulle etichette a 24 h (si collega a B4: funding non modellato).
Gia' presente nel progetto (la skill conferma, non aggiunge): purging sullo span, walk_forward, nessuno split casuale, split cronologico.
ERRORI DELLA SKILL: la funzione deflated_sharpe_ratio e' incoerente (docstring "excess kurtosis" ma formula con curtosi grezza e default 3; massimo atteso senza la varianza degli Sharpe fra le prove; Sharpe annualizzato con errore standard per osservazione). Da non copiare: se servira', implementare da Bailey & Lopez de Prado (2014) con test.
Non applicabile: sopravvivenza dei token delistati (8 large cap, rischio basso).
Errori del baseline corretti: nessuno.

## Sintesi

| Skill | Costo al caricamento | Migliora l'analisi? | Errori o parti inapplicabili | Raccomandazione |
|---|---|---|---|---|
| exit-strategies | ~2.400 token | Si': 3 spunti nuovi applicabili (time stop solo se in perdita, uscita su inversione della tesi bloccata dal motore, parametri trailing concreti) | molti esempi PumpFun/Solana; "hard stop -20 %" incompatibile con la leva | tenere |
| risk-management + position-sizing | ~4.700 token | Si': riferimenti per daily/weekly loss, perdite consecutive, VaR/CVaR, sizing normalizzato alla volatilita', Kelly solo come tetto | nozioni spot (esposizione in nozionale), AMM, rug/MEV; fixed fractional senza costi (il progetto e' migliore) | tenere entrambe (usate insieme) |
| walk-forward-validation | ~2.300 token | Si': valore dell'embargo (>= 2x orizzonte), Deflated Sharpe / PBO per i test multipli, funding 8 h | **formula DSR errata**; il resto e' gia' nel Dataset Builder | tenere con l'avviso |
| trade-journal | ~2.700 token | Poco: alcune analisi riutilizzabili (durata vincenti vs perdenti, per ora/simbolo) | formato pensato per trader umano, campi mutabili e testo libero contrari all'EventJournal | tenere a bassa priorita'; da escludere se non porta risultati nel collaudo |

Nessuna skill ha corretto un errore dell'analisi di base; tutte hanno aggiunto spunti. Le correzioni utili sono andate nel senso opposto: due difetti delle skill (formula DSR, sizing senza costi) individuati confrontandole con il progetto.
