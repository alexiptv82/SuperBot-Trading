# DIAGNOSI DAILY STOP — Analisi read-only engine.py + cli.py
### Risultato dell'audit di codice sui classici Hawk/Bull

**Autore:** Claude Sonnet 4.6 — 29 ottobre 2026
**Branch letto:** `rule-pool` @ `dc16e01` (versione in produzione)
**Stato:** READ-ONLY — nessuna modifica a codice, deploy, VPS, dati.

---

## VERDETTO PRINCIPALE

**Esistono DUE percorsi di daily-stop con comportamenti diversi.**
**I bot classici girano sul percorso LEGACY, in cui `halted()` non ha memoria (stateless): questo è un FATTO verificato nel codice. Che il 29/10 si sia davvero verificato un re-enable intraday NON è provato: servono i log dei trade (vedi "Cosa dicono i numeri del 29/10").**

> **Correzione 29/10 ore 09:5x:** la prima stesura di questo documento sosteneva che il bug fosse "confermato" e che spiegasse "perfettamente" le perdite del 29/10, e che DCA/seconda gamba bypassassero il gate. Rileggendo il codice (`engine.py` righe 308 e 407) il bypass DCA è FALSO, e la spiegazione delle perdite era sovrastimata. Le sezioni sotto sono state riscritte di conseguenza.

---

## PERCORSO 1 — Capital V1 (OFF sui classici attuali)

`capital_manager.py` contiene `latch_risk()`:

```python
def latch_risk(ref: DayReference, equity: object) -> DayReference:
    """Latch even if market rebounds; daily-stop clears only on valid UTC rollover."""
    if risk_view(ref, equity).stop_latched and not ref.stop_latched:
        return replace(ref, stop_latched=True, revision=ref.revision + 1)
    return ref
```

`DayReference.stop_latched` è un campo persistente. Una volta che si attiva, rimane `True` fino al `rollover` del giorno UTC. Non può disarmarsi per recupero equity intraday.

**Questo è il comportamento CORRETTO. Ma Capital V1 è OFF.**

---

## PERCORSO 2 — Legacy 12% (attivo sui classici)

`engine.py` → `halted()`:

```python
def halted(self, prices: dict) -> str:
    eq = self.equity(prices)
    if self._capital_reference is not None:   # ← Capital V1, è None → skip
        ...
    if eq <= self.limits.kill_equity:
        return "capitale sotto la soglia minima"
    if eq <= self.day_start_equity * (1 - self.limits.daily_stop):
        return "stop giornaliero raggiunto"
    return ""  # ← torna stringa vuota se equity recupera!
```

`halted()` è una funzione **stateless**: ricalcola ogni volta dall'equity corrente. Non esiste `halt_latched` nel percorso legacy.

`cli.py` chiama `halted()` ogni ciclo:

```python
halt = acc.halted(prices)
if halt:
    if not state.get("halt_notified"):
        notify_halt(halt)
        state["halt_notified"] = True
else:
    # Reset flag quando il halt viene rimosso (es. nuovo giorno / resume)
    state.pop("halt_notified", None)
```

**`halt_notified` impedisce solo di spammare la notifica, non blocca le aperture.**
Il ciclo successivo, se `halted()` ritorna `""`, le aperture ripartono.

---

## SEQUENZA DI FALLIMENTO DOCUMENTATA (ipotesi verificabile)

```
Ciclo N:    equity < 0.88 × day_start_equity
            → halted() = "stop giornaliero raggiunto"
            → notify_halt() (una volta)
            → state["halt_notified"] = True
            → nessuna apertura questo ciclo ✓

Ciclo N+1:  posizione floating va in gain temporaneo
            → equity > 0.88 × day_start_equity
            → halted() = ""           ← GATE DISARMATO
            → state.pop("halt_notified")
            → nuova apertura PERMESSA  ← BUG

Ciclo N+2:  mercato ritorna contro → equity crolla
            → halted() = "stop giornaliero raggiunto"
            → notify_halt() di nuovo
            → ma la posizione è già aperta nel ciclo N+1
```

**Vincolo importante sul meccanismo:** le perdite già REALIZZATE (posizioni chiuse) non possono far "risalire" l'equity sopra soglia. Il gate può disarmarsi solo se il P&L flottante di posizioni ancora aperte torna positivo abbastanza da riportare `equity` sopra `0,88 × day_start_equity`. Con poche posizioni aperte la finestra è stretta. Quindi la mancanza di latch è un punto debole reale ma di impatto probabilmente limitato; non basta da sola a spiegare perdite molto oltre il 12%.

## COSA DICONO I NUMERI DEL 29/10 (calcolo dagli screenshot, non dai log)

Il cruscotto calcola "P&L oggi" come `equity - day_start_equity` (`cli.py` riga 935), quindi la base di giornata si ricava per differenza:

