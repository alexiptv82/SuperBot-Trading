#!/bin/bash
# Unico punto d'ingresso amministrativo SuperBot (root, eseguito dal proprietario con la sua password).
#   ripresa            installa il pacchetto verificato in /root/falco-scalp-rilascio ed esegue 00-ripresa.sh: RIUSA le
#                      due run del 23/11 (in pausa, approved:false, journal conservati), codice corretto 246a3a92
#   (rilascio)         non piu' utilizzabile: le run esistono gia' e non vanno ricreate
#   aggiorna-contratti aggiornamento mirato del codice di Falco Evoluto e Brain Scalp al commit 5539ee47 (regole dei
#                      contratti BTC/ETH): solo la cartella del codice nelle 4 unita'; run, mandati, pause, RC1, web
#                      e bridge invariati; rollback automatico delle unita'
#   autonomia          installa /usr/local/sbin/superbot-ops e /etc/sudoers.d/superbot-ops (elenco chiuso, vedi file)
#   revoca-autonomia   rimuove wrapper e regola sudo
# Ogni file viene copiato nella destinazione di root e verificato LI' con SHA-256 prima dell'uso.
set -euo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
SRC=/home/superbot-agent/brain-unico-lab/wt-fe
SHA=246a3a92fc21d30b775f866bc266876c84199552
UI=/home/superbot-agent/brain-unico-lab/rilascio/ui-393b38f6
UISHA=6dad215321b725f7a129228dba793de7f2abee64c9878a89014612effe2f198b
PKG=/root/falco-scalp-rilascio
LOG=/home/superbot-agent/precollaudo-esiti/rilascio-falco-scalp.log
nogo() { echo "NO-GO: $*"; exit 1; }
[ "$(id -u)" = 0 ] || nogo "serve root (sudo)"
put() {  # impronta sorgente destinazione modo
  install -m "$4" -o root -g root "$SRC/$2" "$3"
  [ "$(sha256sum "$3" | cut -d' ' -f1)" = "$1" ] || { rm -f "$3"; nogo "impronta diversa: $2"; }
}
case "${1:-}" in
  rilascio) nogo "le run esistono gia': usare la modalita' ripresa" ;;
  ripresa)
    install -d -m 700 -o root -g root "$PKG"
    while read -r h f; do [ -n "$h" ] && put "$h" "$f" "$PKG/$(basename "$f")" 500; done <<'LISTA'
c639a85c6e37ec03adc748586977817aee633e17848d9457adae1f652a3a66e0 deploy/falco-evoluto/rilascio/comune.sh
227c1b60c6465d117b9f08705514d2d269ea7576d4aee60743bdbbb4afc5288a deploy/falco-evoluto/rilascio/00-rilascio.sh
ffb55fc0e53c68359e17c6faa27e8c345318b7fbf7deb60213e7a07cf326590c deploy/falco-evoluto/rilascio/00-ripresa.sh
2586bc308a39cd8691516d4b67d6cf701113d41a83a1f2973e2a78e1e1759ba7 deploy/falco-evoluto/rilascio/05-rc1-pausa.sh
4633a963f55f1b4d80442168652f46978f006a05afe99397c063cb8a11781898 deploy/falco-evoluto/rilascio/10-preflight.sh
b292492115bb5b7ddc8c1f836a1f4804f0a6d2bc0a9b607c6a2bcd240897178b deploy/falco-evoluto/rilascio/15-ripresa-preflight.sh
34a80fe057ad69dd8fa5da1dfb66d1d002238dbb4e6599be8b1286ef87c591b3 deploy/falco-evoluto/rilascio/20-backup.sh
40fcee764219117c99b9e48fe11e6b9bd6d31584aed117ff5cead5b59870f946 deploy/falco-evoluto/rilascio/30-codice.sh
cc73d27d81c33eaf748df270cc90eacfe4f88a63743a07857d912287f38b9637 deploy/falco-evoluto/rilascio/35-verifica-run.sh
36f2ff2a752f59afcbc9f73e774f7678d61bb7689feec8f1f02a1f50a83a119d deploy/falco-evoluto/rilascio/40-run.sh
849f5fdde10f9da7757b28b1ee7a622149ad1ea8d40ee1c08ba2965e1ad9cefa deploy/falco-evoluto/rilascio/50-unita.sh
0fc1e6e1ee74ea50b890dc2c6917238a3d84b87b1bb9429c0e173b079182d0f1 deploy/falco-evoluto/rilascio/80-paper.sh
8bbe7c9039739b770a1ef2c57f4f0183c3dd153287febf59dd181328071953f3 deploy/falco-evoluto/rilascio/90-rollback.sh
5b56d8008bd9f585fe4cc86af8eb7c0ddec009aca97b993774528e17e7a77b94 deploy/falco-evoluto/rilascio/falco_scalp_web_cutover.py
7835d87b7e93a679d33b6cd2f94885a09adf5807350cb3de3ab1814562c68c9e deploy/falco-evoluto/rilascio/compare_probe.py
062bd3da406b0ca5bbc51412611370eed9413060b3c518113301e49760db8d8b deploy/brain-unico/avvio/70-interfaccia.sh
cfa17d4d5f92cf5924dfb84abde84efd21f9c6c5440d20f9984dce97c2afb998 deploy/brain-unico/avvio/brain_unico_web_cutover.py
bd52e7ef44bfeee2b73f80f488e66afadb078eb1231a134c1c5fd37c5412248d deploy/brain-unico/avvio/brain_unico_web_probe.py
638c4da73615e11439d4e92f89890b5ca92c031b7df789d358d2d92fe7210afd deploy/brain-unico/precollaudo/controlli.py
LISTA
    echo "PASS  19 file del pacchetto installati e verificati in $PKG"
    RC=0
    sh "$PKG/00-ripresa.sh" "$SHA" "$UI" "$UISHA" 2>&1 | tee "$LOG.ripresa" || RC=$?
    chmod 644 "$LOG.ripresa"                 # leggibile dall'operatore: il registro non contiene segreti
    exit "$RC" ;;
  aggiorna-contratti)
    install -d -m 700 -o root -g root "$PKG"
    while read -r h f; do [ -n "$h" ] && put "$h" "$f" "$PKG/$(basename "$f")" 500; done <<'LISTA2'
