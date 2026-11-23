#!/bin/sh
# RIPRESA del rilascio PAPER Falco Evoluto + Brain Scalp dopo il NO-GO del 23/11: RIUSA le due run gia' create
# (in pausa, approved:false; journal conservati, mai ricreati), codice corretto in una cartella nuova, poi come il rilascio.
# Uso (root): sh 00-ripresa.sh <commit 40 hex> <cartella build UI> <sha256 di SHA256SUMS>
# Nessuna attivazione: i mandati si approvano solo con 80-paper.sh, per run, con il consenso del proprietario.
set -u
D=$(cd "$(dirname "$0")" && pwd)
. "$D/comune.sh"
SHA=${1:-}; UI=${2:-}; UISHA=${3:-}
[ "$(id -u)" = 0 ] || nogo "serve root"
ST="$BACKUPS/rilascio.state"
fail() {
  echo "FAIL  $1"
  echo "== rollback automatico dei passi gia' fatti"
  sh "$D/90-rollback.sh"
  echo "ESITO RILASCIO: NO-GO ($1). Run e codice conservati; RC1 invariato."
  exit 1
}
echo "== RIPRESA rilascio Falco Evoluto + Brain Scalp, commit $SHA, $(date -u +%FT%TZ)"
sh "$D/05-rc1-pausa.sh" || nogo "Brain RC1: pausa non confermata (nessuna modifica eseguita)"
[ ! -e "$ST" ] || nogo "stato di un rilascio precedente presente ($ST): eseguire prima 90-rollback.sh"
sh "$D/15-ripresa-preflight.sh" "$SHA" "$UI" "$UISHA" || nogo "preflight della ripresa (nessuna modifica eseguita)"
mkdir -p -m 700 "$BACKUPS"; : > "$ST"; chmod 600 "$ST"
sh "$D/20-backup.sh" || fail "backup"
# copia di sicurezza delle due run riusate (journal compresi), prima di qualunque altro passo
K="$BACKUPS/runs-before-ripresa-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p -m 700 "$K"
cp -a "$PARENT/$F_DIR" "$PARENT/$S_DIR" "$K/" || fail "copia delle run"
echo "PASS  copia delle run in $K"
sh "$D/30-codice.sh" "$SHA" || fail "codice"; echo codice >> "$ST"
sh "$D/35-verifica-run.sh" "$SHA" || fail "verifica delle run riusate"
echo unita_avviate >> "$ST"
sh "$D/50-unita.sh" "$SHA" || fail "unita'"; echo unita >> "$ST"
echo web_avviato >> "$ST"
python3 "$D/falco_scalp_web_cutover.py" --deploy --source-root "$LAB" --sha "$SHA" || fail "web e bridge"
echo web >> "$ST"
bash "$D/70-interfaccia.sh" --activate --candidate "$UI" --manifest-sha "$UISHA" || fail "interfaccia"
echo ui >> "$ST"
echo "== controlli finali"
for r in falco scalp; do sh "$D/80-paper.sh" "$r" stato || fail "stato $r"; done
[ -f "$RC1_RUN/pause.flag" ] && [ "$(systemctl is-active "$RC1_EXIT")" = active ] || fail "RC1 non piu' in pausa o uscite ferme"
for u in "$U_F_EXIT" "$U_F_RUN" "$U_S_EXIT" "$U_S_RUN" superbot-v3-paper-single-close-bridge.service; do
  [ "$(systemctl is-active "$u")" = active ] || fail "$u non attiva"; done
[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8002/api/v3/compare)" = 401 ] || fail "confronto non protetto"
echo "ESITO RILASCIO: PRONTO PER IL COLLAUDO PAPER (due run in pausa, mandati approved:false, nessun trade; RC1 in pausa)"
echo "Attivazione, solo con il consenso finale: sh $D/80-paper.sh falco attiva \"<Nome>\" | sh $D/80-paper.sh scalp attiva \"<Nome>\""