| | Hawk #7 | Bull #6 |
|---|---:|---:|
| Equity 08:07 | 698,86 | 673,48 |
| P&L oggi | -145,89 | -205,67 |
| `day_start_equity` ricavato | ~844,75 | ~879,15 |
| Soglia stop (0,88 × base) | ~743,4 | ~773,6 |
| Perdita di giornata / base | **17,3%** | **23,4%** |
| Equity sotto la soglia di | ~44,5 | ~100,1 |

Riscontro: la base Bull ricavata (~879,15) coincide con l'equity Bull dello screenshot del 28/10 (879,16), quindi la perdita Bull è tutta successiva a quello screenshot e alla mezzanotte UTC. La prima stesura di questo documento calcolava -14,5% e -20,5% dividendo per 1.000: era sbagliato, la base corretta è quella di inizio giornata.

Entrambi hanno quindi superato lo stop di una misura notevole (Bull di quasi 100 USD). Spiegazioni compatibili, NON distinguibili senza i log:
1. **Posizioni già aperte quando lo stop è scattato**: lo stop blocca solo le nuove aperture, quindi più posizioni aperte che chiudono a SL dopo il superamento fanno scivolare la perdita oltre il 12%. Con Bull a 3 slot, margini 150-350 e leva fino a 15x è plausibile.
2. **Controllo solo a cadenza di ciclo (15 min) sulle barre chiuse**: tra un controllo e l'altro più SL possono scattare insieme.
3. **Re-enable intraday** per assenza di latch: possibile ma richiede floating positivo temporaneo; da provare con l'ordine cronologico di aperture e chiusure.
4. **Evento singolo grande** (liquidazione o gap): ChatGPT ha già segnalato casi LIQ prima di Fix A (NEAR SHORT -101,50, INJ LONG -194,88).

Dato utile per discriminare: Bull passa da 4 a 7 chiusi tra le 21:56 del 28/10 e le 08:07 del 29/10, cioè solo 3 chiusure per -205,67 (circa -68 a chiusura). Una perdita media di quella taglia per singola chiusura fa pensare a SL su margini alti o a liquidazione, più che a una raffica di piccole perdite. Va verificata sui dati reali (il conteggio dashboard può contare realizzi parziali, non posizioni complete).

---

## SECONDO PUNTO: DCA E SPLIT BYPASSANO IL GATE? — NO (verificato)

Nel codice `engine.py` il DCA controlla `_capital_reference` (Capital V1):

```python
blocked = bool(self._capital_reference and self._capital_reference.stop_latched)
```

Con `_capital_reference = None` (Capital V1 OFF), questo blocco è `False` sempre.

**Verificato: NO, nel percorso legacy DCA e seconda gamba sono bloccati.** Il blocco `_capital_reference` qui sopra riguarda solo il dimensionamento Capital V1 (inattivo), ma i due punti di esecuzione controllano direttamente `halted()`:

- `add_dca()` (`engine.py` riga 308): `halt = self.halted(prices)`, se non vuoto ritorna `"<motivo>: DCA bloccato"`.
- `_fill_split()` (`engine.py` riga 407): `halt = self.halted(marks)`, se non vuoto annulla la seconda gamba con `"<motivo>: seconda gamba bloccata"`.

Anche `open()` (riga 229) controlla `halted()`. Quindi tutte e tre le vie di nuovo rischio sono coperte dal gate legacy. Resta solo la fragilità comune: poiché `halted()` è stateless, se il gate si disarma si riaprono insieme nuove entrate, DCA e seconde gambe.

Verifica sui dati reali (non possibile da questa sessione): cercare in `trade_history.jsonl` e nei log eventi sequenze `halt → apertura/DCA/seconda gamba` nello stesso giorno UTC.

---

## IMPATTO

I valori corretti sono nella sezione "Cosa dicono i numeri del 29/10" (perdita di giornata 17,3% Hawk e 23,4% Bull rispetto alla base di inizio giornata, contro uno stop al 12%). L'impatto specifico del mancato latch NON è quantificabile da screenshot: la prima stesura riportava una "stima conservativa" di 50-150 USD per posizione riaperta, che era un'ipotesi senza base nei dati e va ignorata.

---

## PROPOSTA DI FIX (concettuale, no modifica ora)

### Fix minimo — solo percorso legacy

```python
# In PaperAccount:
def __init__(self, ...):
    ...
    self._halt_latched_day: Optional[str] = None  # UTC day del latch

def roll_day(self, day: str, prices: dict) -> None:
    if day != self.day:
        self.day, self.day_start_equity = day, self.equity(prices)
        # Latch si resetta SOLO al cambio giorno UTC
        self._halt_latched_day = None

def halted(self, prices: dict) -> str:
    eq = self.equity(prices)
    if self._capital_reference is not None:  # Capital V1 path (invariato)
        ...
    if eq <= self.limits.kill_equity:
        return "capitale sotto la soglia minima"
    # Latch: se già scattato oggi, rimane fino a mezzanotte UTC
    if self._halt_latched_day == self.day:
        return "stop giornaliero raggiunto"
    if eq <= self.day_start_equity * (1 - self.limits.daily_stop):
        self._halt_latched_day = self.day  # primo trigger: latch
        return "stop giornaliero raggiunto"
    return ""
```

