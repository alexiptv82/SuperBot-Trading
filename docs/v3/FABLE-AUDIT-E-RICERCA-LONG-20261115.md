# SuperBot V3 — audit indipendente e ricerca LONG (Fable, 15 novembre 2026)

Solo PAPER. Nessun deploy, merge, riavvio, ordine, chiusura o modifica di parametri è stato eseguito.
Etichette: **VERIFICATO** (provato qui con codice o dati), **IPOTESI**, **NON VERIFICATO**, **CORREZIONE PROPOSTA**.

Rami di questo lavoro (nessuna PR aperta):
- `work/brain-manual-close-ro-fix-20261115` — correzione del pulsante «Chiudi» e test.
- `work/long-research-fable-20261115` — preregistrazione, laboratorio, risultati, script di audit, questo rapporto.

---

## A — Bug della chiusura manuale Brain

**Causa (VERIFICATO in locale, NON VERIFICATO sulla VPS).**
La dashboard pubblica gira in un container che monta le cartelle delle run in **sola lettura** (lo impone lo script
di pubblicazione `rc84-publish-single-close-only-paper.py`). Per decidere se mostrare «Chiudi» attivo, il backend web
calcola `_brain_single_close_ready` → `exit_service_healthy` → `_active_lease_token`, che apre `.exit_service.lock`
con `O_RDWR`. Su un mount in sola lettura l'apertura fallisce (EROFS), quindi il servizio uscite risulta sempre
"non sano" e i campi `brain_single_close_allowed` / `manual_close_allowed` restano `false`.
Il frontend disegna il pulsante ma con `disabled`, **senza cambiarne l'aspetto**: sembra attivo e non fa nulla.

**Prove.** Riproduzione su un vero bind mount read-only: cartella RW → sano `True`; stessa cartella vista RO → `False`.
Il resto della catena funziona: richiesta accodata dal bridge → sidecar chiude (`reason=manual`) → journal →
`close_result.json` letto dal web → posizione sparita; doppia richiesta respinta; richiesta ripetuta su posizione
chiusa respinta (idempotenza).

**Perché Falco/Toro non hanno il problema.** Per i classici il permesso dipende solo da variabili d'ambiente
(`classic_single_close_enabled`), senza leggere il lease.

**Perché non è emerso al rilascio dell'11/11.** Il collaudo provò solo i rifiuti senza posizioni reali, e in quel
momento la run Brain non aveva ancora un servizio uscite attivo.

**CORREZIONE PROPOSTA** (commit `89f8da7f`): apertura del lock in sola lettura (`flock` non richiede scrittura).
Una riga in `backend/v3/runner/exit_service.py`. Test: 5 nuovi (vista RO simulata, vero mount RO, senza
proprietario, heartbeat vecchio, catena completa) — 2 falliscono sul codice attuale e passano dopo; 207 regressioni
di uscite/bridge/runner superate. Frontend (non eseguibile qui, mancano le dipendenze Node): pulsante disattivato
riconoscibile e motivo del rifiuto mostrato invece di «Invio non riuscito».
Installazione: serve ricostruire l'immagine web — **solo con autorizzazione**; i servizi Brain non vanno toccati.

**Altri rischi sulla stessa catena.**
- IPOTESI: dopo la patch P0, `last_minute_close` pretende la candela del minuto appena chiuso; nei primi secondi di
  ogni minuto Bitget può non averla ancora → chiusura respinta con «prezzo non disponibile, riprova».
- VERIFICATO: i codici `servizio_uscita_non_pronto`, `bridge_non_disponibile`, `solo_lettura` non erano tradotti.

**Conferma sulla VPS:** lo script `deploy/scripts/v3-brain-audit-readonly-20261115.sh` stampa
`chiusura_brain_consentita_vista_dal_web` e `lock_O_RDWR=ERRORE_EROFS` se la diagnosi è giusta.

---

## B — Prestazioni di Brain

