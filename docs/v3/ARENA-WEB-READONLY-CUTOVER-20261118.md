# AI Arena: web in sola lettura per l'app Samsung (cutover del solo container web)

Ramo `work/arena-web-readonly-cutover-20261118` (PR in bozza, base PR #110). **Nulla di questo documento è stato
eseguito sul VPS.** La gara PAPER di 72 ore è in corso e non viene toccata: runner, servizi uscite, journal, Brain
storico, nginx, DESK_MODE e credenziali restano come sono. Nessun APK nuovo, nessuna chiusura manuale.

## Diagnosi (da screenshot del 18/11, 18:21)

L'immagine web in uso (`superbot:brain-close-ro-candidate-20261115`) è anteriore all'integrazione Arena: il lettore
`read_view.py` e la rotta `GET /api/v3/arena` **non esistono nel codice dell'immagine**. Non bastano variabili d'ambiente
o mount. In più il container non monta `/opt/superbot-ai-arena-paper` e la UI statica dice ancora "14 giorni".

## Cosa fa la soluzione (e cosa evita)

| Scelta | Perché |
|---|---|
| L'immagine candidata parte dall'**ID dell'immagine in uso** (nessun pull) e aggiunge **5 file** Arena + **21 righe** in `v3_api.py` | Non si assume che HEAD del repo riproduca l'immagine. Login, impronta, sessioni (JWT con chiave nel DB `/app/data`) e fix correnti restano quelli dell'immagine |
| Le 21 righe sono estratte dal `v3_api.py` del repo, **senza il ramo di chiusura manuale**, e verificate per hash | Nell'immagine non esiste nessuna rotta di scrittura Arena, nemmeno con flag futuri. `POST/PUT/DELETE` → 405 |
| `v3_api.py` dell'immagine è **modificato in un solo punto** (ancora unica, rifiuto se ambigua o se contiene già codice Arena) | Patch chirurgica, non sostituzione |
| La prova prima dello switch gira in un **container usa-e-getta senza rete** che **non avvia `server.py`** | `server.py` all'avvio crea il polling Telegram (`notifier.poll_commands`): un secondo web completo su una porta parallela lo duplicherebbe e potrebbe disturbare quello vivo. Per questo la "prova su porta parallela" è sostituita da una prova ASGI con la dipendenza di sessione vera, su una **copia** del DB di sessioni, con tutti i mount `:ro` |
| Il nuovo container è creato **prima** di toccare il vecchio e confrontato campo per campo | Se differisce in qualunque campo (limiti di risorse, capability, log, rete, porte, utente, mount, ambiente) si rifiuta **senza aver fermato nulla** |
| Il vecchio container resta **fermo e rinominato** + immagine precedente con tag di conservazione + copia 0600 dell'`inspect` | Rollback in un comando |
| Rollback **automatico** se dopo lo switch fallisce uno qualunque dei controlli | Vedi sotto |

Gli unici cambiamenti rispetto al container attuale: mount `/opt/superbot-ai-arena-paper` **in sola lettura**, le variabili
`V3_ARENA_READONLY_ENABLED=1` e `V3_ARENA_TRIAL_DAY=2026-11-18`. Porta `127.0.0.1:8002` invariata (mai 0.0.0.0).

## Provato qui, in locale

* Modello dell'immagine = albero del repository all'11/11 (ultimo commit prima dell'integrazione Arena), Python 3.12,
  SQLAlchemy 2.0.28, FastAPI 0.110.0 (come `requirements.txt`).
* Test end-to-end con **vero bind mount in sola lettura** di tre run attivate con T0 comune:
  1. immagine non patchata (lo stato reale del VPS): la sonda la **rifiuta** (`arena_routes_unexpected`);
  2. immagine patchata ma Arena non montata: rifiutata (`journal_not_verified`);
  3. immagine patchata + mount ro: `GET /api/v3/arena` → **401 senza sessione, 401 con sessione falsa, 200 con sessione
     vera** (JWT firmato con la chiave del DB), 3 portafogli, **stesso T0**, rotta solo GET, `POST/PUT/DELETE` non
     raggiungibili, **nessun file Arena modificato** (hash prima/dopo).
* Orchestrazione con Docker finto: sostituzione riuscita, ambiente e mount conservati, segreto mai stampato né salvato
  fuori dalla copia 0600; rifiuto prima di toccare qualcosa se la configurazione differisce; rollback automatico per sonda
  live, percorso pubblico, comportamento cambiato, container non sano, PID dei servizi cambiati, avvio fallito;
  rollback manuale idempotente; recupero dopo sessione persa (due punti d'interruzione).
* Ha trovato e corretto due difetti: l'output di `docker run cat` veniva tagliato (`strip`) alterando il file; la pulizia di
  `--prepare` poteva cancellare un candidato valido già esistente.

## NON provato (richiede il VPS)

* L'immagine **vera**: il modello è ricostruito dalla storia git. `--inspect` confronta gli hash dei file condivisi e prova
  l'ancora di patch **sul `v3_api.py` reale** prima di costruire qualsiasi cosa; `--prepare` prova l'import e la rotta
  nell'immagine candidata vera con l'ambiente vero.
* Il comportamento di SQLite/mount su filesystem e Docker del VPS; la memoria disponibile per il container di prova (1 GB).
* Il passaggio nginx pubblico, la UI sul Samsung, il tempo reale di fermo del web (stimato: pochi secondi).

## Procedura (ogni fase richiede l'OK esplicito dell'utente; da `systemd-run` o `tmux`)

```
SHA=<commit revisionato, 40 caratteri>
SRC=/opt/superbot-arena-ui-builds/web-cutover-${SHA:0:8}
sudo git clone --quiet --no-tags --single-branch --depth 60 --branch work/arena-web-readonly-cutover-20261118 \
  https://github.com/alexiptv82/SuperBot-Trading.git "$SRC"
sudo git -C "$SRC" checkout --quiet --detach "$SHA"
C="$SRC/deploy/scripts/arena-web-readonly-cutover-20261118.py"
```

**1. Sola lettura** (nessuna modifica):
`sudo python3 $C --inspect --source-root $SRC --sha $SHA`
Atteso: `arena_flags_absent=TRUE`, `overlay_*=MISSING_IN_IMAGE_OK`, `shared_closure_missing=NONE`,
`patch_anchor_test=PASS`, `web_untouched=TRUE`. Rifiuti previsti: immagine con ID diverso da quello atteso (stampa
quale: va rivista, non forzata), flag Arena già presenti, mount Arena già presente, porta diversa da `127.0.0.1:8002`.
`shared_closure_differs` elenca i moduli condivisi diversi dal repo: informativo, decide la prova di import.

**2. Costruzione e prova dell'immagine candidata** (nessun traffico, nessuna modifica al web):
`sudo systemd-run --unit=arena-web-prepare --collect --wait --pty python3 $C --prepare --source-root $SRC --sha $SHA`
Atteso: `probe_RESULT=PASS_CANDIDATE`, `probe_arena_routes=GET_ONLY`, `candidate_image=sha256:...`,
`RESULT=CANDIDATE_READY_FOR_SEPARATE_PUBLISH`. Annotare `candidate_image`. In caso di errore le etichette create da
questa esecuzione vengono rimosse; un candidato già esistente non viene mai cancellato.

**3. Sostituzione del solo container web** (fermo di pochi secondi):
`sudo systemd-run --unit=arena-web-publish --collect --wait --pty python3 $C --publish --source-root $SRC --sha $SHA --candidate-id sha256:<annotato>`
Ordine interno: preflight e nuova sonda → backup in `/opt/superbot-v3-backups/arena-web-before-<data>` (inspect 0600,
mount, comportamento prima) → tag di conservazione dell'immagine precedente → `docker create` del nuovo container **senza
avviarlo** e confronto campo per campo → solo allora stop del vecchio, rename, avvio → verifiche: salute, comportamento
identico a prima sulle rotte non autenticate (`/api/health`, `/api/auth/webauthn/status`, `/api/v3/overview`,
`/api/v3/brain/config`, `/api/v3/brain/status`), sonda live nel container (sessione vera mintata dentro il container:
`/api/v3/arena` 401 senza sessione, 200 con sessione, 3 portafogli, T0 identico), percorso pubblico via nginx locale
(`/api/health` 200, `/api/auth/webauthn/status` 200, `/api/v3/arena` 401), PID dei servizi systemd **invariati**.
Atteso: `RESULT=WEB_UPDATED_ARENA_READONLY`. Se un controllo fallisce: rollback automatico, il container fallito viene
**conservato fermo** (`superbot-arena-web-rejected-*`, per i log).

**4. Rollback / recupero** (idempotente; vale anche dopo una sessione persa a metà):
`sudo python3 $C --rollback` → `RESULT=PREVIOUS_WEB_RESTORED`.
Gestisce: dopo un publish riuscito, dopo SIGKILL tra stop e rename, dopo creazione senza avvio. Non cancella nulla.
Rifiuta se il container attivo non è né il precedente né il candidato (non indovina).

**5. UI statica** (solo dopo il punto 3; il rilascio rifiuta se `/api/v3/arena` risponde 404):
```
sudo bash $SRC/deploy/scripts/arena-web-ui-readonly-preflight-20261118.sh --sha $SHA
# stampa CANDIDATE_BUILD, INDEX_SHA256 (nuova) e CURRENT_PUBLIC_INDEX_SHA256 (attuale)
sudo bash $SRC/deploy/scripts/arena-web-ui-readonly-release-rollback-20261118.sh --activate \
  --candidate <CANDIDATE_BUILD> --new-sha <INDEX_SHA256> --old-sha <CURRENT_PUBLIC_INDEX_SHA256>
```
Il preflight esegue test e build in un container Node senza rete con `REACT_APP_BRAIN_ARENA_SHADOW_API=1`, backend
same-origin, **tutti i controlli di chiusura a 0**. Il rilascio fa backup verificato di `/opt/superbot-web/build`,
**conserva manifest, service worker e icone attuali** (identità della PWA), non riavvia nginx né container, e torna
indietro da solo se web, endpoint impronta, rotta Arena o Brain non rispondono come prima.
UI: `... --rollback --new-sha <INDEX_SHA256> --old-sha <CURRENT_PUBLIC_INDEX_SHA256>`.
Il service worker è network-first per le pagine e gli asset hanno hash nel nome: la nuova UI compare al primo
ricaricamento dell'app (chiudere e riaprire se mostra ancora "14 giorni").

## Cosa vedrai nell'app (e cosa no)

Per ciascuna AI: stato, T0, capitale iniziale, PnL realizzato, PnL del giorno, win rate, trade chiusi (motivo, PnL),
posizioni aperte (lato, leva, entry, stop, margine), decisioni e no-trade. Aggiornamento automatico ogni 30 secondi.
**Limite noto del lettore esistente:** con posizioni aperte l'equity è "non valutata" e il PnL non realizzato è "n.d."
(nessuna quotazione verificata nel journal, nessun numero inventato). Una stima a mercato richiede una modifica
separata del lettore, da decidere.

## Ripiego senza web e senza app (disponibile subito, in sola lettura)

```
sudo env PYTHONPATH=/opt/superbot-arena-stage:/opt/superbot-arena-stage/backend \
  /opt/superbot-arena-stage/.venv/bin/python3 -s -m backend.v3.arena.readout_cli --day 2026-11-18
```
Tabella per AI con stato, T0, PnL, aperte e ultime chiuse; `--json` per il dato grezzo. Stesso lettore verificato della
dashboard; non scrive, non usa rete né crediti. Il codice è nello stage solo dopo un aggiornamento dello stage: finché non
c'è, usare un checkout pinned come sopra (`PYTHONPATH=$SRC:$SRC/backend`, python di sistema).

## Rischi residui

* Il web resta fermo pochi secondi durante lo switch; la gara non dipende dal web. Il polling Telegram del web si
  interrompe in quei secondi, come a ogni riavvio.
* La prova pre-switch passa l'ambiente del container (con i suoi segreti) a un container **senza rete**, per consentire
  l'import di `config`; nulla viene stampato e il file d'ambiente 0600 è cancellato a fine esecuzione.
* Le sessioni esistenti restano valide (chiave JWT e `token_version` sono nel DB montato, invariato). Se per qualunque
  motivo il DB cambiasse, serve un nuovo accesso con password/impronta, come oggi.
* Se `--inspect` rivela un'immagine diversa da quella attesa, **fermarsi**: la procedura non forza nulla.
