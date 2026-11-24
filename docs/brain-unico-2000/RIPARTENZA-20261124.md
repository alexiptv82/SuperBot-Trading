# Brain unico PAPER 2.000 USDT: ripartenza del 24/11/2026

Incarico del proprietario (24/11): fermare Falco Evoluto e Brain Scalp, archiviarli e ripartire con **un solo Brain
PAPER da 2.000 USDT** che usa bene il capitale, gestisce le uscite e accantona i profitti. Solo PAPER. Ramo
`claude/brain-unico-2000-20261124`.

## Stato prima della ripartenza (verificato sulla VPS, 24/11 09:00 UTC)
- Falco Evoluto e Brain Scalp RUNNING; **messi in pausa** con `superbot-ops pausa falco|scalp` alle 09:00 (nessuna nuova
  apertura; uscite e chiusure manuali attive). Falco aveva aperto nei giri delle 08:00 e delle 09:00.
- Brain RC1 in pausa, non toccato.
- In produzione: interfaccia `main.3dd759b4.js`, `/api/v3/paper-archive` = 404 → **il pacchetto `app-f50f7ae4` non è
  installato**. Non viene installato: la ripartenza porta direttamente la dashboard nuova adattata al Brain unico.
- Le cartelle delle run sono leggibili solo da root: posizioni aperte e journal li legge la procedura root.

