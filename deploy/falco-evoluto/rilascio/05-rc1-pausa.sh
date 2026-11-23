#!/bin/sh
# Brain RC1: mostra lo stato e mette in pausa le NUOVE aperture solo se la pausa manca. Nessuna chiusura di posizioni,
# servizio delle uscite e chiusura manuale invariati. Usa lo strumento gia' installato e verificato (80-paper.sh RC1).
set -eu
. "$(dirname "$0")/comune.sh"
[ "$(id -u)" = 0 ] || nogo "serve root"
P=/root/brain-unico-avvio/80-paper.sh
printf '%s  %s\n' 1ea8709f75a4c65fc496bbc191e0dab1eb3a95deabd5ed3e1e1ed0ad168ba9a5 "$P" | sha256sum --strict -c - >/dev/null \
  || nogo "80-paper.sh di RC1 assente o diverso"
echo "== Brain RC1 prima"
sh "$P" stato || true
if [ -f "$RC1_RUN/pause.flag" ]; then echo "RC1: ERA GIA' IN PAUSA (nessuna modifica)"
else sh "$P" pausa && echo "RC1: PAUSA APPLICATA ORA (solo nuove aperture; posizioni e uscite invariate)"; fi
[ -f "$RC1_RUN/pause.flag" ] || nogo "RC1: pause.flag ancora assente"
[ "$(systemctl is-active "$RC1_EXIT")" = active ] || nogo "RC1: servizio delle uscite NON attivo"
echo "RC1_PAUSA=CONFERMATA uscite=$(systemctl is-active "$RC1_EXIT") runner=$(systemctl is-active "$RC1_RUN_U")"