**Fonte dei numeri di Brain: RIPORTATI nella issue #95 da schermate Termius (13–15/11), non riestratti da me.**
Il journal è sulla VPS; lo script di audit serve a rimisurarli in modo completo e aggiornato.

| | Operazioni | Vincenti | PnL netto |
|---|---|---|---|
| SHORT | 11 | 7 | circa +217 USDT |
| LONG | 2 | 0 | circa −137 USDT |
| Totale | 13 | 7 | circa +80 USDT |

Altri fatti riportati: tutte le posizioni a leva 20×; stop fra 0,40% e 0,87% dal prezzo; nelle prime 6 chiusure
lordo −5,7 USDT e commissioni 50,7 USDT (8–9,5 USDT a operazione); 62 decisioni di cui 30 NO_TRADE del modello,
16 respinte dal rischio, 15 approvate ma solo 6 aperte davvero.

**Controllo oggettivo (VERIFICATO, candele reali Bitget a 1 minuto, `results/brain_window_baseline.json`).**
Nella finestra 13/11 14:00 → 15/11 06:00 UTC gli 8 simboli di Brain sono scesi in media del **10,0%**
(BTC −7,4%, SOL −13,2%, ADA −13,8%). Ho simulato un ingresso a OGNI ora su ogni simbolo con le regole di uscita di
Brain (stop fisso, obiettivo 2R, 24 ore, 6 bp per lato, 2 bp di slippage):

| Stop | SHORT a caso: vincenti | SHORT: media | LONG a caso: vincenti | LONG: media |
|---|---|---|---|---|
| 0,50% | 62,8% | +31 bp | 16,2% | −39 bp |
| 0,75% | 71,0% | +72 bp (≈ +51 USDT su 7.000) | 8,2% | −70 bp (≈ −49 USDT) |
| 0,90% | 70,0% | +87 bp | 6,1% | −87 bp |

Brain ha vinto 7 SHORT su 11 (64%) con circa +20 USDT medi: **meno di SHORT aperti a caso** nella stessa finestra.
I due LONG persi rientrano nel 92% di LONG perdenti di quelle ore. Il risultato positivo è spiegato dalla discesa del
mercato; non è una prova di abilità né di apprendimento di DeepSeek. Limiti del confronto: 13 operazioni, dati da
schermate, Brain non può aprire ogni ora su tutti i simboli (limiti di margine) ed è stato in pausa alcune ore.

IPOTESI dalle prime 6 chiusure: la dimensione è decisa dal tetto di margine (nozionale quasi costante) e non dal
rischio, quindi le perdite crescono con la distanza dello stop (stop larghi −77/−83 USDT) mentre le vincite a stop
stretto valgono +48/+73 USDT: servono circa il 57% di vincenti per pareggiare, invece del 40% teorico di un 2R.

**VERIFICATO dal codice installato:**
1. Con leva 20–50× e perdita massima 21,43% del margine, lo stop di **ogni** posizione Brain deve stare entro
   **0,91%** dal prezzo a 20× (0,27% a 50×). È dentro il rumore orario delle crypto.
2. Il PnL PAPER non contabilizza il funding.
3. Le proposte respinte dal rischio vengono scritte nel journal **senza lato, leva, stop e motivo specifico**
   (`NO_TRADE / RISK_REJECTED / risk_rejected`): oggi non si può sapere quanti LONG proposti da DeepSeek sono stati
   scartati né perché. Lo stesso vale per le 9 approvazioni non aperte. È la prima lacuna da colmare.

---

## C — Perché gli SHORT vanno meglio

**Risposta breve: per il regime di mercato, non per l'abilità del segnale.** (VERIFICATO sui dati sotto.)

Dati: 453 perpetual crypto Bitget, candele giornaliere 2020-01-01 → 2026-11-14, universo "a quella data" (primi 30
per volume), 0 buchi, 0 candele invalide.

| Rendimento medio giornaliero dell'universo | BTC sopra la media a 100 giorni | BTC sotto |
|---|---|---|
| Tutto il periodo | +27 bp | −9 bp |
| Luglio 2025 → novembre 2026 | 0 bp (205 giorni) | **−23 bp** (297 giorni) |

