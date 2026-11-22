# Valori comuni del pre-collaudo Brain Unico (letto dagli altri script; nessuna azione qui).
LAB=/home/superbot-agent/brain-unico-lab/wt-int
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3          # stesso interprete del servizio uscite attuale
PARENT=/opt/superbot-v3-paper-runs
RUN_ID=brain-unico-paper-rc1                              # legato dal mandato
RUN_DIR=brain-v3-unico-paper-rc1                          # prepare_paper_run accetta solo cartelle brain-v3-*
RUN=$PARENT/$RUN_DIR
CFG_SHA=e415ca968e7475be820712294fd97a81dfe6ef03e21df00342a0eab68203eedc
U_EXIT=superbot-brain-unico-rc1-exit.service
U_RUN=superbot-brain-unico-rc1-runner.service
OLD_EXIT=superbot-v3-paper-brain-exit.service              # servizio uscite della vecchia run: MAI toccato
nogo() { echo "NO-GO: $*"; exit 1; }
