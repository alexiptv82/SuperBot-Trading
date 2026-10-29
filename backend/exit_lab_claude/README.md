# Laboratorio uscite/entrate classici (Claude) - 29/10/2026

**Solo PAPER, solo offline, nessuna scrittura su produzione.** Non tocca `backend/desk`, `deploy`, `frontend`, il VPS,
i dati dei bot, ne' il Brain. Branch esclusivo `work/classics-exit-lab-claude-20261029` (base `rule-pool` @ `c1a7c91`).
Il laboratorio di ChatGPT (`work/classics-12oct-selective-lab-20261029`, cartella `backend/rollback_lab`) non e' toccato.

## Domanda
L'utente ipotizza che gli stop siano troppo vicini e propone: stop piu' largo fissato dall'inizio, entrata scaglionata con
margine aggiunto se il prezzo va contro, take profit piu' corto, molti trade chiusi in profitto. Funziona sui dati reali?

## Cosa fa
Prende le **entrate reali** (357 posizioni archiviate di Hawk/Bull, `data/real_entries.csv`, gia' pubbliche nel diario) e le
rigioca su candele **1m reali** di Bitget (endpoint pubblici, nessuna chiave), cambiando solo uscite e, in una famiglia,
il momento d'ingresso. Costi e regole di fill come `engine.py` (fee 6 bp, slippage 2 bp avverso, funding long, liquidazione,
nella stessa candela liquidazione > stop > TP). Permanenza massima 24h uguale per tutte le varianti.

Famiglie (56 varianti): **uscite** (stop x1/1.5/2, TP x0.5/0.75/1/1.5), **due gambe** (seconda gamba a ritracciamento
0.3/0.5/0.75 della distanza stop, stop largo fisso, TP sul prezzo medio, TTL 3h Hawk / 12h Bull), **rimbalzo** (entra solo
dopo un ritracciamento contro il segnale: limite al livello, oppure dopo una barra da 5 minuti che chiude a favore).
Sizing `[S]` = stesso nozionale dell'originale; `[R]` = nozionale ridotto perche' la perdita allo stop resti 1R (il "limite" che
l'utente si dava a mano). Placebo: stesse entrate, lato opposto.

## Regole fissate PRIMA di vedere i risultati
1. **Gate di fedelta'**: sul sottoinsieme SL/TP semplice (nessuna chiusura parziale), la variante base deve riprodurre il tipo
   di uscita reale in >= 85% dei casi e il P&L netto aggregato entro il 10% della somma dei |net| reali. Se NON passa, tutti i
   risultati sono "solo indicativi".
2. **Candidata** solo se: R medio per segnale > 0 dopo costi; estremo inferiore dell'IC95 del delta vs base > 0; delta > 0 in
   almeno 2 fasi su 3 (golden / prima crisi / dopo); i 3 migliori trade pesano < 50% dei guadagni.
3. Si dichiara che sono provate 56 varianti: ~3 sembreranno buone per puro caso. Una candidata va riconfermata su dati nuovi.

## Controlli del banco (candele sintetiche, `--synthetic`, solo impianto)
* **Senza alcun vantaggio** (random walk): 0 candidate su 56; rimbalzo a -0,03 R. Atteso: a parita' di entrate casuali
  il valore atteso e' -costi, qualunque sia la forma di stop/TP.
* **Con vantaggio reale** (deriva a favore del segnale): 6 candidate, tutte uscite che lasciano correre di piu'; il rimbalzo
  peggiora (-0,23 R) perche' con una vera tendenza aspettare un ritracciamento fa perdere il movimento.
* Il gate di fedelta' su percorsi casuali dà ~52% di concordanza: non si supera per caso.
* **Errore trovato e corretto durante questi controlli**: nella famiglia rimbalzo il confronto "per segnale" premiava il solo fare
  meno trade, e quello "sugli stessi segnali eseguiti" regalava ~ +p R alla variante anche senza vantaggio, perche' i segnali in cui il
  prezzo ritraccia contro sono per costruzione quelli in cui l'entrata immediata parte male. Ora il delta e' R medio per trade
  eseguito della variante meno R medio di TUTTI i segnali del base.

## Limiti dichiarati
* Entrate quasi solo SHORT (338 vs 15 LONG): nessuna conclusione sui LONG.
* Periodo 12-26/10, un solo regime di mercato per fase, campione piccolo e correlato tra simboli; l'IC bootstrap a blocchi di 12h e'
  approssimato e probabilmente ottimista.
* Le uscite reali comprendevano chiusure decise da AI/regole, parziali e seconde gamba: qui sostituite da SL/TP/tempo.
* Seconda gamba: ricalcolo del TP sul prezzo medio e TTL del motore sono ipotesi non verificabili sui dati.
* Nessun limite di slot/cassa tra posizioni contemporanee; nessun impatto di mercato.

## Uso
```
python -m unittest -v test_lab_sim                                         # test del simulatore
python fetch_candles.py --entries data/real_entries.csv --out cache        # candele (rete)
python run_lab.py --entries data/real_entries.csv --cache cache --out results
python run_lab.py --entries data/real_entries.csv --synthetic --out /tmp/s # solo impianto
```
Le modifiche a stop, DCA, tipo forzato o prompt dei bot restano **decisione dell'utente** (CLAUDE.md, regola 3) e un deploy
richiede un OK separato (regola 1).
