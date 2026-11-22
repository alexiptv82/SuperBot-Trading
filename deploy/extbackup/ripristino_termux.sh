#!/bin/sh
# Ripristino di PROVA della copia Android degli INDISPENSABILI, su smartphone con Termux, SENZA root.
# Uso: sh ripristino_termux.sh <cartella con gli archivi scaricati> <file della chiave PRIVATA age>
#   - la cartella contiene superbot-backup-indispensabili-<istante>.manifest.json e l'archivio (.tar.gz.age intero
#     oppure le parti .tar.gz.age.part000, .part001, ...), scaricati da GitHub (copie/android/AAAA/MM/);
#   - restore_external_backup.py (impronta gia' verificata) sta nella stessa cartella di questo script.
# Che cosa fa: controlla strumenti e SPAZIO LIBERO del telefono prima di tutto; copia gli archivi cifrati nella
# memoria PRIVATA di Termux (mai i dati in chiaro nella memoria condivisa); esegue il ripristino verificato (SHA-256
# di archivio e parti, decifratura autenticata, manifesto interno, integrity_check dei database, quattro catene
# EventJournal V3 obbligatorie); con esito OK cancella i dati in chiaro e conserva solo il registro.
# La chiave privata non viene copiata ne' trasmessa: la legge solo age, sul telefono.
set -eu
SRC="${1:?cartella degli archivi scaricati}"
KEY="${2:?file della chiave privata age}"
HERE=$(cd "$(dirname "$0")" && pwd)
ANDROID_KEY=age1kpdfwmlpjmmwre34kg5zpdjlrc3kjw7syymzax8tg2jm892wa5sqnzc9nm
BASE="$HOME/superbot-ripristino"
[ "$(id -u)" != 0 ] || echo "NOTA: non serve root; si consiglia l'utente normale di Termux"
for c in python age age-keygen sha256sum; do
  command -v "$c" >/dev/null 2>&1 || { echo "NO-GO: manca $c (pkg install python age coreutils)"; exit 2; }
done
python -c "import sqlite3, hashlib, tarfile, gzip, fcntl" 2>/dev/null || { echo "NO-GO: Python senza sqlite3/hashlib/tarfile"; exit 2; }
[ -f "$HERE/restore_external_backup.py" ] || { echo "NO-GO: manca restore_external_backup.py accanto allo script"; exit 2; }
[ -f "$KEY" ] || { echo "NO-GO: chiave privata non trovata: $KEY"; exit 2; }
grep -q '^AGE-SECRET-KEY-1' "$KEY" || { echo "NO-GO: $KEY non contiene una chiave privata age"; exit 2; }
# la chiave privata deve corrispondere alla chiave pubblica Android (age-keygen -y la ricava senza mostrarla)
[ "$(age-keygen -y "$KEY")" = "$ANDROID_KEY" ] || { echo "NO-GO: la chiave privata non corrisponde a $ANDROID_KEY"; exit 2; }

set -- "$SRC"/superbot-backup-indispensabili-*.manifest.json
[ "$#" = 1 ] && [ -f "$1" ] || { echo "NO-GO: in $SRC serve UN solo manifesto superbot-backup-indispensabili-*.manifest.json (trovati: $#)"; exit 2; }
MAN="$1"
NAME=$(basename "$MAN" .manifest.json).tar.gz.age
# manifesto: destinatario Android, elenco delle parti, dimensioni (per lo spazio)
INFO=$(python -I - "$MAN" "$ANDROID_KEY" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
if (m.get("cifratura") or {}).get("destinatario") != sys.argv[2]:
    print("ERRORE destinatario diverso dalla chiave Android"); sys.exit(1)
if m.get("componente") != "indispensabili":
    print("ERRORE componente non indispensabili"); sys.exit(1)
parts = [p["file"] for p in (m.get("parti") or [])] or [m["archivio"]]
plain = (m.get("contenuto") or {}).get("byte_in_chiaro") or 0
print(m["dimensione"], plain, " ".join(parts))
EOF
) || { echo "NO-GO: $INFO"; exit 2; }
SIZE=$(echo "$INFO" | cut -d' ' -f1)
PLAIN=$(echo "$INFO" | cut -d' ' -f2)
FILES=$(echo "$INFO" | cut -d' ' -f3-)
for f in $FILES; do [ -f "$SRC/$f" ] || { echo "NO-GO: file mancante (scaricare tutte le parti): $f"; exit 2; }; done
[ "$PLAIN" -gt 0 ] || PLAIN=$((SIZE * 10))
# spazio: copia cifrata + archivio ricomposto + tar.gz decifrato + dati estratti + 256 MiB di margine
NEED=$((SIZE * 3 + PLAIN + 268435456))
mkdir -p "$BASE"
AVAIL=$(python -I -c 'import os, sys; s = os.statvfs(sys.argv[1]); print(s.f_bavail * s.f_frsize)' "$BASE")
echo "== spazio telefono: archivio $((SIZE / 1048576)) MiB, dati in chiaro $((PLAIN / 1048576)) MiB, necessari $((NEED / 1048576)) MiB, liberi $((AVAIL / 1048576)) MiB"
[ "$AVAIL" -gt "$NEED" ] || { echo "NO-GO: spazio insufficiente sul telefono"; exit 1; }

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARC="$BASE/archivio-$STAMP"; OUT="$BASE/ripristino-$STAMP"; TMPDIR="$BASE/tmp-$STAMP"; LOG="$BASE/ripristino-$STAMP.log"
export TMPDIR
umask 077
mkdir -p "$ARC" "$TMPDIR"
cp "$MAN" "$ARC/"
for f in $FILES; do cp "$SRC/$f" "$ARC/"; done
RC=0
python -I "$HERE/restore_external_backup.py" --archive "$ARC/$NAME" --identity "$KEY" --out "$OUT" > "$LOG" 2>&1 || RC=$?
rm -rf "$TMPDIR"
grep -E "parti:|archivio cifrato|decifratura|manifesto interno|componente|database|journal V3|RISULTATO|ERRORE" "$LOG" || true
N=$(grep -c "catena verificata (obbligatorio)" "$LOG" || true)
echo "catene EventJournal V3 obbligatorie verificate: $N"
if [ "$RC" = 0 ] && [ "$N" = 4 ]; then
  rm -rf "$OUT" "$ARC"
  echo "ESITO: RIPRISTINO SU ANDROID CERTIFICATO (dati in chiaro cancellati; registro $LOG)"
  exit 0
fi
echo "ESITO: NON CERTIFICATO (uscita $RC, catene obbligatorie $N/4). Dati in chiaro in $OUT: cancellarli dopo l'esame con: rm -rf $BASE/ripristino-* $BASE/archivio-*"
exit 1
