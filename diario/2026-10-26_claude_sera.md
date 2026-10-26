# Diario Claude — 26 ottobre 2026 (turno sera)

## Contesto: diagnosi performance e fix segnali (voce corretta a fine turno)

L'utente ha segnalato che Bull ha perso molto oggi: ha aperto solo SHORT in una giornata
di rimbalzo. Ha anche segnalato che un portafoglio si è fermato per limite di perdita
giornaliero. L'utente sospettava che il fix dei LONG non fosse completamente operativo.

## Diagnosi

### Causa principale: formula stagionale moltiplicativa invertita

In `seasonal.py` la formula originale era:
```python
effective = monthly_bias * cycle_mult
```
Con ottobre 2026 a mese 30 dal halving (`cycle_mult = -1.0`, fase "bear market"):
```
22% × (-1.0) = -22 → short_bonus = 5
```
Il sistema dava **5 SHORT** a BTC in ottobre, il mese storicamente **più bullish** (+22%).

Combinato con il P1 fix (RSI 30-50 → +8 SHORT), il totale era fino a **13 SHORT** di
bias nella scoring — sufficiente a superare la soglia di confidence su segnali neutri.

### Causa secondaria: daily loss limit inattivo in paper mode

```python
def _daily_loss_exceeded(acc) -> bool:
    if not LIVE._live:
        return False   # ← bypass totale in paper
```
Il daily stop non funzionava mai in paper, consentendo perdite illimitate nella sessione.

### Analisi report 4 AI esterne

L'utente ha raccolto report da DeepSeek, Kimi 3, Grok 4.7 e ChatGPT 6.
Tutti e 4 hanno identificato il problema della formula moltiplicativa.
Punti di sintesi adottati:
- Formula additiva pesata (ChatGPT 6): `0.60 × monthly + 0.40 × cycle`
- Curva smooth interpolata (Grok 4.7): mese 30 = −0.40 invece di −1.0
- market_factor (Grok): se BTC va contro il prior, riduce/azzera il bonus
- DailyGuard + open risk cap (DeepSeek + Kimi): blocca la 2a posizione Bull

## Implementazione (corretta dopo verifica sul codice live)

Il primo tentativo (commit `767bee0` sul ramo `ccr-999de027-0stnyt`) era basato su `main`, che contiene una versione
**vecchia** di `cli.py`/`signals.py` (il codice dei bot vive su `rule-pool`): non e' deployabile e non va unito.
Il lavoro vero e' sul ramo `work/fix-segnali-v2` (base `rule-pool`), commit `b93196b`, unito in `rule-pool` da AI Write
con il merge `35f08cf` (il ramo `ccr-...` resta come traccia, da non usare).

### `backend/desk/seasonal.py` (identico tra main e rule-pool, riscritto)
1. Formula additiva: `0.60 * tanh(bias_mensile/22) + 0.40 * curva_ciclo` (prima: bias mensile x moltiplicatore di fase).
2. Curva del ciclo interpolata (`_CYCLE_ANCHORS`): mese 30 = -0.40 (prima -1.0 a gradino).
3. Freno di mercato: `btc_return_3d` contro il prior di >=1,5% dimezza il bonus, di >=3% lo azzera.
4. `get_seasonal(symbol, now_ms)` invariata; `btc_return_3d` e' opzionale.
Esiti: BTC ottobre 2026 da 5 SHORT a 5 LONG; BTC/ETH 1 novembre da 9/10 SHORT a 6 LONG; mesi storicamente deboli
(mag, ago, set) restano SHORT (3, 3, 5).

### `backend/desk/seasonal_v1.py` (nuovo, byte-identico al vecchio `seasonal.py`)
SHA-256 `47c12da1...` uguale al valore fissato in `deploy/scripts/profit_review_audit.py`. Serve agli script di audit
(`seasonality_audit.py`, `profit_review_audit.py`) che ricostruiscono i bonus applicati nelle righe storiche: con la V2
avrebbero ricostruito bonus sbagliati. `mirror_pair_audit.py` ora accetta anche argomenti keyword.

### `backend/desk/signals.py`
`read_symbol(..., btc_return_3d=None)` passa il valore a `get_seasonal`.

### `backend/desk/cli.py` (solo Bull)
- `bull_entry_gate()`: tetto al rischio SL aggregato `BULL_MAX_OPEN_RISK_USD=160` (env `DESK_BULL_MAX_OPEN_RISK`).
  La prima posizione passa sempre; le successive solo se rischio aperto + nuovo <= 160$.
  Con 350$ x 15x e stop ~1,5-3% (84-157$ a posizione) di fatto blocca la seconda posizione finche' la prima e' aperta.
- Nessun nuovo SHORT se BTC sale piu' del 2% in 24h (`DESK_BULL_SHORT_VETO_BTC_24H`); candidati registrati come
  `rifiutata:rischio_aperto_bull` e `rifiutata:veto_short_rimbalzo_btc`.
- `_open_sl_risk()`: uno stop gia' in profitto conta zero.

