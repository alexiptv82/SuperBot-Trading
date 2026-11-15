# Laboratorio LONG (Fable) — preregistrazione

**Data di congelamento:** 15 novembre 2026, PRIMA di qualunque calcolo sui dati giornalieri multi-asset.
**Stato:** sola ricerca offline. Nessun bot, servizio, strategia o parametro operativo viene toccato.

## Contaminazione dichiarata

L'autore ha già visto: (a) candele 15m BTC/ETH/SOL Bitget dal 12/04/2025 al 13/11/2026 e i risultati negativi delle
strategie LONG intraday su quel campione (PR #93, #94); (b) i verdetti dei laboratori precedenti (strategie 9/10,
long-lab ed edge-lab 29/10, BB100, Supertrend). Sa quindi che il 2025–2026 è stato in prevalenza ribassista/laterale
per quei tre mercati. NON ha visto dati giornalieri dell'universo esteso, né alcun risultato delle ipotesi qui sotto.
Nessun parametro verrà cambiato dopo i risultati: un parametro per ipotesi, scelto per convenzione e motivato qui.

## Dati

- Bitget USDT-FUTURES, candele giornaliere UTC (`1Dutc`) di tutti i perpetual crypto oggi quotati (`isRwa = NO`,
  esclusi stablecoin e oro tokenizzato), dall'inizio dello storico disponibile. Solo candele chiuse, nessuna interpolazione.
- **Bias di sopravvivenza dichiarato:** i contratti rimossi dal listino non sono scaricabili; il bias favorisce i LONG.
- **Universo "a quella data":** al giorno *t* sono ammessi i simboli con almeno 90 candele fino a *t* e con mediana a
  30 giorni del volume in USDT fra le prime 30 dell'insieme ammesso (calcolata solo con dati ≤ *t*). BTC ed ETH sempre inclusi.
- Decisioni alla chiusura giornaliera (00:00 UTC), ingresso all'apertura della candela successiva.

## Costi

Base: 16 bp a giro (commissione 6 + slippage 2 per lato) + funding LONG 1 bp/8h (3 bp al giorno).
Stress: 30 bp a giro + funding 3 bp/8h (9 bp al giorno). Gli SHORT speculari non incassano funding (prudente).

## Periodi (gli stessi dei laboratori precedenti, l'ultimo esteso a oggi)

DEV: inizio → 31/12/2023. VAL: 01/01/2024 → 30/06/2025. TEST: 01/07/2025 → 14/11/2026.
Non c'è taratura: i periodi servono solo a verificare la stabilità del segno.

## Filtro di mercato unico (G)

G = chiusura giornaliera BTC > media semplice a 100 giorni di BTC. Scelta di convenzione (via di mezzo fra 50 e 200).
Le varianti 50 e 200 saranno riportate solo come sensibilità descrittiva, mai usate per scegliere.

## Ipotesi

### H1 — Deriva di regime (diagnostica)
Rendimento giornaliero medio dell'universo equipesato, e di BTC, separato per G acceso/spento.
Serve a quantificare quanta parte del risultato di LONG e SHORT è semplice deriva del mercato.

### H2 — Forza relativa (momentum cross-sezionale), solo LONG
Ogni lunedì 00:00 UTC: classifica per rendimento a 28 giorni; LONG equipesato sui primi 5 per una settimana.
Confronti: universo equipesato, BTC, ultimi 5, 5 a caso (1.000 estrazioni). Versione con filtro G e senza.
Previsione: primi 5 > universo > ultimi 5. Se ultimi 5 ≥ primi 5, l'ipotesi è falsa su questo mercato.

### H3 — «Trend dei leader» multigiornaliero, solo LONG (candidata per Toro)
Ingresso alla chiusura del giorno *t* se: (i) G acceso; (ii) chiusura > massimo dei 20 giorni precedenti;
(iii) rendimento a 28 giorni nel terzo superiore dell'universo.
Uscita: stop mobile = massima chiusura dall'ingresso − 3 × ATR(20) giornaliero (stop prima di tutto nella candela;
gap → apertura); oppure G spento alla chiusura → uscita all'apertura successiva; oppure 30 giorni.
Massimo 5 posizioni, una per simbolo; a parità di giorno precedenza alla forza relativa più alta.
Controlli: ingressi casuali con stesse uscite (1.000 estrazioni, stessi giorni con G acceso); ablazione senza (iii); ablazione senza G.

