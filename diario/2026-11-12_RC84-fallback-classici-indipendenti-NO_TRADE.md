# RC84 — 12 novembre 2026, indipendenza Falco/Toro e NO_TRADE

## Contesto verificato
- Il collaudo della PR Draft #85 mostrato dall'utente ore 06:08 e 06:31 Europe/Rome ha superato **239 + 156 = 395 test selezionati**. Il codice di questa PR **non era ancora distribuito** sui bot attivi.
- La VPS Singapore aveva tre `pause.flag` PAPER creati manualmente alle 05:05 per bloccare nuove aperture senza chiudere posizioni. Non rimuovere durante la riparazione.
- Restava il difetto strutturale: `backend/desk/cli.py` chiamava lo stesso `rules_decisions` per Falco e Toro in assenza di una decisione Claude; segnali uguali potevano aprire due operazioni identiche anche dopo aver spento la strategia automatica LONG S25.
- Ulteriore bug: `{"decisions":[]}` era un JSON valido senza posizioni, ma veniva erroneamente interpretato come assenza di decisioni e sostituito da fallback regole. Questo annullava un NO_TRADE intenzionale.

## Patch preparata, SOLO RAMO DI LAVORO, NON DEPLOY
- Branch `work/rc84-fix-classic-divergence-brain-market-20261111`, HEAD finale **`fbbd016dfa58129b84886cea0be89c81c64777ed`**, PR [Draft #85](https://github.com/alexiptv82/SuperBot-Trading/pull/85).
- `backend/desk/cli.py` nuova funzione pura `_rc84_paper_classic_entry_policy(portfolio,source,decisions)` che filtra soltanto **nuovi ingressi**: Falco ammette ingressi LONG/SHORT di tipo `scalp` sia da Claude sia dalle regole, Toro ammette ingressi LONG/SHORT di tipo `medio` **solo da Claude** (fallback regole in Toro **manage/close/hold, mai nuove aperture**).
- Ingressi con `trade_type` non conforme sono scartati con diagnostica di sola stampa `[RC84_POLICY]`, il totale appare in `HB["rc84_policy_rejected"]`. Nessuna posizione aperta viene chiusa forzatamente o trasformata in una direzione opposta; entrambi possono fare LONG/SHORT quando autorizzati dai segnali.
- Risposta Claude valida `{"decisions":[]}` conserva `NO_TRADE` e **non richiama fallback**. Anche un eventuale futuro `DESK_S25_TORO_ENTRY_APPROVED=1` non deve sovrascrivere il NO_TRADE. Valori non validi/JSON troncati restano fallback, ma **solo** secondo la policy dei due portafogli.
- Il filtro è applicato esclusivamente con `not LIVE._live` per non modificare accidentalmente un'eventuale futura installazione con soldi veri. Deve essere riesaminato prima di qualunque passaggio LIVE.
- Gli stop protettivi, uscite a tempo S25 pregresse, pause, equity, DCA e risk manager continuano a usare le logiche preesistenti. `Brain` non è toccato da questa patch.

## Test aggiunti (NON ANCORA ESEGUITI)
File `backend/tests/test_long_s25.py`: politica di fallback differenziata, direzioni LONG e SHORT non bloccate, gestione delle posizioni lasciata invariata, ciclo sintetico con identico segnale rules (Falco scalp apre, Toro NO), test di risposta Claude valida vuota su Falco e Toro anche con eventuale S25 abilitata. **Non dichiarare passanti questi test finché l'utente non manda output.**

## Prossima azione
L'utente si trova nel clone isolato `/root/rc84-tests-UKXAJfmd/src` con virtualenv `.venv`. Usare un solo comando:
```bash
git pull --ff-only origin work/rc84-fix-classic-divergence-brain-market-20261111 &&
test "$(git rev-parse HEAD)" = "fbbd016dfa58129b84886cea0be89c81c64777ed" &&
PYTHONPATH="$PWD:$PWD/backend" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/python -m pytest -q backend/tests/test_long_s25.py
```
Solo dopo PASS, fare una verifica strategia SHORT/LONG indipendente e programmare backup+deploy PAPER con verifica unica proprietà delle uscite e collaudo DeepSeek reale, senza inutili suite ripetute. **No merge, no reset, no riavvio, LIVE vietato** fino a controllo e autorizzazione. GitHub Actions quota bassa/in coda.
