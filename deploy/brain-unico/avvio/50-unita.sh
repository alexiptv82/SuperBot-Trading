#!/bin/sh
# REINSTALLA le due unita' Brain Unico sulla run GIA' ESISTENTE (creata dal pre-collaudo, conservata dal rollback) e
# le avvia SENZA mandato. Non ricrea la run, non tocca journal, budget o mandato. Codice: la cartella gia' installata
# al commit della RC, verificata file per file contro il commit. Unita' come il modello RC84 in produzione
# (Type=notify + watchdog per le uscite, runner legato alle uscite, ProtectSystem=strict, scrittura solo nella run),
# piu' il file della chiave AI del Brain (EnvironmentFile opzionale: senza mandato non si chiama comunque il modello).
# Uso (root): sh 50-unita.sh
set -eu
. "$(dirname "$0")/comune.sh"
D=$(cd "$(dirname "$0")" && pwd)
COMMIT=3440340289fdd23398f57390238daf8da3eb3fa9
STAGE=/opt/superbot-brain-unico-$(printf '%s' "$COMMIT" | cut -c1-12)
AIENV=/etc/superbot-v3-paper/brain-ai.env
[ "$(id -u)" = 0 ] || nogo "serve root"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
[ -d "$RUN" ] && [ ! -L "$RUN" ] && [ -f "$RUN/journal.db" ] && [ -f "$RUN/PREPARED_PAUSED_ONLY.json" ] \
  || nogo "run $RUN assente o incompleta (non la ricreo)"
for u in "$U_EXIT" "$U_RUN"; do [ ! -e "/etc/systemd/system/$u" ] || nogo "$u esiste gia'"; done
printf '%s  %s\n' "$CFG_SHA" "$RUN/runner_config.json" "$CFG_SHA" "$STAGE/backend/v3/runner/runner_config_brain_unico_paper_b.json" \
  | sha256sum --strict -c - >/dev/null || nogo "impronta della configurazione diversa"
"$PY" -c "import json,sys; sys.exit(0 if json.load(open('$RUN/mandate.json')).get('approved') is False else 1)" \
  || nogo "il mandato NON e' approved:false"
T=$(mktemp -d)
git -C "$LAB" archive "$COMMIT" | tar -x -C "$T"
diff -r -x __pycache__ "$T" "$STAGE" >/dev/null || { rm -rf "$T"; nogo "il codice in $STAGE non coincide con il commit $COMMIT"; }
rm -rf "$T"
EV=$("$PY" -c "import sqlite3; print(sqlite3.connect('file:$RUN/journal.db?mode=ro', uri=True).execute('select count(*) from v3_events').fetchone()[0])")
echo "run esistente $RUN: journal con $EV eventi (conservato), configurazione $CFG_SHA, mandato approved:false"
echo "codice $STAGE identico al commit $COMMIT"
if [ -f "$AIENV" ] && grep -q '^DEEPSEEK_API_KEY=.' "$AIENV"; then echo "chiave DeepSeek del Brain: presente (valore non letto)"
else echo "ATTENZIONE: chiave DeepSeek del Brain assente in $AIENV: va aggiunta prima di approvare il mandato"; fi
umask 022
cat > "/etc/systemd/system/$U_EXIT" <<UNIT
# Brain Unico PAPER rc1: servizio delle uscite (proprietario unico). Avvio esplicito, nessuna sezione Install.
[Unit]
Description=Brain Unico PAPER rc1: servizio delle uscite (proprietario unico)
After=network-online.target
Wants=network-online.target
[Service]
Type=notify
NotifyAccess=main
User=root
WorkingDirectory=$STAGE
Environment=DESK_MODE=paper
Environment=PYTHONPATH=$STAGE
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStartPre=/usr/bin/test -f $RUN/PREPARED_PAUSED_ONLY.json
ExecStart=/usr/bin/env DESK_MODE=paper $PY -m backend.v3.runner.exit_worker --data-dir $RUN --run-id $RUN_ID --config $RUN/runner_config.json --start-paper --legacy-exits-disabled
TimeoutStartSec=180
WatchdogSec=60
Restart=on-failure
RestartSec=15
RestartPreventExitStatus=2
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$RUN
UNIT
cat > "/etc/systemd/system/$U_RUN" <<UNIT
# Brain Unico PAPER rc1: runner (sidecar). Senza mandato approvato resta fermo e non spende. Avvio esplicito.
[Unit]
Description=Brain Unico PAPER rc1: runner DeepSeek (sidecar)
BindsTo=$U_EXIT
After=$U_EXIT
Requires=$U_EXIT
[Service]
Type=simple
User=root
WorkingDirectory=$STAGE
Environment=DESK_MODE=paper
Environment=PYTHONPATH=$STAGE
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=V3_BRAIN_PEER_OBSERVATIONS=disabled
EnvironmentFile=-$AIENV
ExecStartPre=/usr/bin/test -f $RUN/PREPARED_PAUSED_ONLY.json
ExecStart=/usr/bin/env DESK_MODE=paper $PY -m backend.v3.runner.wiring --data-dir $RUN --run-id $RUN_ID --config $RUN/runner_config.json --exit-mode sidecar
Restart=on-failure
RestartSec=15
RestartPreventExitStatus=2
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$RUN
UNIT
chmod 644 "/etc/systemd/system/$U_EXIT" "/etc/systemd/system/$U_RUN"
systemctl daemon-reload
systemctl start "$U_EXIT" || nogo "avvio del servizio delle uscite"
i=0; until sh "$D/30-controlli.sh" uscite >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 36 ] || nogo "uscite non sane dopo 3 minuti"; sleep 5; done
systemctl start "$U_RUN" || nogo "avvio del runner"
i=0; until sh "$D/30-controlli.sh" tutti >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 60 ] || { sh "$D/30-controlli.sh" tutti; nogo "controlli non superati dopo 5 minuti"; }; sleep 5; done
sh "$D/30-controlli.sh" tutti
echo "UNITA' INSTALLATE E AVVIATE SENZA MANDATO: $U_EXIT (sano), $U_RUN (halted per il mandato, nessuna spesa)"
