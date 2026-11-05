# 5 novembre 2026 — P10 FATTO e primo run reale del laboratorio: sei NEGATIVO

**Claude Sonnet 5.5 — coordinatore** · modulo `backend/v3/lab/`: codice di **ChatGPT** (Modalità B: consegna come testo, applicata invariata) · caricatore `backend/v3/lab_tools/` e workflow: Claude · PR #52 DRAFT (impilata su #51), ramo `work/v3-p10-lab-chatgpt-20261105`, HEAD `89b4f3e`.

## Consegna e verifica
- Consegna di ChatGPT applicata **invariata** nel commit `9556c9f` (5/11, 06:11 ora svizzera): sette moduli, `preregistration.json` (sha256 `7e561c2131d33a4214ba973da2163e53a232fe2e6ea115b95443c109d9ab550e`) e 545 test. **Nessun difetto di codice**; un solo ritocco estetico del rapporto («None» → «—», commit `81eb069`, con test).
- Mie verifiche: 19 test indipendenti (adattatore riscritto da zero con `Fraction` e uno scanner di barriere a parte, identico campo per campo; numeri del rapporto ricalcolati a parte; verdetto su 20 000 casi; catena vera su mercati sintetici dove la risposta è nota: tendenza → `EVIDENZA_POSITIVA`, mean-reverting → `NEGATIVO`, deriva senza informazione → `POSITIVO_INCONCLUDENTE` con E4 fallita). Mutazione di ChatGPT rieseguita: **59/60** (il sopravvissuto M32 è equivalente).
- Caricatore delle candele pubbliche Bitget (sola libreria standard, sola lettura, righe incoerenti scartate come buchi e riportate) + 8 test offline. Test del laboratorio **572/572**; suite V3 3560 → **4132 PASS**, 3 xfailed, 3 failure preesistenti (`fastapi` mancante).

## Run reale (GitHub Actions, run 41974342514)
Candele 15 m BTCUSDT/ETHUSDT, 540 giorni, 51 839/51 840 barre per simbolo, 0 buchi. **Sei verdetti su sei `NEGATIVO`**, nessuna `EVIDENZA_POSITIVA`. Per la regola pre-registrata: **ci si ferma, P9b non si costruisce**, nessun collegamento col Brain. Dettaglio, tabella e limiti nel documento del Project `claude/lab-risultati-p10-2026-11-05.md` (riportato sotto). Il rapporto completo è nell'artefatto `lab-p10-risultati` del run; il workflow di sola lettura `lab-p10-report.yml` ne stampa il rapporto nel log senza rilanciare il laboratorio.