Negli ultimi 16 mesi il mercato è stato "sotto" per il 59% dei giorni, e in quei giorni le altcoin hanno perso in
media lo 0,23% al giorno. Qualunque SHORT ha avuto il vento a favore, qualunque LONG contro.

- Specchio SHORT del trend (H5: rottura dei minimi a 20 giorni, solo con BTC sotto la media): +1,98% per operazione,
  ma **SHORT su simboli a caso negli stessi giorni fanno +2,16%**: il segnale non aggiunge nulla alla deriva.
- "I deboli continuano a scendere": gli ultimi 5 per forza relativa hanno fatto −3,0% a settimana nel periodo recente.
- Laboratori precedenti (29/10, 26 simboli, 18 mesi): il punteggio dei classici ha vantaggio lordo ≈ 0 (R −0,004);
  replay di questa sessione, sole regole su BTC/ETH/SOL: Falco SHORT lordo +261, netto −577 dopo le commissioni.

Le dieci domande:
1–2. Migliori per il regime ribassista; la strategia SHORT a regole non batte SHORT casuali.
3–4. Non c'è prova che gli SHORT "vedano prima"; i LONG non sono in ritardo, sono contro deriva.
5. I filtri LONG non sono troppo stretti: allentarli (prove P1, gemello, mirror) ha solo aumentato le perdite.
6. Sì per Brain: stop ≤ 0,91% è incompatibile con qualunque LONG che non sia uno scalp.
7. La leva non crea la perdita ma la moltiplica: a leva ~20× i costi valgono ~3% del margine per operazione.
8. NON VERIFICATO (serve il journal); è plausibile e corretto che DeepSeek segua il trend superiore.
9. NON VERIFICABILE oggi: i rifiuti non registrano il lato (vedi B.3).
10. Sì: ciò che paga gli SHORT è stare dal lato della deriva. L'equivalente LONG è operare solo quando la deriva è positiva.

**Avvertenza:** i risultati SHORT recenti di Brain e Falco non dimostrano un vantaggio che sopravviva a un cambio di
regime. Per Brain il confronto diretto è nella sezione B: nella sua finestra SHORT casuali hanno fatto meglio.

---

## D — Diagnosi della debolezza LONG

1. **Regime (VERIFICATO).** Con BTC sotto la media a 100 giorni nessuna tecnica d'ingresso LONG provata, qui o prima, è positiva.
2. **Orizzonte e costi (VERIFICATO).** Sugli orizzonti intraday il vantaggio lordo LONG è zero e i costi (~16 bp a giro)
   decidono il segno: mirror 15m, gemello, BB100, Supertrend, punteggio classico.
3. **Stop (VERIFICATO per Brain).** Vedi B.1.
4. **Rimbalzi (VERIFICATO).** Ogni forma di "compra il rimbalzo" è stata bocciata: P1, Bollinger, bounce del mirror,
   e ora «Riconquista» (H4b).
5. **Gestione delle uscite (VERIFICATO).** L'unica famiglia LONG con aspettativa positiva (H3) vince solo il 38% delle
   volte e guadagna dalle poche operazioni lasciate correre: take profit ravvicinati la distruggerebbero.

---

## E — Strategie LONG: già provate e nuove

### Inventario di ciò che era già stato provato (verificato su codice e rapporti)