## Parametri storici (fase 3) e scelte
| Fonte | Cosa funzionava | Difetto da non copiare |
|---|---|---|
| Falco V2 (`backend/desk`, `7f7a8419f49`) | scalp 15–45×, margine 150–250 (tetto 400), **TP 0,3–1 %, SL 0,2–0,6 %**, R:R ≥ 2, **35 % a 2R e residuo a 3–4R**, revisione di ogni posizione a ogni giro (hold/close/partial_close), fino a 10 posizioni, 25+ simboli con **XAU e XAG**, stop entro il 75 % della distanza di liquidazione | dimensionamento a margine (rischio non controllato), DCA, nessun costo AI contato |
| Brain pilota (`brain_pilot/portfolio.py`, `1f2edeb6`) | **leva calcolata**: la più bassa che fa stare la posizione nel margine massimo, entro il limite di liquidazione; stop minimo 0,8 ATR; TP ≥ 1,5R | rischio 1 %, margine 100 |
| Brain DeepSeek 2.000 (`runner_config_brain2000_paper.json`, ramo `work/v3-release-candidate-gpt6-20261106`) | **rischio 4,29 % (75 su 350), aperto 12 %, margine 20 % (400) per posizione, 55 % totale**, ciclo 60 min | `max_loss_margin_fraction` 0,214 con leva minima 20× → stop massimo ~0,9 %: setup validi rifiutati |
| Falco Evoluto / Brain Scalp (23–24/11) | Guardian, protezione profitti, chiusura singola, journal | stesso conflitto (stop max 1,17 %: 309 segnali su 355 rifiutati), 4 posizioni al massimo (anche un tetto fisso a 4 nel controllo dopo l'AI) |

I valori **realmente caricati** sulla VPS per queste run stanno nelle loro cartelle (solo root): la procedura li archivia
intatti (`runner_config.json` con impronta) e l'Archivio dell'app li mostra. Un risultato storico positivo non garantisce
profitti futuri: questi valori sono la base del collaudo PAPER, da correggere con i risultati.

## Configurazione applicata (`backend/v3/runner/runner_config_brain_unico_2000_paper.json`, schema 3)
| Voce | Valore |
|---|---|
| Capitale, slot | 2.000 USDT; 10 aperture contemporanee (le due quote di un'apertura = 1 slot), nessun obbligo di riempirli |
| Mercati | 25 cripto per capitalizzazione negoziabili su Bitget (BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, HYPE, LINK, SUI, AVAX, XLM, BCH, HBAR, LTC, SHIB, DOT, UNI, AAVE, NEAR, PEPE, APT, ICP, ETC) + **XAUUSDT, XAGUSDT**; regole dei contratti verificate 27/27 con i dati Bitget attuali, viste di mercato complete anche per oro e argento |
| AI | DeepSeek (`deepseek-flash`, ragionamento), giro ogni 30 min, tetto di spesa 4 USD/giorno |
| Rischio | 4,3 % per trade (≈ 86 USDT), 12 % aperto, 10 % nella stessa direzione (le cripto si muovono con BTC), costi stimati 16 bp andata e ritorno |
| Margine | massimo 400 per trade, 55 % totale, minimo 5 (nessuna size minima che blocchi un setup valido) |
| Leva | 15–50×, **scelta dal codice**: la più bassa che raggiunge la dimensione massima consentita da rischio e margine; lo stop deve restare entro il 60 % della distanza di liquidazione (stessa regola del RiskManager); la leva proposta dall'AI non conta; lo stop non viene mai stretto |
| Uscite | due quote: **35 % con TP a 2R**, residuo con **TP a 3,5R**, stop a pareggio da 2R, trailing da 2,5R a 1R; durata massima 12 h (intraday); stop obbligatorio sempre |
| Revisione AI | a ogni giro DeepSeek rivede ogni apertura: HOLD, CLOSE, PARTIAL_CLOSE (incassa la 1ª quota), MODIFY_STOP (solo più stretto, ≥ 5 bp dal prezzo); il codice valida; se l'AI non risponde restano attive le uscite deterministiche |
| Modalità | ATTIVO; **SELETTIVO** da +300 USDT netti realizzati nella sessione (rischio 0,6 R, confidenza ≥ 0,65); **PROTEZIONE** da +400 (0,35 R, confidenza ≥ 0,8, nessun rientro); netti = commissioni e costo AI della sessione dedotti; sessione da mezzanotte (ora italiana) |
| Freni | stop giornaliero 25 % (avviso 15 %), perdita di sessione 20 %, floor dei profitti dal +25 % (conserva il 50 %), drawdown globale: rischio dimezzato dal 15 %, blocco al 30 %; equity minima 1.400 |
| Salvadanaio | a mezzanotte (ora italiana) il profitto **realizzato** sopra 2.000 passa nel salvadanaio, mai reinvestito; P&L aperto mai accantonato; perdite nel capitale operativo, senza reintegri; ricostruito dal journal con la stessa funzione nel runner e nella dashboard |

Con questi valori: stop 2 % → 15× (rischio pieno, margine ~265); stop 0,4 % → 39× (153,6 unità a 100, margine ~394);
stop 0,2 % → 50× con margine 400 (rischio ~72 < 86); stop 4 % → NO_TRADE (oltre il limite di liquidazione anche a 15×).

## Codice (nessun componente stabile riscritto)
- `backend/v3/unico.py`: politica del Brain unico, quote, salvadanaio (funzioni pure).
- Motore (`brain_f2/engine.py`): leva "fit". RiskManager invariato.
- Esecutore (`executor/paper.py`), `open_serial.py`: apertura in due `paper_open` normali (stesso stop, stessa decisione).
  Ogni chiusura resta un `paper_close`: contabilità, perdita giornaliera, Guardian e app restano corretti.
- Uscite (`exits.py`, `monitor.py`): TP proprio della quota e stop stretti dall'AI (`stop_move`, dalla candela successiva).
- Revisione AI (`runner/position_review.py`) e canale `brain_close_request.json` eseguito dal servizio delle uscite
  (motivo `brain_close`, distinto dalle chiusure manuali dell'operatore, che restano `manual` e materiale di apprendimento).
- Guardian (`guardian.py`): livelli SELETTIVO/PROTEZIONE dal netto realizzato di sessione.
- Controllo dopo l'AI (`post_ai_guard.py`): slot del profilo (non più il 4 fisso) e salvadanaio escluso dal capitale.
- Dashboard: un solo Brain (modalità, slot, salvadanaio, quote, stop del Brain, revisioni AI), statistiche per trade.
- Le run storiche (schemi 1 e 2) si comportano come prima: tutti i test esistenti invariati e verdi.

## Installazione (un comando root) e rollback
Pacchetto `rilascio/brain-unico-<commit>`; `ripartenza.sh`: impronte → codice nuovo (`30-codice.sh`) e contratti →
`ripartenza_brain.py` (pausa, chiusura contabile delle posizioni aperte dal canale ufficiale, arresto, archivio
integrale con impronte e `RISULTATI.json` in `.archivio/reset-<data>`, unità di Brain Scalp sul codice nuovo, Falco
Evoluto disattivato, run nuova da 2.000 con journal nuovo nello slot di Brain Scalp, avvio, verifica, attivazione PAPER
con lo stesso nome di chi aveva approvato) → web e interfaccia (sonda sui dati veri, vecchia web conservata) → controllo
dal dominio. Rollback: `ripartenza.sh --rollback <TIMBRO>`.
Slot riusato: stessa cartella, stesso `run_id` tecnico (`brain-scalp-paper-p1`), stesse unità → bridge di chiusura,
`superbot-ops` (`pausa scalp`, `log scalp-runner`…) e mount della web restano validi senza modifiche ai privilegi.