### H4 — PROPOSTA ORIGINALE: «Tenuta → Leadership»
**Meccanismo ipotizzato:** nelle giornate di vendita generale la pressione colpisce tutti gli asset in proporzione al
loro beta; un asset che scende meno di quanto il suo beta prevede sta ricevendo acquisti veri. Quando la pressione
del mercato cessa, quell'asset ha meno offerta residua e riparte prima.
**Misura (tenuta):** media, sugli ultimi 30 giorni, del residuo (rendimento asset − beta × rendimento BTC) nei soli
giorni in cui BTC scende; beta = regressione sui 60 giorni precedenti. Servono almeno 8 giorni negativi di BTC nei 30.
- **H4a (cross-sezione, settimanale):** lunedì 00:00 UTC, LONG sui primi 5 per tenuta per una settimana; confronti
  come H2. Previsione: primi 5 > universo > ultimi 5.
- **H4b (strategia a evento «Riconquista»):** *stress* = negli ultimi 10 giorni BTC ha chiuso almeno una volta ≥10%
  sotto la massima chiusura dei 30 giorni precedenti; *innesco* = prima chiusura BTC sopra la massima chiusura dei 5
  giorni precedenti dopo lo stress (un solo innesco per episodio; nuovo episodio solo dopo un nuovo stress).
  All'innesco: LONG all'apertura successiva sui primi 3 per tenuta (tenuta > 0). Uscita: stop mobile 3 × ATR(20);
  oppure BTC chiude sotto la minima chiusura dei 10 giorni precedenti; oppure 14 giorni. Nessun filtro G (è la
  strategia per il recupero, complementare a H3).
  Controlli: BTC stesso agli inneschi; 3 nomi a caso agli inneschi (1.000 estrazioni); gli ULTIMI 3 per tenuta
  (ipotesi concorrente «rimbalzano di più i più venduti»).
**Quando dovrebbe fallire:** falsi inneschi in ribassi che proseguono; tenuta dovuta a illiquidità anziché a domanda.
**Falsificazione:** se gli ultimi per tenuta rendono quanto o più dei primi, o se i primi non battono il caso, è falsa.

### H5 — Specchio SHORT di H3 (solo diagnostica, nessuna proposta: Falco resta invariato)
Rottura del minimo a 20 giorni + terzo inferiore di forza relativa + G spento; stesse uscite speculari.
Serve a misurare l'asimmetria LONG/SHORT a parità di regole.

## Misure per H3 e H4b

Per operazione: rendimento netto in % del nozionale (senza leva), durata, motivo d'uscita, MAE.
Per periodo: n, % vincenti, media netta, profit factor, somma, drawdown.
Continuità: segnali e operazioni a settimana, giorni medi in posizione, occupazione degli slot, intervallo massimo
senza operazioni, quota di tempo con capitale inutilizzato.

## Criteri GO / NO-GO (fissati ora)

Una strategia merita un collaudo SHADOW/PAPER in avanti (mai un'attivazione diretta) solo se TUTTI:
1. operazioni ≥ 100 in totale e ≥ 20 per periodo (H4b, a evento: ≥ 60 e ≥ 10);
2. media netta per operazione > 0 ai costi base in DEV, VAL e TEST;
3. profit factor netto complessivo ≥ 1,20;
4. somma netta superiore al 95% dei controlli casuali;
5. media netta > 0 anche ai costi di stress;
6. nessun simbolo oltre il 40% del profitto totale.
Se anche uno solo fallisce: NO-GO, nessuna nuova taratura sullo stesso campione.
Per H2 e H4a (cross-sezione): differenza primi − universo > 0 in tutti e tre i periodi e t per settimane ≥ 2.