| Famiglia | Dove | Dati | Esito |
|---|---|---|---|
| Punteggio classico lato LONG | long-lab, edge-lab 29/10 | 26 simboli, 18 mesi, 15m | lordo ≈ 0 |
| Bonus rimbalzo (P1), filtri di regime | long-lab | idem | nessuno batte il caso |
| Bollinger mean reversion, pullback, squeeze | laboratorio 9/10 | BTC/ETH dal 2019 | lordo negativo o ≈ 0 |
| Donchian 4h/1h/giornaliero | laboratorio 9/10, ampiezza (53 coppie) | dal 2020 | non superano i criteri (risultati numerici non presenti nel repository) |
| Momentum/reversal settimanale neutrale | crosssec-lab | 53 coppie | risultati non presenti nel repository |
| Carry sul funding | funding-lab; PR #97/#98 | proxy Binance | proxy non valido; strategia mai testata |
| LONG mirror 15m | PR #93 | BTC/ETH/SOL 18 mesi | FAIL |
| Toro gemello | PR #94 | idem | NO-GO strategico |
| Toro BB100 «Profit Hunter» | PR #96 | 5 mercati, 365 giorni | NO-GO |
| Supertrend 15m/1h | PR #99 | 5 mercati, 365 giorni | NO-GO (−32 bp, PF 0,59) |

Mai provati prima: selezione per forza relativa solo LONG, trend multigiornaliero con filtro di mercato, tenuta nei ribassi.

### Ipotesi nuove, preregistrate prima dei risultati (`research/long_lab_fable/PREREGISTRAZIONE.md`, commit `9d63d0fd`)

Rendimenti netti in % del nozionale, senza leva; costi 16 bp a giro + funding 3 bp/giorno; stress 30 bp + 9 bp/giorno.

| Ipotesi | Risultato | Esito |
|---|---|---|
| **H2 Forza relativa** (primi 5 a 28 giorni, settimanale) | primi 5 − universo: −0,07%/sett. (t −0,1); con filtro +0,63% (t 1,05); battono il 48–51% dei casuali | **Falsa** come selezione LONG |
| **H3 Trend dei leader** (filtro BTC>SMA100 + rottura 20 giorni + forza relativa; stop mobile 3 ATR; max 30 giorni) | 268 operazioni; +6,30% medio; PF 1,72; t 2,2; stress +5,26%. DEV +12,2%, **VAL −2,5%**, TEST +7,8%. Batte il 92,9% dei casuali | **NO-GO** sui criteri fissati (2 e 4) |
| H3 senza forza relativa | +5,76%, PF 1,67 | la forza relativa aggiunge poco |
| H3 senza filtro di mercato | +0,76%, PF 1,07; TEST −5,1% | **il filtro di regime è l'ingrediente attivo** |
| **H4a Tenuta** (proposta originale, cross-sezione) | primi 5 − universo: −0,91%/sett. (t −1,8); con mercato debole −2,2% (t −2,5) | **Falsificata**, segno opposto |
| **H4b Riconquista** (proposta originale, a evento) | 142 operazioni; −1,25%; PF 0,87; primi ≈ ultimi ≈ casuali | **Falsificata**, NO-GO |

**Proposta originale Fable: onestamente fallita.** L'idea era che gli asset che "tengono" nei ribassi ripartano per
primi. I dati dicono il contrario: chi tiene durante le vendite poi recupera il ritardo verso il basso. Comprare
altcoin quando BTC riconquista il massimo a 5 giorni dopo un −10% non paga (61 episodi in 7 anni).
Resta un'osservazione, non una regola: la "tenuta" in mercato debole è semmai un indizio SHORT (t −2,5).

**Cosa si è imparato su H3.** Il guadagno viene da due cose: stare LONG solo a mercato favorevole e lasciar correre
con uno stop mobile. Ingressi casuali con lo stesso filtro e le stesse uscite fanno già +3,4% per operazione. Il
periodo negativo (2024 – metà 2025) è quello in cui BTC saliva e le altcoin scendevano (universo −4,6 bp/giorno con
filtro acceso): un filtro basato solo su BTC lì sbaglia.
IPOTESI nata DOPO i risultati (quindi non provabile su questo campione): filtro sull'ampiezza delle altcoin invece
che su BTC. Si può valutare soltanto su dati futuri.

---

## F — Toro: leva e margine

**Il profitto in USDT dipende da rischio e distanza dello stop, non dalla leva.** Nozionale = rischio ÷ (stop + costi).
La leva decide solo quanto margine resta impegnato e quanto è vicina la liquidazione.

