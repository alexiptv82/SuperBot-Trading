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
