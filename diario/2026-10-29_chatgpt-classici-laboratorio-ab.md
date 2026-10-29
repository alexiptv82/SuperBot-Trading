# 29 ottobre 2026 — laboratorio recupero strategia classici (ChatGPT)

## Autorizzazione e isolamento
Dopo discussione «ritrovare la strada» l'utente autorizza: «ok mi sembra un ottima scelta di lavoro puoi procedere per il momento su i classici». Applicata **solo a sviluppo e test offline**, non a merge/deploy/reset/pausa o nuovi ordini. Hawk/Bull classici PAPER, Brain Free e Brain Scalp, app, VPS Singapore, dati e file journal/vault restano invariati. Branch esclusivo `work/classics-12oct-selective-lab-20261029` base dc16e01.

## Risultati verificati

1. CI provenance `40815650805` SUCCESS: il file storico `backend/desk/signals.py` è identico fra 12 ottobre, fine golden e prime perdite, SHA blob `57b524e75593b0fe6f3a0712af1a0b2f14bd4a75`. Ritorno a quel file non dimostra ritorno ai risultati.
2. Creato laboratorio isolato `backend/rollback_lab/ab_runner.py` con workflow sintetico `classics-12oct-replay-ci.yml`, esecuzione SUCCESS per entrambi i portafogli su input simulati. Confronta segnale 12/10 e segnale dc16e01, ciascuno con vecchio e moderno engine `PaperAccount`. Non reimporta CLI né gestisce ordini. Input identici per tutte le varianti.
3. Verifica reale Bitget 12–29 ottobre 2026, 7 mercati BTC,ETH,SOL,ADA,DOGE,BNB,XRP, step30m, 17 giorni, costo/slippage/stop da motore: **Actions `40821658014` SUCCESS**, SHA dati identico Hawk/Bull `3a0b3b232509f6e7d441045449647955f025a4c4f5fb65ded7e64f80374dc5ab`. Conti PAPER nuovi1000, simulazioni no AI/DCA/split/macro/intrabar. Old scorer+old engine: Hawk115 chiuse netto **-443,70**, Bull69 chiuse **-585,40**. Old scorer+new engine: stessi risultati in questo campione. New scorer+old/new engine: Hawk14 chiuse **-10,00**, Bull14 chiuse **-20,40**. Vecchio modello tutto SHORT; moderno 11 LONG,3 SHORT ciascuno. 7 mercati non rappresentano intero universo.
4. **Gate fedeltà NON SUPERATO**: confronto con `diario/analisi-run-2026-10-27/positions.csv`, golden PAPER Hawk #2 solo sette mercati **44 posizioni +390,8264 USD**, Bull #1 **13 posizioni +359,8484 USD**. Stesso periodo di chiusura 12–16 ottobre nel backtest vecchio: Hawk46 chiuse **+25,83**, Bull23 chiuse **-136,61**. Scarto ampio: nessuna proposta di rollback può considerare il banco fedelmente validato. Le golden reali su 26 mercati erano Hawk76 +1090,61 e Bull17 +770,75. Necessaria riproduzione deterministica per vero timestamp d'ingresso, simbolo, direzione, prezzi, motivazioni, size, partial, DCA, decisioni Claude e feed 15m.
5. Il backtest preesistente nel repo aveva C63 invece di golden C70, conto100000 anziché1000 e scorer preP1 non esattamente SHA12/10; queste differenze sono state superate nel nuovo esperimento isolato.
6. Avviata verifica aggiuntiva del vecchio universo di 26 simboli (Actions `40822151627`), esito NON disponibile alla scrittura di questa voce; non attribuirgli risultati fino a verifica e integrazione successiva.

## Verdetto provvisorio
NON ripristinare direttamente il software 12/10, NON giudicare la redditività delle due versioni dal solo backtest a sette asset. Quello che sappiamo con affidabilità: vecchio scoring uguale fra golden e prima crisi; cambi di mercato e componenti AI/uscite/sizing confondenti; la prima prova comparativa su dati reali non ricostruisce i fatti documentati. Prossimo gate: test fedeltà degli ordini e dei realizzi con stesso mercato/timeframe/candidati e replay distinto per finestra da capitale iniziale.