| Leva | Liquidazione circa | Stop massimo ammesso dal motore |
|---|---|---|
| 3× | 32,8% | 24,6% |
| 6× | 16,2% | 12,1% |
| 10× | 9,5% | 7,1% |
| 15× | 6,2% | 4,6% |
| 20× | 4,5% | 3,4% |

Quindi: scenario A (6–10×) regge stop del 7–12%; B (10–15×) stop del 4,6–7%; C (15–20×) stop del 3,4–4,6%.

Movimento di prezzo necessario (costi e 3 giorni di funding inclusi) con rischio 25 USDT:

| Stop tecnico | Nozionale | +15 | +25 | +40 | +60 | Margine a 10× |
|---|---|---|---|---|---|---|
| 2% | 1.111 | 1,6% | 2,5% | 3,9% | 5,6% | 111 |
| 4% | 588 | 2,8% | 4,5% | 7,1% | 10,4% | 59 |
| 6% | 400 | 4,0% | 6,5% | 10,2% | 15,2% | 40 |
| 10% | 244 | 6,4% | 10,5% | 16,7% | 24,9% | 24 |
| 21% (mediana H3) | 118 | 13,0% | 21,5% | 34,2% | 51,3% | 12 |

Con rischio 12 / 16 / 30 il nozionale scala in proporzione (×0,48 / ×0,64 / ×1,2).

Combinazioni "margine × leva" fissate a priori: 300 USDT a 15× = 4.500 di nozionale; per perdere al massimo 25 USDT
lo stop dovrebbe stare a **0,40%**. Con uno stop tecnico del 4% la perdita sarebbe 187 USDT. Sopra circa 1.000 di
nozionale, rischio ≤ 30 USDT e stop tecnico non stanno insieme: è il motivo per cui la leva alta spinge verso stop finti.

Rischio aggregato: tre stop insieme = 3 × rischio (75 USDT con 25); cinque = 125, oltre lo stop giornaliero del 12%.
Con la soglia a 450 il capitale spendibile è 550: 22 perdite piene consecutive a 25 USDT.
Funding: 3 bp al giorno del nozionale (0,18 USDT/giorno su 588); stress 9 bp. Trascurabile rispetto al rischio.

**Per H3 la leva è irrilevante:** con stop mediano del 21% e rischio 25 USDT il nozionale è ~118 USDT per posizione;
cinque posizioni usano meno di 600 USDT di nozionale, cioè **meno di 1×** sul capitale.
Traduzione in USDT di H3 (descrittiva, 7 anni, rischio fisso):

| Rischio per operazione | PnL medio | PnL mediano | Totale | Drawdown massimo | Anni negativi |
|---|---|---|---|---|---|
| 12 | +4,1 | −3,4 | +1.100 | 168 | 2022, 2025 |
| 16 | +5,5 | −4,6 | +1.467 | 224 | 2022, 2025 |
| 25 | +8,6 | −7,2 | +2.292 | 349 | 2022, 2025 |
| 30 | +10,3 | −8,6 | +2.750 | 419 | 2022, 2025 |

Obiettivi da +25/+40/+60 USDT **in media** per operazione con 1.000 USDT richiederebbero di rischiare il 7–18% del
capitale a operazione: non lo raccomando. +60 e oltre arrivano, ma come coda rara (migliore: +25 R).

---

## G — Toro: frequenza e continuità

Misure di H3 (5 slot, 2020–2026):

| Misura | Valore |
|---|---|
| Segnali | 736 (285 non eseguiti per slot pieni) |
| Operazioni a settimana | 0,86 in media; **1,57 a filtro acceso** |
| Durata media | 14,9 giorni |
| Occupazione degli slot | 36,5% |
| Giorni senza alcuna posizione | 52,6% |
| Intervallo massimo senza nuovi ingressi | 189 giorni (ribasso 2022) |
| Con 3 slot | 0,59 operazioni a settimana, risultato peggiore (+5,5%, TEST +1,7%) → meglio 5 slot |

