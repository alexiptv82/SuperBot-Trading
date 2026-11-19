# Profilo di rischio v2 — studio quantitativo (SOLO PROPOSTA; nessuna soglia modificata)

**Revisione del 19/11/2026 sera**, richiesta dal proprietario: distinguere capitale, margine, nozionale, leva, stop, costi, perdita massima e rischio %. Le soglie operative restano quelle attuali fino a tua approvazione. Le tabelle sono **aritmetica** su formule e parametri dichiarati sotto: non sono backtest né previsioni di rendimento.

## Correzione al primo studio
Nel primo studio avevo scritto che 20–50× "servirebbero solo con stop sotto lo 0,3 %". **Era sbagliato**: avevo fissato il margine al tetto di 400 USDT e ricavato la leva minima. Il calcolo corretto è il seguente: **la leva non cambia la perdita allo stop**, cambia solo il margine impegnato e la distanza dalla liquidazione. Con rischio 1–1,5 %, 20–50× sono **matematicamente compatibili**, con margini piccoli (52–278 USDT). Ciò che non è compatibile con un rischio contenuto è "margine fisso 200–350 **e** leva alta" insieme.

## Definizioni e parametri
| Grandezza | Formula / valore |
|---|---|
| Capitale (equity) | 2.000 USDT (PAPER di riferimento) |
| Rischio % | perdita massima prevista allo stop / equity; qui 1 % = 20 USDT e 1,5 % = 30 USDT |
| Costi andata+ritorno `c` | commissioni 0,06 % × 2 + slippage 0,02 % × 2 = **0,16 %** del nozionale (valori della configurazione Arena; lo slippage reale va misurato per simbolo) |
| Nozionale | rischio / (distanza stop + c) |
| Margine | nozionale / leva |
| Perdita max allo stop | nozionale × (stop + c) = **rischio**, qualunque sia la leva |
| Distanza di liquidazione (approssimata) | 1/leva − margine di mantenimento (0,5 %) |
| Ammesso **oggi** | leva ≥ 20, perdita/margine ≤ 21,4 %, margine ≤ 400, stop < ½ × (liquidazione − c) |
| Ammesso **v2 (proposta)** | margine ≤ 400 e stop < ½ × (liquidazione − c); nessun minimo di leva, nessun vincolo perdita/margine |
| Gap 3 % PAPER | nozionale × (3 % + c): il PAPER **non tronca al margine** (`paper_close`: `loss_exceeds_margin`) |
| Gap 3 % reale isolato | min(margine + commissioni, nozionale × (3 % + c)): sull'exchange a margine isolato la liquidazione ferma la perdita al margine |