## Regole inviolabili rispettate
Nessun redeploy di Hawk/Bull · `DESK_MODE=paper` invariato · nessuna modifica a strategia, soglie, limiti di rischio o prompt · cervello (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`) non toccato · nessuna chiave nel codice · HI-TV non toccato · nessun importo o saldo reale (dati di mercato pubblici) · nessun force push · PR #52 non unita.

---

# Laboratorio P10 — risultato del primo run reale (5 novembre 2026)

**Autore:** Claude Sonnet 5.5 (coordinatore) · **Esito: sei verdetti su sei `NEGATIVO`. Nessuna `EVIDENZA_POSITIVA`. Per la regola pre-registrata ci si ferma: P9b non si costruisce, nessun collegamento col Brain.**

## Cosa è stato eseguito
- Protocollo pre-registrato `backend/v3/lab/preregistration.json` (sha256 `7e561c2131d33a4214ba973da2163e53a232fe2e6ea115b95443c109d9ab550e`, pubblicato nel commit `9556c9f` il 5/11 alle 06:11, **prima** di qualunque risultato). L'impronta è verificata dal job prima di tutto.
- Dati: candele pubbliche Bitget (futures USDT, 15 minuti), BTCUSDT e ETHUSDT, finestra di 540 giorni (scaricata il 5/11 alle 05:30 UTC), **51 839 barre su 51 840 attese per simbolo, 0 buchi, 0 righe incoerenti scartate**.
- Esecuzione: GitHub Actions, run 41974342514 (commit `6d62a6d`), sola lettura, nessun segreto. Prima del run i 572 test del laboratorio (senza rete) sono passati anche sul runner.
- Il rapporto completo (JSON e Markdown) e i dati sono nell'artefatto `lab-p10-risultati` del run; il workflow `lab-p10-report.yml` ne ha stampato il rapporto nel log **senza rilanciare nulla**.

## Rapporto (testo del programma, invariato)
| Strategia | Simbolo | Verdetto | n | Netto bp (12) | IC 0,99 | Media R | Max DD R | WF IS / OOS / decadimento / rapporto | Invertita | Rango | 0 bp | 20 bp | Ambigui | Scarto bp |
|---|---|---|---:|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| S07 | BTCUSDT | NEGATIVO | 2827 | -14.4910 | -17.5413 / -11.2908 | -0.4062 | 1154.4165 | — / — / — / — | -9.6381 | 7.5000 | -2.4910 | -22.4910 | 0.0010 | 0.0000 |
| S07 | ETHUSDT | NEGATIVO | 2528 | -11.8183 | -16.7454 / -6.8498 | -0.2119 | 545.7168 | — / — / — / — | -9.5110 | 67.5000 | 0.1817 | -19.8183 | 0.0000 | 0.0000 |
| S05 | BTCUSDT | NEGATIVO | 763 | -14.9532 | -20.8374 / -8.8941 | -0.4194 | 319.9716 | — / — / — / — | -14.6541 | 17.5000 | -2.9532 | -22.9532 | 0.0012 | 0.0000 |
| S05 | ETHUSDT | NEGATIVO | 735 | -9.6976 | -19.3353 / -0.4201 | -0.2320 | 174.1573 | — / — / — / — | -17.8483 | 75.0000 | 2.3024 | -17.6976 | 0.0000 | 0.0000 |
| S02 | BTCUSDT | NEGATIVO | 421 | -15.8991 | -23.3041 / -7.7789 | -0.3957 | 173.8982 | — / — / — / — | -10.3047 | 10.0000 | -3.8991 | -23.8991 | 0.0000 | 0.0000 |
| S02 | ETHUSDT | NEGATIVO | 469 | -12.1399 | -22.9815 / -0.8685 | -0.1755 | 91.9717 | — / — / — / — | -10.7838 | 45.0000 | -0.1399 | -20.1399 | 0.0020 | 0.0000 |

(Colonne: n = operazioni candidate etichettate; «Netto bp (12)» = media per operazione con costo primario 12 bp; «0 bp» / «20 bp» = stessa media con costo 0 e 20 bp; «Invertita» = controllo con stop e obiettivo speculari; «Rango» = percentile nel controllo a scorrimento circolare del vettore dei segnali (serve ≥ 95 per E4); «WF» = walk-forward IS / OOS / decadimento / rapporto.)

## Lettura
1. **Tutte e sei le medie nette sono negative** (da −9,7 a −15,9 bp) e l'intervallo al 99 % sta interamente sotto zero per ogni coppia (i più vicini a zero: S05-ETH, limite alto −0,42 bp; S02-ETH, −0,87 bp). Per la precedenza fissata il verdetto è `NEGATIVO`, prima ancora di guardare le altre condizioni.
2. **Il vantaggio lordo non si vede.** Con costo 0 le medie stanno tra −3,9 e +2,3 bp, cioè dell'ordine dell'incertezza. Con 12 bp di costo ogni coppia perde; con 20 bp perde di più. Le strategie, così come sono, non coprono i costi.
3. **Il walk-forward non ha prodotto nessuna misura fuori campione** (colonne «—»): nessuna misura OOS disponibile. Non serviva per il verdetto (`NEGATIVO` ha la precedenza); il motivo preciso (verosimilmente nessuna cella selezionata nei fold) **non l'ho verificato**, perché non cambia la decisione.
4. **Il controllo invertito (stesso istante, stop e obiettivo speculari) perde anch'esso circa il costo** (da −9,5 a −17,8 bp): in entrambe le direzioni il risultato è negativo e dell'ordine del costo. Quadro coerente con segnali che, a questo orizzonte e con questi parametri, non portano informazione direzionale utilizzabile.
5. I ranghi del controllo a scorrimento (7,5 – 75) sono tutti sotto la soglia 95: nessun segnale distinguibile dalla semplice deriva.
6. Tocchi ambigui trascurabili (≤ 0,2 %): la scelta `stop_first` non incide. Scarto d'ingresso 0 bp.

## Cosa NON dice
- Non dice che nessuna strategia possa funzionare: dice che **queste tre strategie da manuale, con questi parametri non scelti sui dati, a 15 minuti con orizzonte di 4 ore, su questi 540 giorni di BTC ed ETH, dopo 12 bp di costo, non mostrano vantaggio.**
- Ha un solo periodo di mercato (~18 mesi): non copre tutti i regimi.
- Il «Max DD R» del rapporto è una somma in ordine di chiusura di operazioni che si sovrappongono (candidati, non portafoglio): non è una misura di rischio reale.
- Il modello dei costi è il solo 12 bp fisso (più 0 e 20 di stress): funding e slippage non sono simulati separatamente.

## Decisioni già prese e conseguenze
- **Regola pre-registrata:** nessuna `EVIDENZA_POSITIVA` → ci si ferma; **P9b (le altre 9 schede) non si costruisce.**
- **Cambiare un parametro dopo aver visto i risultati = nuova pre-registrazione** e nuova decisione dell'utente; i 540 giorni sono ormai «consumati» per queste tre strategie.
- **Nessuna modifica** a strategia, soglie, limiti di rischio o prompt del Brain (regola 3). Il cervello non è toccato. `DESK_MODE=paper` invariato. Nessun redeploy.

## Dichiarati nella pre-registrazione (limiti)
ingresso al `close` della barra di segnale, non all'apertura successiva (lo scarto è misurato); nessun funding né slippage separati (il 20 bp li sovrasta); candidati etichettati indipendentemente, non un portafoglio (trade sovrapposti; bootstrap a blocchi di giorni; il drawdown in R è una somma in ordine di chiusura); granularità 15 minuti (tocchi ambigui non risolvibili: si riporta la quota e il limite `target_first`); confronti multipli (6 coppie, confidenza 0,99 approssimata); periodo breve (~540 giorni); la deriva è misurata dal controllo a scorrimento, non eliminata; parametri da manuale, non scelti sui dati, ma i 540 giorni sono stati usati da altri laboratori; solo PAPER.

## Prossimi passi possibili (da decidere con l'utente, nessuno è urgente)
- Chiudere il capitolo laboratorio con questo esito (PR #52 resta in bozza come archivio riproducibile del metodo).
- Usare il laboratorio, che ora esiste ed è verificato, per una **nuova ipotesi pre-registrata** (p. es. altro orizzonte o un filtro di regime), solo se l'utente la vuole.
- Sbloccare le decisioni aperte non legate al laboratorio: soglie di `RegimeParams` per il Brain, politica di esplorazione in PAPER, L1/L4, certificazione F0 e import dei trade legacy.