**Punto da contestare.** "Continuità comparabile agli SHORT" nello stesso periodo non è ottenibile senza perdere:
la stessa deriva che paga gli SHORT tassa i LONG. Togliendo il filtro le operazioni salgono a 1,14 a settimana e i
giorni fermi scendono al 22%, ma il risultato va a zero (PF 1,07) e nel periodo recente è −5% per operazione.
La continuità va cercata **a livello di sistema**: Falco lavora quando il mercato è sotto la media, Toro quando è
sopra. Una seconda strategia LONG "da recupero" non esiste nei dati: H4b era il tentativo ed è fallito.

---

## H — Apprendimento incrociato Toro–Brain (progetto, nessuna modifica operativa)

Oggi Brain legge solo le **posizioni** dei classici (`classic_peers.read_peers`), non segnali, rifiuti o motivazioni.

1. **Registro osservazioni Toro** (file append-only nella cartella Toro, scritto dalla strategia in ombra):
   segnale, simbolo, regime, indicatori, motivo, eseguito/rifiutato e perché, stop iniziale, poi esito: durata,
   massimo profitto flottante, profitto realizzato, MAE, motivo d'uscita, eventuale intervento manuale.
2. **Colmare la lacuna di Brain** (B.3): registrare lato, leva, stop e codice di rifiuto anche per le proposte respinte.
3. **Confronto giornaliero offline**: per ogni segnale Toro, cosa ha deciso Brain sullo stesso simbolo entro ±1 ciclo
   (LONG / SHORT / NO_TRADE / non valutato) e con quali dati; poi l'esito di entrambi.
4. **Memoria a tre livelli**, tenuti separati:
   - *fatti osservati* (ogni coppia segnale–decisione–esito);
   - *ipotesi* (differenze ricorrenti con almeno 30 casi);
   - *regole validate* (ipotesi confermata su un secondo campione successivo, effetto con intervallo che esclude lo zero).
5. Solo il livello 3 può entrare nel prompt di DeepSeek, come contesto dichiarato "evidenza, non ordine", e solo dopo
   test e autorizzazione. Un singolo trade vincente di Toro non sposta nulla.

Informazioni utili da aggiungere a Brain come **solo contesto** (IPOTESI, da provare in ombra): stato del filtro di
mercato e ampiezza delle altcoin; forza relativa del simbolo; FRRD come osservatore. Nessuna apertura automatica.
Per i LONG di Brain il vincolo vero è lo stop ≤ 0,91%: finché resta, Brain può fare solo scalp LONG, la categoria
che i dati bocciano. Cambiarlo è una decisione di rischio che spetta all'utente.

---

## I — Raccomandazione finale

**Strategia principale per Toro: «Trend dei leader a regime» (H3), ma in OMBRA, non in PAPER.**

- *Perché:* è l'unica famiglia LONG, fra tutte quelle provate nel progetto, con aspettativa netta positiva e robusta
  ai costi (+6,3% per operazione, PF 1,72; stress +5,3%).
- *Perché non subito in PAPER:* ha fallito due dei sei criteri fissati prima (un periodo su tre negativo; 92,9% dei
  casuali contro il 95% richiesto). Rispetto il NO-GO: nessuna ritaratura sullo stesso campione.
- *Problema che risolve:* smette di comprare contro deriva; lascia correre i vincitori.
- *Rischi:* 62% di operazioni in perdita, anni interi negativi (2022, 2025), lunghi periodi fermo, bias di
  sopravvivenza dei dati, dipendenza dal filtro su BTC nei periodi di dominanza di BTC.
- *Frequenza plausibile:* 1–2 operazioni a settimana a mercato favorevole, zero a mercato sfavorevole.
- *Per approvarla:* in ombra, regole congelate, almeno 40 operazioni simulate in avanti (circa 6 mesi di mercato
  favorevole) con R medio > 0 e sopra la mediana dei controlli casuali; in parallelo, e solo in avanti, la variante
  con filtro di ampiezza.
- *Quando abbandonarla:* dopo 40 operazioni in avanti con R medio ≤ 0, oppure sotto la mediana dei casuali.