## Tabella completa
| Rischio (USDT) | Stop | Leva | Nozionale | Margine | Commissioni a/r | Slippage a/r | Perdita max allo stop | Perdita/margine | Distanza liquidazione | Ammesso oggi | Ammesso v2 | Gap 3 % PAPER | Gap 3 % reale isolato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.0 % (20) | 0.20 % | 5× | 5,556 | 1,111 | 6.67 | 2.22 | 20 | 1.8 % | 19.50 % | no | no | 176 | 176 |
| 1.0 % (20) | 0.20 % | 10× | 5,556 | 556 | 6.67 | 2.22 | 20 | 3.6 % | 9.50 % | no | no | 176 | 176 |
| 1.0 % (20) | 0.20 % | 20× | 5,556 | 278 | 6.67 | 2.22 | 20 | 7.2 % | 4.50 % | sì | sì | 176 | 176 |
| 1.0 % (20) | 0.20 % | 30× | 5,556 | 185 | 6.67 | 2.22 | 20 | 10.8 % | 2.83 % | sì | sì | 176 | 176 |
| 1.0 % (20) | 0.20 % | 50× | 5,556 | 111 | 6.67 | 2.22 | 20 | 18.0 % | 1.50 % | sì | sì | 176 | 118 |
| 1.0 % (20) | 0.30 % | 5× | 4,348 | 870 | 5.22 | 1.74 | 20 | 2.3 % | 19.50 % | no | no | 137 | 137 |
| 1.0 % (20) | 0.30 % | 10× | 4,348 | 435 | 5.22 | 1.74 | 20 | 4.6 % | 9.50 % | no | no | 137 | 137 |
| 1.0 % (20) | 0.30 % | 20× | 4,348 | 217 | 5.22 | 1.74 | 20 | 9.2 % | 4.50 % | sì | sì | 137 | 137 |
| 1.0 % (20) | 0.30 % | 30× | 4,348 | 145 | 5.22 | 1.74 | 20 | 13.8 % | 2.83 % | sì | sì | 137 | 137 |
| 1.0 % (20) | 0.30 % | 50× | 4,348 | 87 | 5.22 | 1.74 | 20 | 23.0 % | 1.50 % | no | sì | 137 | 92 |
| 1.0 % (20) | 0.50 % | 5× | 3,030 | 606 | 3.64 | 1.21 | 20 | 3.3 % | 19.50 % | no | no | 96 | 96 |
| 1.0 % (20) | 0.50 % | 10× | 3,030 | 303 | 3.64 | 1.21 | 20 | 6.6 % | 9.50 % | no | sì | 96 | 96 |
| 1.0 % (20) | 0.50 % | 20× | 3,030 | 152 | 3.64 | 1.21 | 20 | 13.2 % | 4.50 % | sì | sì | 96 | 96 |
| 1.0 % (20) | 0.50 % | 30× | 3,030 | 101 | 3.64 | 1.21 | 20 | 19.8 % | 2.83 % | sì | sì | 96 | 96 |
| 1.0 % (20) | 0.50 % | 50× | 3,030 | 61 | 3.64 | 1.21 | 20 | 33.0 % | 1.50 % | no | sì | 96 | 64 |
| 1.0 % (20) | 1.00 % | 5× | 1,724 | 345 | 2.07 | 0.69 | 20 | 5.8 % | 19.50 % | no | sì | 54 | 54 |
| 1.0 % (20) | 1.00 % | 10× | 1,724 | 172 | 2.07 | 0.69 | 20 | 11.6 % | 9.50 % | no | sì | 54 | 54 |
| 1.0 % (20) | 1.00 % | 20× | 1,724 | 86 | 2.07 | 0.69 | 20 | 23.2 % | 4.50 % | no | sì | 54 | 54 |
| 1.0 % (20) | 1.00 % | 30× | 1,724 | 57 | 2.07 | 0.69 | 20 | 34.8 % | 2.83 % | no | sì | 54 | 54 |
| 1.0 % (20) | 1.00 % | 50× | 1,724 | 34 | 2.07 | 0.69 | 20 | 58.0 % | 1.50 % | no | no | 54 | 37 |
| 1.0 % (20) | 2.00 % | 5× | 926 | 185 | 1.11 | 0.37 | 20 | 10.8 % | 19.50 % | no | sì | 29 | 29 |
| 1.0 % (20) | 2.00 % | 10× | 926 | 93 | 1.11 | 0.37 | 20 | 21.6 % | 9.50 % | no | sì | 29 | 29 |
| 1.0 % (20) | 2.00 % | 20× | 926 | 46 | 1.11 | 0.37 | 20 | 43.2 % | 4.50 % | no | sì | 29 | 29 |
| 1.0 % (20) | 2.00 % | 30× | 926 | 31 | 1.11 | 0.37 | 20 | 64.8 % | 2.83 % | no | no | 29 | 29 |
| 1.0 % (20) | 2.00 % | 50× | 926 | 19 | 1.11 | 0.37 | 20 | 108.0 % | 1.50 % | no | no | 29 | 20 |
| 1.5 % (30) | 0.20 % | 5× | 8,333 | 1,667 | 10.00 | 3.33 | 30 | 1.8 % | 19.50 % | no | no | 263 | 263 |
| 1.5 % (30) | 0.20 % | 10× | 8,333 | 833 | 10.00 | 3.33 | 30 | 3.6 % | 9.50 % | no | no | 263 | 263 |
| 1.5 % (30) | 0.20 % | 20× | 8,333 | 417 | 10.00 | 3.33 | 30 | 7.2 % | 4.50 % | no | no | 263 | 263 |
| 1.5 % (30) | 0.20 % | 30× | 8,333 | 278 | 10.00 | 3.33 | 30 | 10.8 % | 2.83 % | sì | sì | 263 | 263 |
| 1.5 % (30) | 0.20 % | 50× | 8,333 | 167 | 10.00 | 3.33 | 30 | 18.0 % | 1.50 % | sì | sì | 263 | 177 |
| 1.5 % (30) | 0.30 % | 5× | 6,522 | 1,304 | 7.83 | 2.61 | 30 | 2.3 % | 19.50 % | no | no | 206 | 206 |
| 1.5 % (30) | 0.30 % | 10× | 6,522 | 652 | 7.83 | 2.61 | 30 | 4.6 % | 9.50 % | no | no | 206 | 206 |
| 1.5 % (30) | 0.30 % | 20× | 6,522 | 326 | 7.83 | 2.61 | 30 | 9.2 % | 4.50 % | sì | sì | 206 | 206 |
| 1.5 % (30) | 0.30 % | 30× | 6,522 | 217 | 7.83 | 2.61 | 30 | 13.8 % | 2.83 % | sì | sì | 206 | 206 |
| 1.5 % (30) | 0.30 % | 50× | 6,522 | 130 | 7.83 | 2.61 | 30 | 23.0 % | 1.50 % | no | sì | 206 | 138 |
| 1.5 % (30) | 0.50 % | 5× | 4,545 | 909 | 5.45 | 1.82 | 30 | 3.3 % | 19.50 % | no | no | 144 | 144 |
| 1.5 % (30) | 0.50 % | 10× | 4,545 | 455 | 5.45 | 1.82 | 30 | 6.6 % | 9.50 % | no | no | 144 | 144 |
| 1.5 % (30) | 0.50 % | 20× | 4,545 | 227 | 5.45 | 1.82 | 30 | 13.2 % | 4.50 % | sì | sì | 144 | 144 |
| 1.5 % (30) | 0.50 % | 30× | 4,545 | 152 | 5.45 | 1.82 | 30 | 19.8 % | 2.83 % | sì | sì | 144 | 144 |
| 1.5 % (30) | 0.50 % | 50× | 4,545 | 91 | 5.45 | 1.82 | 30 | 33.0 % | 1.50 % | no | sì | 144 | 96 |
| 1.5 % (30) | 1.00 % | 5× | 2,586 | 517 | 3.10 | 1.03 | 30 | 5.8 % | 19.50 % | no | no | 82 | 82 |
| 1.5 % (30) | 1.00 % | 10× | 2,586 | 259 | 3.10 | 1.03 | 30 | 11.6 % | 9.50 % | no | sì | 82 | 82 |
| 1.5 % (30) | 1.00 % | 20× | 2,586 | 129 | 3.10 | 1.03 | 30 | 23.2 % | 4.50 % | no | sì | 82 | 82 |
| 1.5 % (30) | 1.00 % | 30× | 2,586 | 86 | 3.10 | 1.03 | 30 | 34.8 % | 2.83 % | no | sì | 82 | 82 |
| 1.5 % (30) | 1.00 % | 50× | 2,586 | 52 | 3.10 | 1.03 | 30 | 58.0 % | 1.50 % | no | no | 82 | 55 |
| 1.5 % (30) | 2.00 % | 5× | 1,389 | 278 | 1.67 | 0.56 | 30 | 10.8 % | 19.50 % | no | sì | 44 | 44 |
| 1.5 % (30) | 2.00 % | 10× | 1,389 | 139 | 1.67 | 0.56 | 30 | 21.6 % | 9.50 % | no | sì | 44 | 44 |
| 1.5 % (30) | 2.00 % | 20× | 1,389 | 69 | 1.67 | 0.56 | 30 | 43.2 % | 4.50 % | no | sì | 44 | 44 |
| 1.5 % (30) | 2.00 % | 30× | 1,389 | 46 | 1.67 | 0.56 | 30 | 64.8 % | 2.83 % | no | no | 44 | 44 |
| 1.5 % (30) | 2.00 % | 50× | 1,389 | 28 | 1.67 | 0.56 | 30 | 108.0 % | 1.50 % | no | no | 44 | 29 |

