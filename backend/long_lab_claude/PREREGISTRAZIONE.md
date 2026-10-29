# Laboratorio "modifica long" (P1) — pre-registrazione

Scritta PRIMA di vedere qualunque risultato (la data del commit lo dimostra). Nessun parametro sotto e' stato
ottimizzato sui dati: i numeri sono quelli gia' presenti nel repository (P1 del 25/10, `desk/regime.py`) oppure sono
fissati qui. Se un criterio e' sbagliato lo si dice nel rapporto, non lo si cambia dopo.

Autore: Claude. Ramo isolato `work/long-lab-claude-20261029`. Nessun bot, nessun deploy, nessun file di produzione toccato.

## Domanda

1. La modifica P1 ("sbias LONG", commit 635b964: trend 4h 20→14, trend 1d 15→10, +10 punti long se RSI 1h < 35 e
   momento 1h > +0,3%) migliora o peggiora il bot del 13/10 (`9fa667f`, quello oggi in funzione)?
2. Se peggiora o e' indistinguibile dal caso: esiste una versione v2, **senza parametri ottimizzati**, che non regredisca
   il bot (short compresi) e che renda i long piu' affidabili?

## Cosa si misura

- **Codice**: le regole VERE del 13/10 (`desk.signals.read_symbol`, `desk.brain.rules_decisions`), il motore VERO
  (`desk.engine.PaperAccount`: commissioni 6 bp/lato, scivolamento 2 bp/lato, funding, liquidazione, stop prima del TP
  dentro la barra). La lettura dei segnali nel laboratorio e' una copia numericamente identica di `read_symbol`,
  verificata barra per barra contro la funzione vera (test `test_equivalenza_base`).
- **Finestra dei dati come in produzione**: ultime 1000 candele 15m → 1h/4h; il trend 1d NON esiste (servono 30 barre
  giornaliere, ma 1000×15m ne danno ~10). Quindi in questo codice la riduzione "1d 15→10" di P1 e' inerte: si misura
  solo 4h 20→14 + rimbalzo.
- **Cadenza**: decisioni ogni 30 minuti, ogni 15 minuti se c'e' una posizione aperta (come `CYCLE_S`/`CYCLE_FAST_S`
  del bot). Stop e TP giudicati su ogni barra 15m.
- **Soglie di ingresso**: come il 13/10: BTC, ETH, XAU, XAG 60; tutti gli altri 70 (`tier_entry_score`). Cooldown
  scalp 10 min, filtro R:R ≥ 1,5, guardrail Hawk (margine < 50$ o leva < 10 → 60$/15x), tetto 100$ a trade, max 10
  posizioni e 1000$ di margine totale. Il conto parte da 100000$ (non si esaurisce mai) con stop giornaliero pari a 120$
  (come il 12% di 1000$); nessun kill-switch.
