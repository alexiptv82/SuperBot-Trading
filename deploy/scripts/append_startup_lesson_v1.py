#!/usr/bin/env python3
"""Controlled direct VPS append to PAPER brain lessons.md ONLY; no orders or service changes."""
import hashlib
import os
import pathlib
import stat
import sys

ROOT = pathlib.Path("/opt/superbot-desk-data")
BOTS = ("hawk", "bull")
MARKER = "[LESSON-STARTUP-20261024]"
NOTE = "\n## 24/10/2026 — Riavvio PAPER, SHORT concentrati: pazienza e qualità degli ingressi [LESSON-STARTUP-20261024]\n**Fatti al controllo 18:54 UTC:** dopo rollback e riavvio, 16 SHORT contemporaneamente aperti (10 Hawk, 6 Bull), tutti con ROI netto stimato negativo; 4 posizioni chiuse per stop loss (XRP e SOL nei due bot). Tra queste 4 chiusure il win rate era 0%; non è il win rate finale delle 16 posizioni ancora aperte.\n**Diagnosi da verificare:** valutazione del contesto e del rischio di concentrazione insufficiente rispetto al rimbalzo di mercato; non è provato che ogni singolo segnale fosse invalido.\n**Lezione prioritaria:** uno slot libero NON va riempito per principio. Prima di OGNI apertura rivalutare regime, direzione, volatilità, probabilità, costi e rapporto rischio/rendimento come se si osservasse il mercato per la prima volta. Dopo SL, TP o futura uscita Fix B rivalutare da zero anche l'eventuale opportunità inversa sullo stesso simbolo, senza inversioni automatiche.\n**Istruzione qualitativa per Claude:** \"Puoi raccomandare di non aprire nessuna posizione. Slot vuoto = scelta valida.\" Attendere quando il setup non è convincente; evitare ingressi per sfruttare slot o capitale disponibili.\n**KPI-obiettivo (non risultato attuale):** puntare al 70–80% di posizioni definitivamente chiuse in profitto netto e al 20–30% o meno di chiusure per SL; monitorare anche valore atteso netto, perdite medie, costi e drawdown: un win rate elevato da solo non basta. Registrare gli scarti e i falsi positivi. Startup Cooldown è una difesa meccanica futura, NON sostituisce il giudizio professionale sull'ingresso.\n"
def as_bytes(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):raise ValueError("not_regular_file")
        if st.st_size>2*1024*1024:raise ValueError("lessons_file_too_large")
        with os.fdopen(fd,"rb",closefd=False) as stream:return stream.read()
    finally:os.close(fd)
def main():
    paths=[ROOT/b/"lessons.md" for b in BOTS]
    note=NOTE.encode("utf-8")
    if len(note)>3000:raise ValueError("note too long")
    status={}
    for bot,path in zip(BOTS,paths):
        if path.is_symlink() or not path.parent.is_dir():raise ValueError(bot+":unsafe_path")
        raw=as_bytes(path)
        try:s=raw.decode("utf-8")
        except UnicodeDecodeError:raise ValueError(bot+":non_utf8_lessons")
        if b"\x00" in raw:raise ValueError(bot+":unexpected_binary")
        count=s.count(MARKER)
        if count>1:raise ValueError(bot+":duplicate_marker")
        status[bot]={"path":path,"old":raw,"present":bool(count),
                     "pre_sha256":hashlib.sha256(raw).hexdigest()}
    mode=sys.argv[1] if len(sys.argv)>1 else "--dry-run"
    if mode not in ("--dry-run","--apply"):raise ValueError("unknown_mode")
    for bot in BOTS:
        row=status[bot]
        print("LESSON_PREFLIGHT",bot,"existing",row["present"],
              "bytes",len(row["old"]),"sha256",row["pre_sha256"],flush=True)
    if mode=="--dry-run":
        print("LESSON_PREFLIGHT_DONE",flush=True)
        return
    for bot in BOTS:
        row=status[bot];path=row["path"]
        if not row["present"]:
            # Exclusive nofollow append; prevent accidentally overwriting any brain data.
            flags=os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW
            fd=os.open(path,flags)
            try:
                prior=os.fstat(fd)
                if prior.st_size!=len(row["old"]):raise RuntimeError(bot+":concurrent_write_detected")
                payload=(b"\n" if row["old"] and not row["old"].endswith(b"\n") else b"")+note
                while payload:
                    n=os.write(fd,payload)
                    if n<=0:raise OSError("append_failed")
                    payload=payload[n:]
                os.fsync(fd)
            finally:os.close(fd)
        new=as_bytes(path)
        if MARKER.encode() not in new:raise RuntimeError(bot+":postverify_marker_missing")
        if not new.startswith(row["old"]):raise RuntimeError(bot+":original_lessons_modified")
        if new.decode("utf-8").count(MARKER)!=1:raise RuntimeError(bot+":duplicate_marker")
        print("LESSON_UPDATED",bot,"bytes",len(new),"sha256",hashlib.sha256(new).hexdigest(),
              "old_prefix_preserved",True,"marker_once",True,flush=True)
    print("LESSONS_HAWK_BULL_COMPLETE",flush=True)
if __name__=="__main__":main()
