# Pre-registrazione — Lettore di regime v2 (Claude, 30/10/2026)

Scritta **prima** di eseguire il laboratorio sul lettore v2. Parametri, criteri e analisi qui sotto sono congelati: se
dopo i risultati qualcosa cambia, si scrive come **errata** in fondo, con data e motivo, e il risultato originale resta
nel rapporto. Offline: nessun bot, deploy o file di produzione toccato (ramo isolato, mai unito a `rule-pool`).

## Perche' esiste

Osservazione dell'utente (30/10): gli short dei classici vanno bene quando il mercato scende in modo regolare e vanno in
difficolta' quando il mercato non ha direzione o la cambia. Misura gia' disponibile (replica base13 del 13/10, 540 giorni,
5045 trade): gli short aperti col regime *esistente* `desk.regime` = "giu'" fanno −0,131 R a trade (n = 2274), positivi
in soli 4 mesi su 18 (i 3 mesi migliori +84 R, gli altri 15 mesi −381 R). Quindi l'etichetta "ribasso" attuale **non
distingue** il ribasso buono dal ribasso cattivo. Domanda: un lettore che separa *direzione*, *qualita' del movimento*
(pulito / a scatti) e *volatilita' anomala* fa meglio, in modo simmetrico per long e short?

## Il lettore v2 (`regime_v2.py`, profilo `classic15`) — parametri CONGELATI

Tutti ipotesi iniziali, **non ottimizzati**. Per ogni timeframe (15m, 1h, 4h; aggregati dalle barre 15m, solo barre
complete e chiuse) su barre chiuse: A = media semplice di 14 true range; poi