## Cosa dicono i numeri
1. **Perdita allo stop = rischio scelto** in ogni riga. La leva non la cambia.
2. **20–50× sono compatibili con rischio contenuto** per stop fino a ~0,5–0,7 % (a 50× il vincolo di liquidazione ammette stop fino a 0,67 %): margine 52–278 USDT.
3. **Il vincolo che oggi blocca davvero** è perdita/margine ≤ 21,4 % (pensato per 75 USDT su 350 di margine). Vieta per esempio 50× con stop 0,5 % e 20× con stop 1 %, combinazioni con rischio identico ad altre ammesse. La leva minima 20× vieta invece 5–10×, che servono a stop larghi.
4. **Stop stretti richiedono leva**: con stop 0,2 % e rischio 1 % il nozionale è 5.556 e a 5× o 10× il margine (1.111 / 556) supera il tetto di 400; servono almeno 14×.
5. **I costi non dipendono dalla leva** ma dallo stop: commissioni + slippage valgono il 44 % del rischio con stop 0,2 %, il 24 % con 0,5 %, il 14 % con 1 %. È questo, non la leva, il vero limite dello scalp stretto.
6. **Gap:** in reale, con margine isolato, più leva = margine più piccolo = perdita da gap limitata al margine (a 50× con stop 0,5 %: 64 USDT invece di 96). **Il PAPER non lo simula** e mostra la perdita piena: per le leve alte il PAPER è prudente sui gap, ma non riproduce la liquidazione. Il rovescio della medaglia: a 50× la liquidazione dista ~1,5 %, quindi uno spike oltre stop e buffer chiude con perdita pari al margine.

