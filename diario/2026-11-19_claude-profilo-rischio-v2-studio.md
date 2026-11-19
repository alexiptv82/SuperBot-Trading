# Profilo di rischio v2 — studio (SOLO PROPOSTA; nessuna soglia modificata)

Separato dalla P0. Le soglie operative restano quelle attuali (35 % avviso / 50 % stop giornaliero, pavimento 450, rischio per trade, leve 20–50×) fino all'approvazione del proprietario. Le tabelle sono **aritmetica sulle formule di `risk.py`** e sui parametri dell'Arena (equity 2.000, costi 16 bp, manutenzione 0,5 %, buffer di liquidazione 0,5, margine per posizione ≤ 20 %): non sono backtest né rendimenti.

## 1. Il profilo attuale vincola la leva a decidere lo stop
Con leva minima 20× e perdita ≤ 21,4 % del margine:

| Leva | Stop massimo ammesso | Quota dei costi sul rischio |
|---|---|---|
| 50× | 0,27 % | 37 % |
| 40× | 0,38 % | 30 % |
| 30× | 0,55 % | 22 % |
| 20× | 0,91 % | 15 % |

A 50× lo stop sta dentro il rumore e oltre un terzo della perdita sono costi. Ogni setup con stop strutturale oltre 0,91 % è vietato.

## 2. Dimensionamento dal rischio in denaro: la leva diventa un risultato
Procedura: `notional = rischio / (stop + costi)`; leva = la più bassa che tiene il margine entro il tetto (400) e rispetta liquidazione e rapporto perdita/margine; 50× resta il massimo consentito.

| Rischio | Stop | Notional | Leva necessaria | Costi / rischio |
|---|---|---|---|---|
| 1 % (20 USDT) | 0,3 % | 4.348 | 11× | 35 % |
| 1 % | 0,5 % | 3.030 | 8× | 24 % |
| 1 % | 1,0 % | 1.724 | 5× | 14 % |
| 1 % | 2,0 % | 926 | 3× | 7 % |
| 1,5 % (30 USDT) | 0,3 % | 6.522 | 17× | 35 % |
| 1,5 % | 0,5 % | 4.545 | 12× | 24 % |
| 1,5 % | 1,0 % | 2.586 | 7× | 14 % |
| 1,5 % | 2,0 % | 1.389 | 4× | 7 % |

**Conseguenza:** con rischio 1–1,5 % la leva utile sta fra 3× e 17× per stop dello 0,3–2 %. **20–50× restano ammesse, ma servirebbero solo con stop sotto lo 0,3 %**, cioè proprio dove i costi mangiano un terzo del rischio.

## 3. Conflitto con la preferenza storica "size 200–350 a 20–50×"
Margine 350 a 30× = 10.500 di notional. Con stop 0,5 % il rischio è **3,5 % dell'equity**; a 50× è il 5,8 %; con stop 1 % è il 6–10 %. Per stare all'1–1,5 % servirebbero stop di 0,1–0,2 %. Le due regole (margine fisso, rischio fisso) **non convivono**: la decisione del proprietario è dimensionare dal rischio, quindi il margine impiegato diventa un risultato (spesso 100–400, non 350 fisso).

## 4. Proposte (da approvare, ciascuna separata)
1. **Leva minima 1 invece di 20** (massimo 50 invariato): la leva esce da stop, rischio e liquidazione.
2. **Filtro di qualità sui costi:** rifiutare i setup in cui i costi superano il 25 % del rischio (stop < circa 0,5 %), salvo prova di vantaggio netto per quella cella.
3. **Stop minimo legato alla volatilità** (multiplo dell'ATR), così lo stop non cade dentro il rumore.
4. **Limite di perdita di sessione in R** (ipotesi −3 R) come freno operativo; il 50 % resta come limite esterno. Oggi 50 % = 1.000 USDT su 2.000: troppo permissivo (nelle simulazioni sintetiche è il limite stretto di sessione, non il blocco dei profitti, a ridurre le code).
5. **Rischio aggregato per cluster di correlazione** (es. 3 % per cluster) accanto al 12 % totale: con rischio 1–1,5 % il tetto totale consente 8–12 posizioni, spesso correlate.
6. **Costi per simbolo** (spread, slippage misurato) al posto di 16 bp uniformi; slippage di 2 bp è ottimistico per i simboli sottili.
7. **Equity mark-to-market fail-closed** già avviata con #121 e P0; da estendere a dashboard e Guardian.

## 5. Cosa serve per decidere
Dati reali su stop effettivi, costi per simbolo e distribuzione del rischio per trade (E0 e Fase 0, con tuo consenso); ripetere questa tabella con i costi misurati. Nessuna modifica prima.
