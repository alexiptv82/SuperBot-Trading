#!/usr/bin/env bash
# Authorized install of two DISABLED, INACTIVE PAPER-only services.
# No legacy writes, no process starts, no bot activation, no auto-close.
set -euo pipefail
umask 077
STAGE=/opt/superbot-v3-rc70-stage
SNAP=/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218
if [[ "${1:-}" != "--install-disabled-only" ]]; then echo RC70_UNITS_NO_EXPLICIT_FLAG; exit 2; fi
test -f "$STAGE/preview-installed.flag" || { echo RC70_PREVIEW_NOT_READY; exit 2; }
test -d "$STAGE/backend/desk" && test -s "$STAGE/backend/desk/exit_only.py" || { echo RC70_WORKER_CODE_NOT_PRESENT; exit 2; }
test -s "$SNAP/MANIFEST.json" || { echo RC70_BACKUP_NOT_VERIFIED; exit 2; }
for n in hawk bull; do
  D=/opt/superbot-desk-data/$n
  test "$(docker inspect -f '{{.State.Running}}' superbot-desk-"$n")" = false || { echo RC70_LEGACY_ACTIVE; exit 2; }
  test "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' superbot-desk-"$n")" = no || { echo RC70_LEGACY_RESTART; exit 2; }
  test -f "$D/pause.flag" || { echo RC70_LEGACY_UNPAUSED; exit 2; }
  for f in state_v2.json trade_history.jsonl learning_log.jsonl lessons.md; do
    test "$(sha256sum "$D/$f" | cut -d' ' -f1)" = "$(sha256sum "$SNAP/$n/$f" | cut -d' ' -f1)" || { echo RC70_SNAPSHOT_STALE; exit 2; }
  done
  for f in reset.flag reset.flag.work close_position.flag close_position.flag.work; do
    test ! -e "$D/$f" || { echo RC70_PENDING_REQUEST_BLOCK; exit 2; }
  done
done
for n in falco toro; do
  test ! -e "/etc/systemd/system/superbot-v3-$n-exit.service" || { echo RC70_UNIT_ALREADY_PRESENT; exit 2; }
  test "$(systemctl is-active "superbot-v3-$n-exit.service" 2>/dev/null || true)" != active || { echo RC70_UNIT_ALREADY_RUNNING; exit 2; }
done
if [ ! -x "$STAGE/.venv/bin/python3" ]; then
  python3 -m venv "$STAGE/.venv"
  "$STAGE/.venv/bin/python3" -m pip install --disable-pip-version-check --no-input --quiet 'numpy>=1.26,<3' >/dev/null
fi
DESK_MODE=paper DESK_PORTFOLIO=hawk DESK_DATA_DIR="$STAGE/data" \
  PYTHONPATH="$STAGE/backend" PYTHONDONTWRITEBYTECODE=1 \
  "$STAGE/.venv/bin/python3" -c 'from desk import cli; from desk.exit_only import ExitOnlyWorker; assert cli.LIVE._live is False' >/dev/null
echo RC70_EXIT_ONLY_IMPORT_PASS=True
for n in falco toro; do
  if [ "$n" = falco ]; then p=hawk; else p=bull; fi
  unit="/etc/systemd/system/superbot-v3-$n-exit.service"
  cat > "$unit" <<SERVICE
[Unit]
Description=SuperBot V3 $n PAPER manual exit-only worker (no strategy, no opens)
After=docker.service
ConditionPathExists=/opt/superbot-desk-data/$p/pause.flag

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$STAGE
Environment=DESK_MODE=paper
Environment=DESK_PORTFOLIO=$p
Environment=DESK_DATA_DIR=/opt/superbot-desk-data/$p
Environment=PYTHONPATH=$STAGE/backend
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$STAGE/.venv/bin/python3 -m desk.exit_only --portfolio $p --data-dir /opt/superbot-desk-data/$p --snapshot-dir $SNAP/$p --start-paper-exit-only
Restart=no
RestartSec=0
TimeoutStopSec=10
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ReadWritePaths=/opt/superbot-desk-data/$p
ReadOnlyPaths=$SNAP/$p
CapabilityBoundingSet=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
TasksMax=64
MemoryMax=768M

[Install]
WantedBy=multi-user.target
SERVICE
  chmod 0600 "$unit"
done
systemctl daemon-reload
for n in falco toro; do
  name="superbot-v3-$n-exit.service"
  test "$(systemctl is-enabled "$name" 2>/dev/null || true)" = disabled || { echo RC70_UNIT_NOT_DISABLED; exit 2; }
  test "$(systemctl is-active "$name" 2>/dev/null || true)" != active || { echo RC70_UNIT_STARTED_UNEXPECTEDLY; exit 2; }
  echo "RC70_$(echo "$n" | tr '[:lower:]' '[:upper:]')_UNIT_INSTALLED_DISABLED=True"
done
for n in hawk bull; do
  test "$(docker inspect -f '{{.State.Running}}' superbot-desk-"$n")" = false || { echo RC70_LEGACY_STARTED_AFTER; exit 2; }
done
echo RC70_ZERO_WORKERS_STARTED=True
echo RC70_ZERO_CLOSE_REQUESTS_SENT=True
echo RC70_NO_PRODUCTION_WEB_CHANGE=True