### Ritirato: "daily stop attivo in paper"
Nel piano iniziale avevo indicato come bug che `_daily_loss_exceeded` non blocca in paper. **Non e' un bug**: e' una scelta
di progetto (commit `bc6c635`, test `test_daily_loss_limit_never_blocks_in_paper`) e in paper lo stop giornaliero c'e'
gia' nel motore (equity -10% dall'inizio giornata, scelta dell'utente del 21/10). Un limite sul realizzato al 25% non
sarebbe mai raggiungibile prima. `_daily_loss_exceeded` NON e' stato modificato. Il "portafoglio fermo per troppa perdita"
segnalato dall'utente era questo stop del motore che funzionava.

## Verifica
- Test nuovi: `test_desk_fixes_2026_10_26` (19: formula, curva, freno, gate) e `test_bull_guards_2026_10_26` (6 cicli
  completi Bull in paper, con controlli che mostrano che e' la guardia a fermare). Aggiunti al ciclo per-file di `desk-ci`.
- Batteria CI in locale su base `rule-pool` pulita vs modificata: nessuna regressione. Fallimenti gia' presenti prima
  (identici nei due alberi): `test_uptrend_scores_long_and_downtrend_scores_short`, `test_daily_trend_present_with_real_daily_bars`,
  `test_profit_review_audit::test_workflow_isolated_no_activation`.
- Nessuna modifica a engine.py, brain.py, prompt di Claude, soglie di confidenza, R:R, leve, margini.

## Stato (fine turno)
- Codice in `rule-pool` (merge `35f08cf`), baseline `desk-deploy.yml` portata a `63641f7` (`5151b01`) prima del deploy.
- Primo tentativo di scrivere il trigger di deploy bloccato dal controllo di sicurezza della sessione (serviva conferma diretta).
  Dopo "ok, procedi con il deploy" dell'utente: trigger `fcea423` (`sha=35f08cf...`), run `Sala segnali - deploy` #42 = SUCCESS.
- Esito: Hawk e Bull healthy, una sola istanza per bot, versione `35f08cf` dichiarata da entrambi, PAPER, backup del cervello
  verificato prima di toccare i container. Posizioni 0 prima e dopo (i bot erano fermi per lo stop giornaliero): niente da
  migrare. Primo ciclo col nuovo codice 18:33 UTC regolare; desk-status 18:36 UTC conferma.
- Nessun importo di Bitget nel diario; le cifre del paper non sono riportate.
- Prossimo: osservazione 24-48h; poi eventuali ritocchi decisi dall'utente (soglia 160$ del tetto, soglia 2% del veto).
- Dettagli e comandi: STATO.md, sezione "Fix Segnali V2".

## Dopo il deploy: reset dei portafogli (utente) e verifica
- L'utente ha azzerato i portafogli e riavviato i bot per vedere subito il comportamento col fix.
- Verifica di sola lettura (desk-status #52, 18:57 UTC): Hawk e Bull su `35f08cf`, healthy, PAPER, nuovo run con 0 chiusure,
  1 posizione aperta ciascuno (DOT SHORT SCALP, fonte `rules`). Registro di apprendimento non azzerato (contatori in crescita).
- Osservazione: i bot lavorano col fallback a regole ("Claude non disponibile"); causa da verificare in sola lettura.
- Precisazione sul tetto Bull: e' un tetto di rischio SL aggregato (160$), non di numero di posizioni.

## Calendario di Claude 14-22 (richiesta dell'utente)
- Diagnosi: budget giornaliero di Claude (0,70$ a bot) esaurito di notte; dopo, solo regole (desk-claude-finestra #3).
- Applicato il calendario 14:00-22:00 ora svizzera per 14 giorni (fino all'8/11), ramo `work/claude-finestra-14-22`, merge `e70c474`,
  workflow calendario run #4 OK, nessun riavvio. Claude ha ripreso a decidere subito su entrambi i bot.
- Da fare entro l'8/11: rinnovare il calendario, altrimenti Claude resta spento.
- Da valutare con l'utente: limite di posizioni nella stessa direzione (oggi 3 SHORT correlati su ciascun bot) e finestre spezzate per coprire le 8 ore.

## Analisi dello storico (richiesta dell'utente: perche' certi giorni vanno bene e altri no)
- Creato il workflow di sola lettura `desk-storico` (giorno per giorno, durata, lato x direzione di BTC, chiusure parziali, simulazione
  "chiudo al X% di ROI", proposte di apertura per fonte). Risultati sintetici in STATO.md. Nessun importo reale, nessuna scrittura sul server.
- Sintesi: sistema quasi solo short; funziona con discesa regolare di BTC; long mai funzionati (15 trade, 1 vincente); tutte le aperture
  vengono dalle regole; un tetto ROI al 35-40% non migliora; i profitti vengono da trade che durano oltre 6h.
- L'utente ha espresso la sua idea di trading: scalp con rotazione, molte posizioni, stessa metodologia su Hawk e Bull (uno piu' aggressivo,
  l'altro piu' prudente), long quando il mercato gira, tornare al comportamento dei primi giorni con i fix dei long, l'AI deve realizzare
  la sua ideologia (da scrivere come "carta d'intenti"). Il tetto 160$ su Bull "non e' l'idea voluta". Nessuna modifica applicata.
