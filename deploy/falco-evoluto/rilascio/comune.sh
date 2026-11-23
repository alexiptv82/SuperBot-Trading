# Valori comuni del rilascio PAPER Falco Evoluto + Brain Scalp (letto dagli altri script; nessuna azione qui).
LAB=/home/superbot-agent/brain-unico-lab/wt-fe                # repository di laboratorio che contiene il commit
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3              # stesso interprete delle unita' Brain in produzione
PARENT=/opt/superbot-v3-paper-runs
AIENV=/etc/superbot-v3-paper/brain-ai.env                     # chiave DeepSeek (solo letta da systemd, mai stampata)
BACKUPS=/opt/superbot-v3-backups/falco-scalp
# run: nome breve | cartella | run_id | configurazione nel codice | capitale
F_DIR=brain-v3-falco-evoluto-p1; F_ID=falco-evoluto-paper-p1; F_CFG=runner_config_falco_evoluto_paper.json; F_EQ=1000
S_DIR=brain-v3-brain-scalp-p1;   S_ID=brain-scalp-paper-p1;   S_CFG=runner_config_brain_scalp_paper.json;   S_EQ=2000
U_F_EXIT=superbot-falco-evoluto-p1-exit.service; U_F_RUN=superbot-falco-evoluto-p1-runner.service
U_S_EXIT=superbot-brain-scalp-p1-exit.service;   U_S_RUN=superbot-brain-scalp-p1-runner.service
# Brain RC1 (solo controllo e pausa delle nuove aperture; mai chiusure, mai modifiche alla run)
RC1_RUN=$PARENT/brain-v3-unico-paper-rc1
RC1_EXIT=superbot-brain-unico-rc1-exit.service; RC1_RUN_U=superbot-brain-unico-rc1-runner.service
nogo() { echo "NO-GO: $*"; exit 1; }
stage_of() { echo "/opt/superbot-falco-scalp-$(printf '%s' "$1" | cut -c1-12)"; }