c639a85c6e37ec03adc748586977817aee633e17848d9457adae1f652a3a66e0 deploy/falco-evoluto/rilascio/comune.sh
40fcee764219117c99b9e48fe11e6b9bd6d31584aed117ff5cead5b59870f946 deploy/falco-evoluto/rilascio/30-codice.sh
5439f8ad8e725874669d37a7ba03a78c9239933f528688dacde07100ad3949b9 deploy/falco-evoluto/rilascio/60-aggiorna-codice.sh
82dcae2296d176152ffd91c87e0a1861adf33d4620e50b38f22484daf3c53341 deploy/falco-evoluto/rilascio/contratti_check.py
638c4da73615e11439d4e92f89890b5ca92c031b7df789d358d2d92fe7210afd deploy/brain-unico/precollaudo/controlli.py
LISTA2
    echo "PASS  5 file dell'aggiornamento installati e verificati in $PKG"
    RC=0
    sh "$PKG/60-aggiorna-codice.sh" 5539ee4744764b14b76e0e8f71c931536523c7af 2>&1 | tee "$LOG.aggiorna" || RC=$?
    chmod 644 "$LOG.aggiorna"
    exit "$RC" ;;
  autonomia)
    T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
    put 2b672bb10d8f9163450d8394ad420280a2d0e1a143163e1b0b6bc53b9157af0a deploy/falco-evoluto/admin/superbot-ops.sudoers "$T/superbot-ops" 440
    visudo -cf "$T/superbot-ops" >/dev/null || nogo "regola sudo non valida"
    put e7158a7f277da0fc921bde3e787d4f9c938121dee2c180bac7cc4bbd7964e59c deploy/falco-evoluto/admin/superbot-ops /usr/local/sbin/superbot-ops 755
    install -m 440 -o root -g root "$T/superbot-ops" /etc/sudoers.d/superbot-ops
    [ "$(sha256sum /etc/sudoers.d/superbot-ops | cut -d' ' -f1)" = 2b672bb10d8f9163450d8394ad420280a2d0e1a143163e1b0b6bc53b9157af0a ] || { rm -f /etc/sudoers.d/superbot-ops; nogo "regola alterata"; }
    visudo -c >/dev/null || { rm -f /etc/sudoers.d/superbot-ops; nogo "configurazione sudo complessiva non valida: regola rimossa"; }
    echo "AUTONOMIA LIMITATA INSTALLATA: superbot-agent puo' eseguire solo:"
    sudo -l -U superbot-agent | grep superbot-ops || true
    echo "Revoca: sudo bash /root/superbot-installa.sh revoca-autonomia" ;;
  revoca-autonomia)
    rm -f /etc/sudoers.d/superbot-ops /usr/local/sbin/superbot-ops
    visudo -c >/dev/null && echo "AUTONOMIA REVOCATA: wrapper e regola sudo rimossi" ;;
  *) nogo "modalita': ripresa | aggiorna-contratti | autonomia | revoca-autonomia" ;;
esac