**Seconda strategia complementare: nessuna.** Non c'è evidenza che la giustifichi.

**Leva e margine per Toro, se e quando andrà in PAPER:** rischio fisso 16–25 USDT per operazione, 5 slot, nozionale
calcolato dallo stop, leva effettiva sotto 3×. Gli scenari 10–20× restano senza una strategia che li regga.

---

## L — Roadmap

| # | Intervento | Stato | Serve autorizzazione |
|---|---|---|---|
| 1 | Eseguire lo script di audit sulla VPS (sola lettura) | pronto | no (solo esecuzione) |
| 2 | Installare la correzione del pulsante «Chiudi» (immagine web) | CORREZIONE PROPOSTA, testata in locale | sì |
| 3 | Registrare lato, leva e stop delle proposte di Brain (osservabilità) | **preparato**: ramo `work/brain-reject-observability-20261115` (`6d7d3c6`), spento di default, 8 test + 1.128 regressioni | sì |
| 4 | Contabilizzare il funding nel PnL PAPER di Brain | proposta | sì |
| 5 | Toro H3 in ombra con registro osservazioni, regole congelate | **preparato**: `research/long_lab_fable/shadow.py` + test; non installato né schedulato | sì |
| 6 | Confronto offline Toro–Brain e memoria a tre livelli | progetto | sì |
| 7 | Valutazione in avanti del filtro di ampiezza; FRRD come osservatore | IPOTESI | sì |
| 8 | Decisione dell'utente sul vincolo di stop di Brain per i LONG | aperta | — |

Non raccomando: nuove varianti LONG intraday a regole, leva alta per Toro, strategie di rimbalzo.

### Aggiunte dopo il primo rapporto (15/11, pomeriggio)

- **Osservatorio delle proposte di Brain** (punto 3). Il motore elimina di proposito lato e stop dalle decisioni non
  approvate prima di scriverle nel journal; per non toccare quel confine la patch annota la proposta *prima* del
  motore, in un file a parte (`proposal_observations.jsonl`), solo campi numerici, solo con
  `V3_BRAIN_PROPOSAL_LOG=1`. Journal e decisioni restano identici (provato). Unendo per istante e simbolo si saprà
  quanti LONG propone DeepSeek, con quale stop, e quanti ne respinge il rischio.
- **Toro in ombra** (punto 5). `shadow.py` importa le regole H3 dal laboratorio senza ridefinirle, ricostruisce tutto
  da zero a ogni esecuzione e scrive un registro con i campi richiesti per il confronto con Brain (regime, motivo,
  stop iniziale, durata, massimo flottante, MAE, netto, R, uscita, rifiuti per slot pieni). Test: ripetibilità,
  coerenza col motore del laboratorio, nessuna riga chiusa che cambia quando arrivano nuovi giorni.
- **Stato di oggi (ultimo giorno chiuso 14/11/2026):** filtro di mercato **spento**; solo il 6,7% delle altcoin
  dell'universo è sopra la propria media a 100 giorni; **zero segnali**. Con queste regole Toro oggi resterebbe fermo.

## Limiti di questo lavoro

- Nessun accesso alla VPS: la conferma della sezione A e i numeri completi di Brain dipendono dallo script di audit;
  i numeri di Brain nella sezione B vengono da schermate riportate nella issue #95.
- I servizi Brain girano anche da `/opt/superbot-v3-rc84-repair-ab7e0b7` (issue #95): lo script di audit legge solo
  journal e file di stato, quindi non dipende da quale copia del codice è in esecuzione.
- Dati: solo contratti oggi quotati (bias di sopravvivenza, favorisce i LONG); candele giornaliere (stop valutati sul
  minimo del giorno); funding a tasso fisso; slippage delle altcoin minori probabilmente più alto dei 2 bp assunti.
- H3 è una sola specifica; le sensibilità al filtro (50 e 200 giorni: +4,0% e +4,1%, stesso segno e stesso periodo
  negativo) sono descrittive.
- Test frontend non eseguiti (dipendenze Node assenti).