## Proposta quantitativa v2 (da approvare punto per punto)
| # | Proposta | Effetto |
|---|---|---|
| 1 | **Dimensionamento dal rischio:** nozionale = rischio / (stop + costi del simbolo) | perdita allo stop sempre = rischio approvato |
| 2 | **Leva = risultato:** tra la minima che rispetta il tetto di margine e la massima che tiene lo stop entro metà della distanza di liquidazione (meno i costi); tetto 50× invariato. Scelta suggerita: la più alta ammessa, per ridurre margine impegnato e perdita da gap reale | 20–50× restano possibili quando il rischio lo consente, mai imposti |
| 3 | Leva minima da 20 a 1; vincolo perdita/margine 21,4 % sostituito dal vincolo di liquidazione | sblocca stop strutturali più larghi |
| 4 | **Filtro costi:** rifiutare setup con costi > 25 % del rischio (stop sotto ~0,5 % con c = 0,16 %), salvo vantaggio netto misurato per quella cella | evita trade dominati dai costi |
| 5 | Stop minimo legato alla volatilità (multiplo dell'ATR del timeframe d'ingresso) | stop fuori dal rumore |
| 6 | Rischio per trade 1–1,5 % (decisione provvisoria già tua) | — |
| 7 | Rischio aggregato: 12 % totale + tetto per cluster di correlazione (es. 3 %) | con 1–1,5 % il 12 % consente 8–12 posizioni, spesso correlate |
| 8 | Limite di sessione in R (ipotesi −3 R) come freno operativo; 35 %/50 % come limiti esterni | freno coerente con la dimensione dei trade |
| 9 | Costi per simbolo (spread e slippage misurati) invece di 16 bp uniformi | stime oneste sui simboli sottili |
| 10 | **Decisione di modello per il PAPER:** simulare o no la liquidazione al margine | oggi PAPER e reale divergono sui gap |

## Prima di decidere
Misurare su dati reali (Fase 0 ed E0, con tuo consenso): distribuzione degli stop usati, costi effettivi per simbolo, frequenza e ampiezza dei gap, rischio per trade effettivamente corso. Poi ripetere questa tabella con quei valori. Nessuna modifica prima.