**Invarianti del fix:**
1. `_halt_latched_day` è stringa UTC del giorno (`"2026-10-29"`), non un bool
2. Si resetta a `None` in `roll_day()` — solo il cambio giorno UTC lo sblocca
3. Non modifica il percorso Capital V1 (già corretto)
4. Non richiede migrazione stato: `_halt_latched_day = None` al boot è comportamento sicuro (ma se il bot riavvia intraday dopo un latch, il latch si perde — serve persistenza nel `state.json`)

**Test offline necessari prima di deploy:**
1. Unit test: sequenza halt → price recovery → verify still halted → roll_day → verify unlocked
2. Test DCA con halt attivo: verifica che DCA non bypassa nel percorso legacy
3. Test riavvio intraday: se bot crasha e riavvia dopo halt, latch deve essere ripristinato da `state.json`

---

## ALTRI PROBLEMI TROVATI NELL'AUDIT

### Problema 2: `halt_notified` si resetta quando halt scompare

```python
else:
    state.pop("halt_notified", None)
```

Se il gate si riabilita (bug sopra), la notifica verrà mandata di nuovo al prossimo trigger. Quindi l'utente potrebbe ricevere **più notifiche halt nello stesso giorno** — già questo è un segnale diagnostico: se Hawk/Bull hanno mandato più notifiche halt lo stesso UTC day, il re-enable è avvenuto.

**Azione read-only immediata:** verificare quante volte `notify_halt` è stato chiamato nei log di sistema il 29/10.

### Problema 3: `day_start_equity` al rollover include floating su posizioni aperte

```python
def roll_day(self, day: str, prices: dict) -> None:
    if day != self.day:
        self.day, self.day_start_equity = day, self.equity(prices)
```

`self.equity(prices) = cash + margin_in_use + unrealized(prices)`

Se a mezzanotte UTC ci sono posizioni aperte con floating positivo, `day_start_equity` è gonfiato. Il giorno dopo, se il floating scompare (mercato si inverte), il gate scatta **prima** del previsto (la base era artificiamente alta). Viceversa, floating negativo abbassa la base e il gate scatta **più tardi**.

Con leva 15x su BTC, un movimento del 1% su una posizione da 150$ margine sposta 150×15×0.01 = 22.50$ di floating. Su un account da 700$, questo è 3.2% di variazione del `day_start_equity` a seconda di dove si trovava BTC a mezzanotte UTC.

**Non è un bug critico, è un rischio noto che va documentato.**

---

## PROSSIMI PASSI PROPOSTI

### Immediato (read-only, ora)
1. ✅ **Fatto**: audit `engine.py` + `capital_manager.py` + `cli.py`. Confermata la mancanza di latch nel percorso legacy; smentito il bypass DCA/split.
2. **Da fare, ma non accessibile da questa sessione**: `trade_history.jsonl` e stato di Hawk #7 / Bull #6 sono sulla VPS. Serve che qualcuno con accesso li esporti in sola lettura, oppure che tu me li alleghi.

### Con OK utente (branch isolato, no deploy)
3. Implementare unit test del bug: sequenza che dimostra il re-enable
4. Implementare e testare il fix minimo su branch isolato
5. Verificare che il fix non rompa i test CI esistenti

### Con OK utente separato (deploy)
6. Deploy del fix con backup + restore + postflight heartbeat

---

**CONCLUSIONE OPERATIVA**

**Fatto verificato nel codice:** nel percorso legacy `halted()` non ha memoria e si disarma appena l'equity (flottante incluso) torna sopra `0,88 × day_start_equity`. Capital V1 ha invece `latch_risk()` persistente fino al rollover UTC, ma è OFF sui classici. DCA, seconda gamba e `open()` sono tutti coperti dal gate.

**NON verificato:** che questa debolezza abbia causato le perdite del 29/10. Quelle sono compatibili anche con posizioni già aperte che chiudono a SL dopo il superamento della soglia (lo stop non chiude nulla), con il controllo a cadenza di ciclo, o con un evento singolo grande. Per distinguere servono aperture e chiusure in ordine cronologico UTC con l'equity a ogni passo, che stanno in `trade_history.jsonl`/stato sulla VPS e che questa sessione non può leggere.

**Raccomandazione rivista:**
1. Prima la prova sui dati: far estrarre in sola lettura (da chi ha accesso, o con un tuo file) le righe di apertura/chiusura di Hawk #7 e Bull #6 dalle 00:00 UTC del 29/10, con `day_start_equity`.
2. Il latch resta una modifica sensata e a basso rischio (stringe soltanto), ma è comunque una modifica a un limite di rischio: per le regole del repository (punto 3) richiede una tua decisione esplicita, e un deploy richiede un OK separato (punto 1).
3. Per ottenere il latch NON attivare Capital V1: porterebbe lo stop al 20% invece del 12% (`DAILY_LOSS_PCT = 0.20` in `capital_manager.py`), cioè più largo di oggi.

AI: Claude Sonnet 4.6