- **Dati**: candele 15m pubbliche Bitget USDT-futures, 26 simboli di produzione (quelli che hanno storia), ultimi ~540
  giorni (piu' 12 di avviamento). Periodo = intersezione utile per simbolo; ogni simbolo entra quando ha 1000 barre.
- **Stagionalita'**: nel 13/10 e' una funzione della data (mese + fase del ciclo post-halving). Due modi, entrambi
  riportati: (S1) **come in produzione alla data storica**; (S2) **fase di oggi congelata** (da ottobre 2026 la fase e'
  "bear market", moltiplicatore −1,0, che trasforma il bias storico positivo di ott-apr in punti SHORT): e' quello che
  il bot vedra' nei prossimi mesi. Il giudizio principale usa S2 se e solo se S1 e S2 concordano; altrimenti si
  riportano entrambi e si dice che la conclusione dipende dalla stagionalita'.
- **Costi**: base, e sensibilita' con costi ×1,5.

## Varianti (fissate)

| nome | cosa cambia rispetto al 13/10 |
|---|---|
| `base13` | niente (controllo) |
| `p1` | P1 intera: trend 4h 14 (non 20) + 10 punti long su RSI1h<35 e mom1h>+0,3% |
| `p1_w` | solo il peso 4h 14 |
| `p1_reb` | solo il bonus rimbalzo |
| `g_long` | punteggi identici al 13/10, ma un LONG su un'altcoin o BTC/ETH si apre solo se il regime di mercato (`desk.regime`, parametri standard, letto dai punteggi del 13/10) e' "su" o "inversione al rialzo"; short, XAU, XAG invariati |
| `t_bonus` | +10 punti al lato dell'**inversione di mercato confermata** (regime.turn): long se gira al rialzo, short se gira al ribasso; XAU/XAG esclusi; nessun filtro |
| `t_bonus_g` | `t_bonus` + `g_long` |
| `r_reb` | rimbalzo **confermato** (il modo giusto di fare P1), simmetrico: +10 long se RSI1h e' stato < 35 nelle ultime 12 ore, ora e' risalito di almeno 8 punti RSI, il prezzo e' sopra EMA20 1h **e** il mercato sta girando al rialzo (regime.turn = up) o e' rialzista; specchio per gli short (RSI > 65, sceso di 8, sotto EMA20 1h, mercato che gira/e' ribassista) |
| `ref_gate` | riferimento, NON candidato long: il filtro completo di `desk.regime.entry_gate` su entrambi i lati |
| `pl_reb_*` (12) | placebo di `p1_reb`: stesso numero di bonus +10 long, su barre/simboli a caso |
| `pl_shift_*` (12) | placebo di `t_bonus_g`: stessa serie di regime ma spostata di un numero casuale di giorni (5–60): se il beneficio fosse "vero" dovrebbe sparire |

Il regime e' calcolato SEMPRE dai punteggi del 13/10 (non da quelli della variante), cosi' non c'e' circolarita' e in
produzione basterebbe leggerli dove il bot li calcola gia'.

## Criteri di adozione (tutti necessari per dire "v2 non regredisce e migliora i long")

Per una variante V rispetto a `base13`, sullo stesso periodo e gli stessi costi (Δ = netto V − netto base, in $):

- **G1** Δ totale ≥ 0.
- **G2** Δ ≥ 0 in almeno 2 dei 3 terzi del periodo; nel terzo restante Δ ≥ −25% del |netto base| di quel terzo.
- **G3** bootstrap a blocchi di 7 giorni (5000 estrazioni) sulla differenza giornaliera: probabilita' che Δ < 0 ≤ 25%.
- **G4** gli short non peggiorano: netto short V ≥ netto short base − 5% del |netto short base|.
- **G5** attivita': numero di trade entro ±35% di quello della base.
- **G6** rischio: drawdown massimo in $ ≤ 1,15 × quello della base.
- **G7** placebo: Δ di V ≥ al secondo miglior Δ dei 12 placebo della sua famiglia.
- **G8** con costi ×1,5 Δ resta ≥ 0.
- **G9** stesso verso (Δ ≥ 0) sia con la stagionalita' S1 sia con S2.

Per P1 (e le sue meta') si applicano gli stessi criteri: se P1 non li supera, **non va rilasciata**.
Se nessuna variante li supera, il risultato corretto e' "nessuna modifica long da rilasciare: il 13/10 resta com'e'".
Una variante con G1–G9 tutti veri e' solo una **candidata**: il rilascio resta una decisione dell'utente.

## Esperimento sugli eventi (indipendente dal motore)

Per ogni barra di ogni simbolo in cui la condizione di rimbalzo di P1 e' vera, si simula un long con la stessa geometria
del bot (stop 1,2×ATR1h, TP 1,8×stop, massimo 48 ore, stop prima del TP nella stessa barra, costi 16 bp) e si confronta
con: tutte le barre; barre ipervendute senza rimbalzo; la stessa condizione in 4h ribassista vs rialzista; e il
corrispondente short ("vendere il rimbalzo"). Misura in R, per terzo del periodo. Serve a dire se il segnale di P1 ha
un vantaggio proprio, a prescindere da come il bot lo usa.

## Limiti dichiarati (da ripetere nel rapporto)

- Un solo periodo di mercato (~18 mesi) e un solo insieme di simboli: non e' una promessa sul futuro.
- Il laboratorio simula solo le REGOLE (come nel periodo reale 12–26/10, dove Claude non apriva nulla); la fedelta' delle
  singole aperture rispetto ai bot veri e' parziale (misurata in passato: ~15% di aperture sovrapposte, ~85% di uscite
  uguali): conta il confronto tra varianti sullo stesso banco, non il valore assoluto del netto.
- I long reali del 12–26/10 sono solo 13 su 247 aperture: il campione reale e' troppo piccolo per qualunque conclusione.

## Errata e aggiunte (scritte DOPO il primo risultato, dichiarate qui)

1. **Placebo di famiglia sbagliata.** Nella prima esecuzione il controllo G7 per `g_long`, `t_bonus`, `r_reb` e `ref_gate`
   usava i placebo di `t_bonus_g` (che includono sia il bonus sia il filtro). Il criterio resta "il secondo miglior Δ dei
   12 placebo della sua famiglia": ogni variante che legge il regime ha ora i suoi 12 placebo a regime spostato.
   Stessi criteri, nessuna soglia cambiata.
2. **Controlli aggiunti dopo il primo risultato** (non cambiano i criteri, servono a capire): costi zero (lordo),
   soglie +6 per confrontare P1 con "aprire meno", esito per fascia di punteggio, finestre reali di ottobre per
   calibrare la replica, diagnostica del bonus di P1 (quante decisioni cambia).
3. P1 ha un placebo proprio (`pl_p1_*`: peso 4h a 14 + bonus rimbalzo a caso), perche' il suo effetto include il peso.
