#!/bin/sh
# INSTALLA senza avviare: codice al commit della RC, nuova run in pausa (prepare_paper_run), due unita' NON abilitate
# e NON avviate. Nessuna unita' o run esistente viene toccata. Uso (root): sh 10-installa.sh <commit di 40 caratteri>
set -eu
. "$(dirname "$0")/comune.sh"
COMMIT="${1:-}"
[ "$(id -u)" = 0 ] || nogo "serve root"
printf '%s' "$COMMIT" | grep -Eq '^[0-9a-f]{40}$' || nogo "commit non valido"
STAGE=/opt/superbot-brain-unico-$(printf '%s' "$COMMIT" | cut -c1-12)
[ ! -e "$STAGE" ] || nogo "$STAGE esiste gia'"
[ ! -e "$RUN" ] || nogo "$RUN esiste gia'"
for u in "$U_EXIT" "$U_RUN"; do [ ! -e "/etc/systemd/system/$u" ] || nogo "$u esiste gia'"; done
git -C "$LAB" cat-file -e "$COMMIT^{commit}" || nogo "commit assente nel laboratorio"
[ -x "$PY" ] || nogo "interprete assente"
umask 022
mkdir -m 755 "$STAGE"
git -C "$LAB" archive "$COMMIT" | tar -x -C "$STAGE"
printf '%s  %s\n' "$CFG_SHA" "$STAGE/backend/v3/runner/runner_config_brain_unico_paper_b.json" | sha256sum --strict -c - \
  || nogo "impronta della configurazione diversa"
(cd "$STAGE" && DESK_MODE=paper PYTHONPATH="$STAGE" "$PY" -m backend.v3.runner.prepare_paper_run --parent "$PARENT" \
  --run-name "$RUN_DIR" --run-id "$RUN_ID" --config "$STAGE/backend/v3/runner/runner_config_brain_unico_paper_b.json" \
  --prepare-paper-paused --expected-initial-equity 2000) || nogo "preparazione della run"
printf '%s  %s\n' "$CFG_SHA" "$RUN/runner_config.json" | sha256sum --strict -c - || nogo "impronta della configurazione della run"
[ -f "$RUN/PREPARED_PAUSED_ONLY.json" ] && [ -f "$RUN/pause.flag" ] || nogo "run non in pausa"
cat > "/etc/systemd/system/$U_EXIT" <<UNIT
[Unit]
Description=Brain Unico PAPER rc1: servizio delle uscite (proprietario unico)
[Service]
User=root
WorkingDirectory=$STAGE
Environment=DESK_MODE=paper
Environment=PYTHONPATH=$STAGE
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStartPre=/usr/bin/test -f $RUN/PREPARED_PAUSED_ONLY.json
ExecStart=/usr/bin/env DESK_MODE=paper $PY -m backend.v3.runner.exit_worker --data-dir $RUN --run-id $RUN_ID --config $RUN/runner_config.json --start-paper --legacy-exits-disabled
Restart=on-failure
RestartSec=10
UNIT
cat > "/etc/systemd/system/$U_RUN" <<UNIT
[Unit]
Description=Brain Unico PAPER rc1: runner (sidecar; senza mandato approvato resta fermo e non spende)
After=$U_EXIT
[Service]
User=root
WorkingDirectory=$STAGE
Environment=DESK_MODE=paper
Environment=PYTHONPATH=$STAGE
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/env DESK_MODE=paper $PY -m backend.v3.runner.wiring --data-dir $RUN --run-id $RUN_ID --config $RUN/runner_config.json --exit-mode sidecar
Restart=on-failure
RestartSec=10
UNIT
chmod 644 "/etc/systemd/system/$U_EXIT" "/etc/systemd/system/$U_RUN"
systemctl daemon-reload
echo "INSTALLATO, NON AVVIATO: codice $STAGE, run $RUN (in pausa, mandato non approvato), unita' $U_EXIT e $U_RUN"
