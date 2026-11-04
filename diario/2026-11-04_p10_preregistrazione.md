# 2026-11-04 (sera) — Pre-registrazione del laboratorio e prompt P10 per ChatGPT

**Claude Sonnet 5.5 — coordinatore tecnico** · solo documenti: nessun codice, nessun dato di mercato, nessun collegamento col Brain, coi suoi prompt, soglie o limiti (regole 1–9 invariate)

## Cosa è stato deciso
Una revisione esterna (21:26) della proposta di pre-registrazione è stata valutata punto per punto. **Adottati:** stress a 20 bp (solo riportato), sei risultati separati strategia × asset **senza verdetto aggregato**, controllo invertito (stessi istanti d'ingresso, lato opposto, stop/obiettivo speculari; diagnostico), classi di verdetto con confidenza 0,99, regola di decadimento fissata prima (OOS > 0 e ≥ 50 % dell'IS, differenza assoluta riportata), quota di candidati ambigui con `target_first` come limite, drawdown in R, scarto d'ingresso misurato. **Aggiunto da me:** controllo a scorrimento circolare del vettore dei segnali (misura la deriva del mercato). **Già soddisfatto dal repo:** Donchian sulle barre precedenti, `stop_first`, embargo e finestre semiaperte per `closed_at_ms`, orizzonti incompleti scartati, bootstrap a blocchi di giorni. **Dichiarati come limiti:** ingresso al `close` della barra di segnale, nessun funding/slippage separati (non c'è la serie), candidati etichettati indipendentemente (non un portafoglio, niente cooldown dall'uscita), granularità 15 minuti.

## Valori fissati (prima di qualunque risultato)
BTCUSDT/ETHUSDT, 15 m, ~540 giorni. S07 Donchian 20 + EMA50; S05 Bollinger 20/2, %B 0,2/0,8, MACD 12/26/9; S02 EMA 9/21 + ADX(14) ≥ 25. ATR 14, stop 1,5 ATR, obiettivo 2R, cooldown 3, orizzonte 4 h. Costi 12 bp (+ 0 e 20 riportati). Walk-forward 120/30/30 giorni, embargo 1 giorno. Regime (valori **del laboratorio**, non del Brain): shock TR ≥ 3 ATR, espansione percentile ≥ 80 su 2 880 barre, trend ADX ≥ 25, range ADX ≤ 20. File eseguibile: `backend/v3/lab/preregistration.json` (sha256 `7e561c2131d33a4214ba973da2163e53a232fe2e6ea115b95443c109d9ab550e`), documento: `claude/lab-preregistrazione-p10-2026-11-04.md` (Project).
**`EVIDENZA_POSITIVA`** richiede tutte: IC 0,99 con limite basso > 0; walk-forward con almeno 3 fold selezionati, 100 trade OOS, OOS > 0 e ≥ 0,5 × IS; controllo invertito peggiore e ≤ 0; rango ≥ 95 nel controllo a scorrimento. **Se nessuna coppia la ottiene: si ferma, P9b non si costruisce.** Cambiare un parametro dopo i risultati = nuova pre-registrazione.

## Prompt P10
`claude/prompt-chatgpt-p10-lab-2026-11-04.md` (Project): pacchetto `backend/v3/lab/` — protocollo rigido, adattatore etichette → `TradeOutcome`, controlli, verdetto (tabella di verità), valutazione per coppia, esecutore con segmentazione dei buchi e rapporto. Modalità B, parte da #51 `8f123a2`. Test: oracolo a mano, prove di sistema con vantaggio piantato (incluso il caso «deriva senza informazione» che non deve dare evidenza), niente rapporti fra tempi. Verifica di Claude ridotta come concordato.

## Prossimo
ChatGPT consegna P10 → Claude applica invariato, verifica (oracolo dell'adattatore + prova di sistema), poi caricatore BTC/ETH (copia di `labdata.py`, spezza i buchi) + job GitHub Actions + rapporto. Nessuna decisione dell'utente è bloccante; restano aperte quelle per il Brain (soglie di regime, soglie statistiche, politica di esplorazione in PAPER, L1/L4).

⛔ Nessun merge/deploy · `DESK_MODE=paper` invariato · Hawk/Bull non toccati · cervello intatto.