- M = clip((C[t]−C[t−3]) / (2·A)); B = Σ(C−O)/Σ(H−L) sulle ultime 3 barre; S = +1/−1 se C[t] supera il massimo/minimo
  delle 6 barre precedenti; Q = media su 3 barre di (2C−H−L)/(H−L); X = struttura minimi/massimi (minimi recenti contro
  precedenti, massimi precedenti contro recenti, in unita' di A, finestra 6+6).
- F = 0,35·M + 0,20·B + 0,15·S + 0,10·Q + 0,20·X, in [−1, +1].
- ER = |C[t]−C[t−24]| / Σ|ΔC| su 24 barre 1h (qualita' del movimento, 0 = a scatti, 1 = rettilineo).
- VR = A_15m / media di A_15m sulle 288 barre precedenti (volatilita' anomala).
- D = 0,60·F_15m + 0,40·F_1h (il presente); K = F_4h (il movimento ampio); dD = D[t] − D[t−4].

Stato grezzo (ordine): VR ≥ 2,5 → SHOCK. Poi direzione di contesto kdir = −1 se K ≤ −0,25, +1 se K ≥ +0,25, altrimenti 0.
kdir = −1: se D ≥ +0,20 o dD ≥ +0,30 → TURNING_UP; altrimenti ER ≥ 0,30 → DOWN_CLEAN, ER < 0,30 → DOWN_CHOP.
kdir = +1: specchio (TURNING_DOWN, UP_CLEAN, UP_CHOP). kdir = 0: se |D| ≥ 0,35 e ER ≥ 0,30 → EMERGING_UP/DOWN, altrimenti RANGE.
Conferma: lo stato cambia solo dopo 2 chiusure consecutive uguali (SHOCK subito). Nessuno stato e' un veto.

Classe per lato (specchio per costruzione): ALIGNED per SHORT = {DOWN_CLEAN, EMERGING_DOWN}, per LONG = {UP_CLEAN, EMERGING_UP};
OPPOSED per SHORT = {UP_CLEAN, UP_CHOP, EMERGING_UP, TURNING_UP}, per LONG = {DOWN_CLEAN, DOWN_CHOP, EMERGING_DOWN, TURNING_DOWN};
tutto il resto NEUTRAL (RANGE, SHOCK, *_CHOP e TURNING nel verso del lato, NA).

Livello **simbolo**: lo stato del simbolo. Livello **mercato**: stessa macchina sulle mediane di K, D, ER, VR dei simboli cripto
(esclusi XAU/XAG). Tre sorgenti di classe: mercato (primaria), simbolo (secondaria), combinata = ALIGNED solo se entrambe
ALIGNED, OPPOSED se almeno una OPPOSED (terziaria). La barra usata per un trade aperto a `open_ms` e' l'ultima con
chiusura ≤ `open_ms` (causale; test).

## Dati e analisi

- Trade: i 5045 (S1) e 5084 (S2) della replica base13 del 13/10 (stagionalita' S1 storica, S2 fase di oggi congelata) del
  laboratorio `long_lab_claude` (copiati in `inputs/`, non rigenerati). Candele 15m pubbliche Bitget, 540 giorni, 27 simboli.
  Primaria S2 se S1 e S2 concordano, altrimenti si riportano entrambe. XAU/XAG esclusi dalla classe di mercato.
- Politiche (identiche e simmetriche per long e short, applicate ai trade gia' simulati, nessun nuovo trade inventato):
  **G_A** tieni solo ALIGNED; **G_N** tieni ALIGNED + NEUTRAL, scarta OPPOSED; **S_W** peso 1 / 0,5 / 0,25 per ALIGNED / NEUTRAL / OPPOSED.
- Lezione dal laboratorio long: quando ogni trade perde in media, "aprire meno" migliora il netto da solo. Per questo il
  criterio non e' il netto totale ma la **discriminazione**: δ = R medio dei trade tenuti − R medio degli scartati (per S_W:
  R pesato − R base), con bootstrap a blocchi di 7 giorni (5000 estrazioni), e il confronto con placebo.
- Placebo: la serie di classi spostata in modo circolare di k giorni (k da 5 a 60), 200 estrazioni, stessa politica.

## Cancelli

**Sanita' (prima di guardare gli esiti dei trade; se falliscono: "lettore degenere", nessun giudizio sui trade)**
- S0a nessuno stato di mercato occupa piu' del 60% delle barre. S0b per ogni lato la classe ALIGNED contiene tra l'8% e il 60% dei
  trade. S0c test unitari verdi (specchio esatto, causalita', equivalenza batch/vivo, isteresi, dati mancanti).

**S0d (aggiunto con E2, prima del dato reale)** stabilita': la durata mediana di uno stato di mercato e' almeno 8 barre 15m (2 ore).

**Riconoscimento della svolta (BTC e ETH, 15m)** — svolte benchmark fissate ex post: massimo/minimo dei close 1h su ±24 barre
seguito (e preceduto) da un movimento ≥ 4·ATR(1h) entro 24 barre. Direzione del lettore: −1/+1 se lo stato e' *_DOWN o TURNING_DOWN /
*_UP o TURNING_UP, 0 altrimenti; confronto con EMA20/EMA50 a 1h (segno). Una svolta e' "rilevata" alla prima barra ≥ (svolta − 16 barre
15m) in cui la direzione nuova dura ≥ 8 barre; ritardo = quella barra − svolta (puo' essere negativo).
- **D1** ritardo mediano di v2 ≤ 50% di quello EMA20/50 sulle svolte rilevate da entrambi entro 96 barre.
- **D2** non solo piu' rapido: quota di cambi di direzione seguiti entro 96 barre da un movimento ≥ 2·ATR(1h) nel verso nuovo, v2 ≥ EMA − 10 punti
  percentuali, e cambi per settimana di v2 ≤ 3 volte quelli EMA.

**Politiche** — per ogni politica e sorgente di classe (primaria: soglia P ≤ 10%; secondaria e terziaria: P ≤ 3,3%, correzione per 3 famiglie):
- **R1** δ > 0 con P(δ ≤ 0) sotto soglia. **R2** δ > 0 in almeno 2 terzi cronologici su 3 e in nessuno δ < −0,15 R.
- **R3** δ osservato ≥ 95° percentile dei 200 placebo. **R4** attivita': G_A tiene ≥ 25% dei trade base, G_N ≥ 50%.
- **R5** R1 e R3 veri sia in S1 sia in S2. **R6** δ > 0 sia per gli short sia per i long presi da soli (un lettore che aiuta un lato solo non e' simmetrico).
- **R7 (economia, informativo)** R netto medio dei trade tenuti ≥ 0 anche con +0,08 R a trade di stress costi (≈ costi ×1,5; approssimazione dichiarata).
  R1–R6 veri e R7 falso = "discrimina ma non basta da solo a rendere positivo base13".

**Specchio (descrittivo, nessun cancello)**: R di SHORT in ALIGNED contro R di LONG in ALIGNED, per sorgente e scenario: dice se il lato long di base13
funziona quanto lo short *quando il regime lo sostiene* (se no, un lettore simmetrico non puo' pareggiare i lati: serve un motore long diverso).

## Cosa NON significa

Una politica con R1–R6 veri e' solo una **candidata**: rilascio, modifica di soglie/stop/dimensione o uso nei bot restano decisioni dell'utente
con nuovo OK e redeploy. Il profilo `scalp1m` (1m/5m/15m/1h/4h, per il Brain) **non e' validato** da questo laboratorio (mancano dati 1m).

## Limiti dichiarati

La replica sottostima i giorni d'oro (R +0,06 contro +0,54 reali, 12–15/10): i valori assoluti sono pessimisti, i confronti tra
politiche sullo stesso banco restano validi. Un solo periodo di mercato; i trade sono correlati (per questo blocchi di 7 giorni);
costi approssimati nello stress R7; i trade del banco sono quelli di base13 e non rispondono al regime (nessuna riapertura simulata).

## Registro di varianti provate e errata

- **E1 (30/10/2026, PRIMA di ogni esecuzione su dati reali; trovata con la prova su dati finti, non su esiti dei trade).** Il mio cancello D2
  era mal calibrato: confrontare i cambi di direzione di un rilevatore rapido con quelli di un'EMA lenta (ordine di 20 al giorno contro 0,5 a
  settimana su dati finti) non ha senso, e una "quota di cambi confermati" senza tasso di base premia un rilevatore nervoso. Sostituzioni, tutte
  scritte prima del primo dato reale e senza toccare nessun parametro del lettore: **D2** = lift dei cambi confermati (quota con movimento favorevole >= 2 ATR(1h)
  entro 96 barre, divisa per il tasso di base di quel movimento su tutte le barre) >= 1,15 **e** cambi di direzione <= 2 al giorno; **D3 (nuovo)** =
  la quota di svolte vere rilevate dal lettore supera il 95° percentile della stessa quota con le svolte spostate a caso di 5-60 giorni (100 placebo):
  senza D3 un lettore che cambia direzione spesso "rileva" tutto. Aggiunta la durata mediana di uno stato come misura descrittiva (nessun cancello).
  D1 invariato. Il lettore (parametri, stati, classi) e' invariato rispetto alla firma.
- **E2 (30/10/2026, PRIMA di ogni esecuzione su dati reali) - fasi e correzioni ammesse.** Il laboratorio ha due fasi. **Struttura**: occupazione degli stati
  (S0a), quota ALIGNED usando solo istanti e lati dei trade (S0b), stabilita' (S0d), cancelli D1-D3; non legge mai i rendimenti dei trade.
  **Completa**: trade, politiche, specchio. Se la fase struttura non e' accettata (tutti S0a, S0b, S0d, D1, D2, D3 veri), e' ammessa **al
  piu' una** configurazione corretta v2.1 che cambi SOLO soglie, pesi, lunghezza dell'isteresi o finestre del lettore, scelta guardando
  **solo** le metriche strutturali, scritta qui (valori vecchi e nuovi, motivo) prima della fase completa; la fase completa gira **una volta** sulla
  configurazione congelata. Il numero di iterazioni strutturali e' riportato nel rapporto. Se anche v2.1 non e' accettata, il rapporto dichiara
  il lettore non idoneo e si ferma: nessuna terza iterazione, nessuna lettura dei rendimenti per scegliere.

