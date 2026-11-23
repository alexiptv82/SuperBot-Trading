#!/bin/sh
# Installa e avvia le unita' delle DUE run (uscite + runner) SENZA mandato: le uscite sono sane, il runner resta fermo
# per il mandato (nessuna spesa, nessuna apertura). Modello RC1 in produzione. Uso: sh 50-unita.sh <sha>
set -eu
. "$(dirname "$0")/comune.sh"
D=$(cd "$(dirname "$0")" && pwd)
STAGE=$(stage_of "${1:-}")
[ "$(id -u)" = 0 ] || nogo "serve root"
[ -d "$STAGE/backend" ] || nogo "codice $STAGE assente"
check() {  # run run_id modo
  (cd "$STAGE" && DESK_MODE=paper PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$PY" "$D/controlli.py" "$1" "$2" "$3")
}
units() {  # etichetta cartella run_id unita_uscite unita_runner
  RUN="$PARENT/$2"; ID=$3; UE=$4; UR=$5
  for u in "$UE" "$UR"; do [ ! -e "/etc/systemd/system/$u" ] || nogo "$u esiste gia'"; done
  [ -f "$RUN/PREPARED_PAUSED_ONLY.json" ] || nogo "$2 non preparata"
  umask 022
  cat > "/etc/systemd/system/$UE" <<UNIT
# $1 PAPER: servizio delle uscite (proprietario unico). Avvio esplicito, nessuna sezione Install.
[Unit]
Description=$1 PAPER: servizio delle uscite (proprietario unico)
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
ExecStart=/usr/bin/env DESK_MODE=paper $PY -m backend.v3.runner.exit_worker --data-dir $RUN --run-id $ID --config $RUN/runner_config.json --start-paper --legacy-exits-disabled
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
  cat > "/etc/systemd/system/$UR" <<UNIT
# $1 PAPER: runner (sidecar). Senza mandato approvato resta fermo e non spende. Avvio esplicito.
[Unit]
Description=$1 PAPER: runner (sidecar)
BindsTo=$UE
After=$UE
Requires=$UE
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
ExecStart=/usr/bin/env DESK_MODE=paper $PY -m backend.v3.runner.wiring --data-dir $RUN --run-id $ID --config $RUN/runner_config.json --exit-mode sidecar
Restart=on-failure
RestartSec=15
RestartPreventExitStatus=2
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$RUN
UNIT
  chmod 644 "/etc/systemd/system/$UE" "/etc/systemd/system/$UR"
  systemctl daemon-reload
  systemctl start "$UE" || nogo "$1: avvio del servizio delle uscite"
  i=0; until check "$RUN" "$ID" uscite >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 36 ] || nogo "$1: uscite non sane dopo 3 minuti"; sleep 5; done
  systemctl start "$UR" || nogo "$1: avvio del runner"
  i=0; until check "$RUN" "$ID" tutti >/dev/null 2>&1; do i=$((i+1)); [ $i -lt 60 ] || { check "$RUN" "$ID" tutti; nogo "$1: controlli non superati dopo 5 minuti"; }; sleep 5; done
  check "$RUN" "$ID" tutti
  echo "PASS  $1: $UE sano, $UR fermo per il mandato (nessuna spesa, nessuna apertura)"
}
units "Falco Evoluto" "$F_DIR" "$F_ID" "$U_F_EXIT" "$U_F_RUN"
units "Brain Scalp" "$S_DIR" "$S_ID" "$U_S_EXIT" "$U_S_RUN"