**Nessuna modifica al ramo rule-pool/main, nessun deploy o evento su VPS Singapore.** Claude revisiona in parallelo Brain Scalp su rami diversi.

AI: chatgpt (chat normale)


## Aggiornamento conclusivo: universo storico completo (26 mercati)

**Actions 40822151627 SUCCESS**, su Bitget pubblico 12–29 ottobre, identica impronta SHA256 Hawk/Bull `1e9b32793bb965513c53a4098456542b4d2ec94243286a032d25410fd1629dff`. Sono stati caricati tutti e 26 i mercati richiesti (inclusi XAU/XAG). Tutte le combinazioni dello stesso scanner storico o moderno con motore OHLC storico/moderno hanno ottenuto **lo stesso netto** all'interno della stessa ricetta d'ingresso su questo campione, NON prova equivalenza gestione AI/DCA/split reale.

| Portfolio | Scoring/contesto | Chiusure | P&L netto simulato | WR | Max DD simulato |
|---|---|---:|---:|---:|---:|
| Hawk | 12 ottobre | 22 | -550,10 USD | 18% | 610 USD |
| Hawk | moderno | 70 | -273,70 USD | 36% | 756 USD |
| Bull | 12 ottobre | 7 | -585,70 USD | 0% | 590 USD |
| Bull | moderno | 56 | -3,80 USD | 41% | 492 USD |

Nella versione storica simulata **le uscite e perdite della finestra 12–16 ottobre provocano già il blocco delle successive aperture**: zero ulteriori chiusure simulate 16–29 ottobre, circa 957/991 proposte bloccate rispettivamente Hawk/Bull. Non leggere gli zero successivi come giorni di successo o mancanza di segnali. Il motore storico simula 5 LONG/17 SHORT Hawk, 4 LONG/3 SHORT Bull, in forte contrasto con le run golden vere (Hawk74 SHORT/2 LONG, Bull17 SHORT): **forte fallimento di fedeltà direzionale e di conteggio, oltre che P&L**.

Modern scoring a 26 mercati: Hawk26 LONG con -469 USD e 44 SHORT con +196 USD (netto -273,70); Bull16 LONG con -380 USD e 40 SHORT con +376 USD (netto -3,80). Questi aggregati indicano dove indagare, **non autorizzano a vietare i LONG**: il test non riproduce decisioni AI, input/costi reali completi e gestione posizioni della produzione. Il max drawdown resta elevato anche nel modello moderno.

Nel solo periodo golden12–16 il nuovo benchmark senza AI (26 simboli) produce Hawk15 operazioni +167,13 USD e Bull14 +196,53 USD, contro storico vero Hawk76 +1090,61 e Bull17 +770,75, quindi **nessun replay con idoneità a scegliere un rollback**.

**Verdetto:** non eseguire alcun rollback a 12/10 né introdurre nuovi filtri ora. Prima costruire un replay ancora più fedele alle operazioni effettivamente registrate: percorso delle decisioni Claude / fallback, campioni market point-in-time, margine/leva, take/stop, gestione e contabilità, stesso orario di ingresso, stesso calendario. Separare in moduli entry ed exit e testare intervalli indipendenti con conto nuovo, verificando che la golden reale sia riprodotta entro tolleranze concordate. Una volta ottenuta fedeltà, verificare ai periodi di prima crisi e recenti senza ottimizzare sul campione test.

**Nessun change** a branch rule-pool/main, dati o container; CI su ramo isolato e archivio dati JSON/artifacts nel run GitHub. Consultabili:
- https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40822151627
- https://github.com/alexiptv82/SuperBot-Trading/tree/work/classics-12oct-selective-lab-20261029

AI: chatgpt (chat normale)
