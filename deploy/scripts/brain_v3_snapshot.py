#!/usr/bin/env python3
"""Copia CERTIFICATA delle run Brain V3 (PAPER) e del vecchio database Brain Free, per il backup esterno cifrato.

Solo libreria standard (gira sul VPS con `python3 -I`). NON cifra, NON usa la rete, NON avvia ne' ferma nulla: produce
una cartella di staging con file copiati e un dizionario di "fatti" verificati. La cifratura e l'invio stanno in
external_backup_brain_v3.py; il ripristino in restore_brain_v3_backup.py (che riusa le STESSE verifiche).

Garanzie (sorgente = cartelle vere della VPS, sempre in SOLA LETTURA):
  - nessun file della sorgente viene creato, riscritto, spostato o cancellato; nessun database vuoto viene inizializzato
    al posto di un file assente (un file mancante e' un RIFIUTO);
  - SQLite si copia solo con l'API di backup (transazione consistente, include il WAL gia' confermato). Un database in
    modalita' WAL che nessuno sta usando (nessun file -wal/-shm) si apre `immutable=1`: SQLite non crea cosi' nessun
    file collaterale nella cartella vera (una apertura `mode=ro` di un WAL chiuso ne crea due); se i file collaterali
    ci sono gia' (processo vivo o residuo di un processo morto) si apre `mode=ro`; uno solo dei due = stato inatteso =
    rifiuto. Unico effetto possibile sulla sorgente: con i residui di un processo MORTO SQLite ricostruisce il file
    `-shm` (indice volatile del WAL, nessun dato); database e `-wal` restano identici byte per byte (provato nei test);
  - journal.db: catena hash ricalcolata evento per evento (stessa formula di backend/v3/events.py), id evento unici,
    trigger di immodificabilita' presenti, una sola identita' (portfolio "brain" + run_id della run), primo evento
    `run_prepared` coerente con la configurazione, coerenza delle posizioni PAPER (nessuna chiusura senza apertura);
  - coerenza TRA i file della stessa run: configurazione (SHA-256) = marcatore di preparazione = evento
    `run_prepared` del journal; mandato della stessa run e con l'impronta dei limiti della configurazione; heartbeat
    della stessa run; budget.db con schema atteso e spese non anteriori alla creazione della run ne' nel futuro;
  - dati in modifica: la copia viene accettata solo se, rileggendo la sorgente DOPO la copia, l'impronta e' identica
    (altrimenti si riprova poche volte e poi si RIFIUTA con `source_changed_during_capture`);
  - le copie dei database sono rimesse in modalita' journal "DELETE": file singoli, senza -wal/-shm (la copia e'
    logicamente identica, non byte per byte; il budget torna in WAL da solo quando lo apre il suo programma).

Ogni rifiuto e' una `Refused` con un codice fisso (snake_case) e un dettaglio senza valori sensibili.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA = "superbot-brain-v3-snapshot-v1"
GENESIS = "0" * 64
RUN_DIR_RE = re.compile(r"^brain-v3-[A-Za-z0-9_-]{3,55}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
TOKEN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_PORTFOLIOS = ("hawk", "bull", "brain")

DURABLE_REQUIRED = ("journal.db", "budget.db", "runner_config.json", "PREPARED_PAUSED_ONLY.json", "mandate.json")
DURABLE_OPTIONAL = ("daily_loss.json",)
CONTROL = ("pause.flag",)
TRANSIENT = ("heartbeat.json", "exit_heartbeat.json", "close_request.json", ".close_request.work", "close_result.json")
LOCKS = (".exit_service.lock", ".brain-paper-open.lock")
SIDECARS = ("journal.db-journal", "journal.db-wal", "journal.db-shm", "budget.db-journal", "budget.db-wal",
            "budget.db-shm")
TMP_RE = re.compile(r"^\.(heartbeat|exit_heartbeat|daily_loss|close_result|close_request)\..*\.tmp$")
MAX_SMALL = {"runner_config.json": 131072, "PREPARED_PAUSED_ONLY.json": 8192, "mandate.json": 65536,
             "daily_loss.json": 8192, "pause.flag": 8192, "heartbeat.json": 65536, "exit_heartbeat.json": 65536,
             "close_request.json": 65536, ".close_request.work": 65536, "close_result.json": 65536}
EXTRA_MAX_EACH = 1 << 20
EXTRA_MAX_TOTAL = 8 << 20
JOURNAL_COLS = ["seq", "event_id", "portfolio_id", "run_id", "kind", "occurred_at_ms", "source", "payload_json",
                "previous_hash", "event_hash"]
BUDGET_COLS = ["id", "occurred_at", "provider", "units", "metadata"]
PREPARED_KEYS = {"run_id", "portfolio_id", "paper_only", "paused", "mandate_approved", "config_sha256",
                 "initial_equity"}
RISK_KEYS = ("max_loss_fraction", "max_open_risk_fraction", "max_position_margin_fraction",
             "max_total_margin_fraction", "minimum_equity", "estimated_roundtrip_cost_bp",
             "liquidation_buffer_fraction")
PROFILE_KEYS = ("max_loss_margin_fraction", "min_leverage", "max_leverage")
CAPTURE_TOLERANCE_MS = 300_000


class Refused(Exception):
    """Rifiuto esplicito: `code` fisso, `detail` senza valori sensibili."""

    def __init__(self, code, detail=""):
        super().__init__(code + ((": " + str(detail)) if detail else ""))
        self.code = code
        self.detail = str(detail)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ---- lettura sicura di file piccoli -------------------------------------------------------------

def read_small(path, limit, required=True):
    """Bytes di un file normale (niente collegamenti simbolici, dimensione limitata). None se assente e non richiesto."""
    name = os.path.basename(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        if required:
            raise Refused("file_missing", name)
        return None
    except OSError:
        raise Refused("file_unsafe", name)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise Refused("file_unsafe", name)
        chunks = []
        left = st.st_size + 1
        while left > 0:
            part = os.read(fd, min(left, 1 << 20))
            if not part:
                break
            chunks.append(part)
            left -= len(part)
        data = b"".join(chunks)
    finally:
        os.close(fd)
    if len(data) > limit:
        raise Refused("file_unsafe", name)
    return data


def parse_json_strict(raw, code):
    """JSON senza chiavi duplicate ne' NaN/Infinity (stessa severita' del caricatore di runner_config)."""
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("dup")
            out[k] = v
        return out

    def bad(_c):
        raise ValueError("const")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refused(code)


# ---- SQLite in sola lettura -----------------------------------------------------------------------

def _is_wal(path):
    try:
        with open(path, "rb") as f:
            head = f.read(100)
    except OSError:
        raise Refused("file_unsafe", os.path.basename(path))
    if len(head) < 100 or head[:16] != b"SQLite format 3\x00":
        raise Refused("sqlite_not_a_database", os.path.basename(path))
    return head[18] == 2 and head[19] == 2


def open_source_db(path):
    """Apre `path` in sola lettura senza creare file nella sua cartella (vedi la nota in testa)."""
    name = os.path.basename(path)
    if not os.path.lexists(path):
        raise Refused("file_missing", name)
    if os.path.islink(path) or not os.path.isfile(path):
        raise Refused("file_unsafe", name)
    wal_p, shm_p, jr_p = path + "-wal", path + "-shm", path + "-journal"
    if _is_wal(path):
        w, s = os.path.lexists(wal_p), os.path.lexists(shm_p)
        if not w and not s:
            suffix = "?immutable=1"
        elif w and s:
            suffix = "?mode=ro"
        else:
            raise Refused("wal_sidecar_state_unexpected", name)
    else:
        if os.path.lexists(wal_p) or os.path.lexists(shm_p):
            raise Refused("wal_sidecar_state_unexpected", name)
        suffix = "?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(Path(path).resolve().as_uri() + suffix, uri=True, timeout=10)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()      # la prima lettura scopre un journal "caldo"
        return conn
    except sqlite3.Error as e:
        if conn is not None:
            conn.close()
        if "locked" in str(e) or "busy" in str(e):
            raise Refused("sqlite_busy", name)
        if "readonly" in str(e) and os.path.lexists(jr_p) and os.path.getsize(jr_p) > 0:
            raise Refused("hot_journal", name)              # residuo di un arresto brusco: lo recupera solo il suo programma
        raise Refused("sqlite_open_failed", name)


def _integrity(conn, name):
    try:
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error:
        raise Refused("sqlite_integrity_failed", name)
    if ok != "ok":
        raise Refused("sqlite_integrity_failed", name)


def _journal_digest(prev, eid, pf, rid, kind, at, src, payload_json):
    fields = [prev, eid, pf, rid, kind, str(at), src, payload_json]
    return hashlib.sha256(json.dumps(fields, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


# ---- journal.db ---------------------------------------------------------------------------------------

def fingerprint_journal(conn):
    try:
        n, mx = conn.execute("SELECT COUNT(*), COALESCE(MAX(seq),0) FROM v3_events").fetchone()
        row = conn.execute("SELECT event_hash FROM v3_events ORDER BY seq DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        raise Refused("journal_schema_unexpected", "v3_events")
    return {"eventi": n, "seq_max": mx, "testa": row[0] if row else GENESIS}


def fingerprint_budget(conn):
    try:
        n, mx, total = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id),0), COALESCE(SUM(units),0) FROM spend_events").fetchone()
    except sqlite3.Error:
        raise Refused("budget_schema_unexpected", "spend_events")
    return {"righe": n, "id_max": mx, "unita": total}


def read_journal(path, run_id, hash_at=()):
    """Verifica completa di un journal.db (copia o ripristino) e fatti da riportare nel manifesto."""
    want = set(hash_at)
    conn = open_source_db(path)
    try:
        _integrity(conn, "journal.db")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(v3_events)")]
        if cols != JOURNAL_COLS:
            raise Refused("journal_schema_unexpected", "colonne")
        trig = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not {"v3_no_update", "v3_no_delete"} <= trig:
            raise Refused("journal_schema_unexpected", "trigger_di_immodificabilita_assenti")
        prev, count, last_seq, first_hash, first_seq, last_ms = GENESIS, 0, 0, None, None, 0
        seen, pairs, kinds, at_seq = set(), set(), {}, {}
        opens, closes, prepared = {}, {}, []
        for row in conn.execute("SELECT seq,event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                                "previous_hash,event_hash FROM v3_events ORDER BY seq"):
            seq, eid, pf, rid, kind, at, src, pj, ph, eh = row
            if (type(seq) is not int or seq <= last_seq or type(at) is not int or at <= 0
                    or not all(isinstance(x, str) for x in (eid, pf, rid, kind, src, pj, ph, eh))):
                raise Refused("journal_chain_invalid", "seq=%s" % seq)
            if ph != prev or eh != _journal_digest(prev, eid, pf, rid, kind, at, src, pj):
                raise Refused("journal_chain_invalid", "seq=%d" % seq)
            if eid in seen:
                raise Refused("journal_duplicate_event", "seq=%d" % seq)
            seen.add(eid)
            pairs.add((pf, rid))
            kinds[kind] = kinds.get(kind, 0) + 1
            if first_hash is None:
                first_hash, first_seq = eh, seq
            if seq in want:
                at_seq[seq] = eh
            if kind in ("run_prepared", "paper_open", "paper_close"):
                try:
                    payload = json.loads(pj)
                except ValueError:
                    raise Refused("journal_chain_invalid", "payload seq=%d" % seq)
                if not isinstance(payload, dict):
                    raise Refused("journal_chain_invalid", "payload seq=%d" % seq)
                if kind == "run_prepared":
                    prepared.append((seq, eid, src, ph, at, payload))
                elif kind == "paper_open":
                    pid = payload.get("position_id")
                    if (not isinstance(pid, str) or not TOKEN_RE.match(pid) or eid != "paper_open." + pid
                            or pid in opens):
                        raise Refused("paper_incoherent", "apertura seq=%d" % seq)
                    opens[pid] = {"seq": seq, "at": at, "symbol": payload.get("symbol"), "side": payload.get("side")}
                else:
                    pid = payload.get("position_id")
                    o = opens.get(pid) if isinstance(pid, str) else None
                    if (o is None or eid != "paper_close." + pid or pid in closes or at < o["at"]
                            or payload.get("opened_at_ms") != o["at"] or payload.get("symbol") != o["symbol"]
                            or payload.get("side") != o["side"]):
                        raise Refused("paper_incoherent", "chiusura seq=%d" % seq)
                    closes[pid] = seq
            prev, count, last_seq, last_ms = eh, count + 1, seq, max(last_ms, at)
    except sqlite3.Error:
        raise Refused("journal_schema_unexpected", "lettura")
    finally:
        conn.close()
    if count == 0:
        raise Refused("journal_empty")
    if pairs != {("brain", run_id)}:
        raise Refused("journal_identity_mixed", "identita_trovate=%d" % len(pairs))
    if len(prepared) != 1:
        raise Refused("journal_not_prepared", "run_prepared=%d" % len(prepared))
    seq0, eid0, src0, ph0, prepared_ms, pp = prepared[0]
    if (seq0 != first_seq or ph0 != GENESIS or src0 != "rc_setup"
            or eid0 != "v3-prepared-" + sha256_bytes(run_id.encode())[:20]):
        raise Refused("journal_not_prepared", "primo_evento")
    open_ids = sorted(set(opens) - set(closes))
    return {"eventi": count, "seq_max": last_seq, "testa": prev, "primo": first_hash, "tipi": kinds,
            "ultimo_evento_ms": last_ms, "preparata_ms": prepared_ms, "prepared_payload": pp,
            "paper": {"aperte_totali": len(opens), "chiuse": len(closes), "ancora_aperte": len(open_ids),
                      "ids_aperte": open_ids, "ids_aperte_sha256": sha256_bytes(canon(open_ids).encode())},
            "hash_at": at_seq}



# ---- budget.db ------------------------------------------------------------------------------------------

def _iso_ms(text):
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise Refused("budget_schema_unexpected", "occurred_at")
    if dt.tzinfo is None:
        raise Refused("budget_schema_unexpected", "occurred_at_senza_fuso")
    return int(dt.timestamp() * 1000)


def read_budget(path, prefix_ids=()):
    want = set(prefix_ids)
    conn = open_source_db(path)
    try:
        _integrity(conn, "budget.db")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(spend_events)")]
        if cols != BUDGET_COLS:
            raise Refused("budget_schema_unexpected", "colonne")
        stream, rows, total, last_id = hashlib.sha256(), 0, 0, 0
        first_ms = last_ms = None
        providers, prefix = set(), {}
        for rid, at, prov, units, meta in conn.execute(
                "SELECT id,occurred_at,provider,units,metadata FROM spend_events ORDER BY id"):
            if (type(rid) is not int or rid <= last_id or type(units) is not int or units < 0
                    or not isinstance(prov, str) or not isinstance(meta, str)):
                raise Refused("budget_schema_unexpected", "riga id=%s" % rid)
            try:
                if not isinstance(json.loads(meta), dict):
                    raise ValueError
            except ValueError:
                raise Refused("budget_schema_unexpected", "metadata id=%d" % rid)
            ms = _iso_ms(at)
            enc = canon([rid, at, prov, units, meta]).encode()
            stream.update(len(enc).to_bytes(8, "big"))
            stream.update(enc)
            rows, total, last_id = rows + 1, total + units, rid
            first_ms = ms if first_ms is None else min(first_ms, ms)
            last_ms = ms if last_ms is None else max(last_ms, ms)
            providers.add(prov)
            if rid in want:
                prefix[rid] = stream.hexdigest()
    except sqlite3.Error:
        raise Refused("budget_schema_unexpected", "lettura")
    finally:
        conn.close()
    return {"righe": rows, "id_max": last_id, "unita": total, "testa": stream.hexdigest(),
            "primo_ms": first_ms, "ultimo_ms": last_ms, "fornitori": sorted(providers), "prefisso": prefix}


# ---- configurazione, marcatore, mandato ---------------------------------------------------------------

def _dec(value, code):
    if type(value) is not str or not value or len(value) > 24 or not value.isascii():
        raise Refused(code)
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise Refused(code)
    if not d.is_finite():
        raise Refused(code)
    return d


def policy_hash_from_config(cfg):
    """Stessa formula di backend/v3/brain_f2/engine.py::_policy_hash, calcolata dal testo della configurazione."""
    risk = cfg.get("risk_policy")
    if not isinstance(risk, dict) or any(k not in risk for k in RISK_KEYS):
        raise Refused("config_invalid", "risk_policy")
    fields = tuple(str(_dec(risk[k], "config_invalid")) for k in RISK_KEYS)
    if all(k in risk for k in PROFILE_KEYS):
        lo, hi = risk["min_leverage"], risk["max_leverage"]
        if type(lo) is not int or type(hi) is not int:
            raise Refused("config_invalid", "leva")
        fields += (str(_dec(risk["max_loss_margin_fraction"], "config_invalid")), str(lo), str(hi))
    return hashlib.sha256("|".join(fields).encode()).hexdigest()[:16]


def check_config_files(raw_cfg, raw_marker, raw_mandate, run_id):
    cfg = parse_json_strict(raw_cfg, "config_invalid")
    if not isinstance(cfg, dict) or type(cfg.get("schema_version")) is not int:
        raise Refused("config_invalid", "struttura")
    equity = str(_dec(cfg.get("initial_equity"), "config_invalid"))
    cap = _dec(cfg.get("daily_cap_usd"), "config_invalid")
    cfg_sha = sha256_bytes(raw_cfg)
    marker = parse_json_strict(raw_marker, "marker_invalid")
    if (not isinstance(marker, dict) or set(marker) != PREPARED_KEYS or marker["portfolio_id"] != "brain"
            or marker["paper_only"] is not True or marker["paused"] is not True
            or marker["mandate_approved"] is not False or not isinstance(marker["run_id"], str)):
        raise Refused("marker_invalid")
    if marker["run_id"] != run_id:
        raise Refused("marker_mismatch", "run_id")
    if marker["config_sha256"] != cfg_sha:
        raise Refused("config_hash_mismatch", "marcatore")
    if marker["initial_equity"] != equity:
        raise Refused("marker_mismatch", "capitale")
    mandate = parse_json_strict(raw_mandate, "mandate_invalid")
    need = ("version", "approved", "approved_by", "portfolio_id", "run_id", "policy_hash")
    if (not isinstance(mandate, dict) or any(k not in mandate for k in need)
            or type(mandate["approved"]) is not bool or mandate["portfolio_id"] != "brain"):
        raise Refused("mandate_invalid")
    if mandate["run_id"] != run_id:
        raise Refused("mandate_run_mismatch")
    phash = policy_hash_from_config(cfg)
    if mandate["policy_hash"] != phash:
        raise Refused("mandate_policy_mismatch")
    return {"sha256": cfg_sha, "capitale_iniziale": equity, "tetto_giornaliero_unita": int(cap * 1_000_000),
            "policy_hash": phash, "mandato_approvato": mandate["approved"], "validato_da": "struttura"}


def _beat_age(raw, run_id, code, now_ms, keys=None):
    beat = parse_json_strict(raw, code)
    if not isinstance(beat, dict) or type(beat.get("ts_ms")) is not int:
        raise Refused(code)
    if keys is not None and set(beat) != keys:
        raise Refused(code, "chiavi")
    if beat.get("run_id", run_id) != run_id:
        raise Refused("heartbeat_run_mismatch")
    return max(0, now_ms - beat["ts_ms"])


EXIT_BEAT_KEYS = {"schema_version", "run_id", "lease_token", "ts_ms", "state", "last_monitor_ms",
                  "last_commands_ms", "last_error"}


# ---- verifica dei file di UNA run gia' copiata (staging o ripristino) ---------------------------------

def facts_from_files(base, run_name, now_ms, hash_at=(), prefix_ids=()):
    """Tutte le verifiche su una cartella con i file durevoli (e, se ci sono, transient/). Solleva Refused."""
    if not RUN_DIR_RE.match(run_name):
        raise Refused("run_dir_unsafe", run_name)
    raw = {n: read_small(os.path.join(base, n), MAX_SMALL[n]) for n in
           ("runner_config.json", "PREPARED_PAUSED_ONLY.json", "mandate.json")}
    marker = parse_json_strict(raw["PREPARED_PAUSED_ONLY.json"], "marker_invalid")
    run_id = marker.get("run_id") if isinstance(marker, dict) else None
    if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
        raise Refused("marker_invalid", "run_id")
    cfg = check_config_files(raw["runner_config.json"], raw["PREPARED_PAUSED_ONLY.json"], raw["mandate.json"], run_id)
    jr = read_journal(os.path.join(base, "journal.db"), run_id, hash_at)
    pp = jr.pop("prepared_payload")
    if (pp.get("config_sha256") != cfg["sha256"] or pp.get("initial_equity") != cfg["capitale_iniziale"]
            or pp.get("paper_only") is not True or pp.get("mandate_approved") is not False
            or pp.get("schema_version") != 1):
        raise Refused("config_hash_mismatch", "evento_run_prepared")
    bd = read_budget(os.path.join(base, "budget.db"), prefix_ids)
    if bd["righe"]:
        if bd["primo_ms"] < jr["preparata_ms"] - 60_000:
            raise Refused("budget_run_mismatch", "spese_anteriori_alla_run")
        if bd["ultimo_ms"] > now_ms + CAPTURE_TOLERANCE_MS:
            raise Refused("budget_run_mismatch", "spese_nel_futuro")
    control = {"in_pausa": read_small(os.path.join(base, "pause.flag"), MAX_SMALL["pause.flag"], False) is not None}
    tdir = os.path.join(base, "transient")
    activity = {"runner_heartbeat_eta_ms": None, "exit_heartbeat_eta_ms": None, "attiva": False}
    pending = False
    if os.path.isdir(tdir):
        hb = read_small(os.path.join(tdir, "heartbeat.json"), MAX_SMALL["heartbeat.json"], False)
        if hb is not None:
            activity["runner_heartbeat_eta_ms"] = _beat_age(hb, run_id, "heartbeat_invalid", now_ms)
        eb = read_small(os.path.join(tdir, "exit_heartbeat.json"), MAX_SMALL["exit_heartbeat.json"], False)
        if eb is not None:
            activity["exit_heartbeat_eta_ms"] = _beat_age(eb, run_id, "heartbeat_invalid", now_ms, EXIT_BEAT_KEYS)
        pending = any(os.path.lexists(os.path.join(tdir, n)) for n in ("close_request.json", ".close_request.work"))
    ages = [a for a in (activity["runner_heartbeat_eta_ms"], activity["exit_heartbeat_eta_ms"]) if a is not None]
    activity["attiva"] = any(a < 120_000 for a in ages)
    return {"run_name": run_name, "run_id": run_id, "portfolio_id": "brain", "nome_cartella_uguale_a_run_id": run_name == run_id,
            "identita_sha256": sha256_bytes(canon([run_id, jr["primo"], cfg["sha256"]]).encode()),
            "journal": jr, "budget": bd, "config": cfg, "controllo": control, "attivita": activity,
            "richiesta_chiusura_in_sospeso": pending}


# ---- elenco delle voci di una cartella di run -----------------------------------------------------------

EXTRA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def scan_run_dir(run_dir):
    """Voci non previste ma innocue (file normali piccoli) da copiare in extra/. Qualunque altra cosa = rifiuto."""
    try:
        names = sorted(os.listdir(run_dir))
    except OSError:
        raise Refused("run_dir_unsafe", os.path.basename(run_dir))
    known = set(DURABLE_REQUIRED) | set(DURABLE_OPTIONAL) | set(CONTROL) | set(TRANSIENT) | set(LOCKS) | set(SIDECARS)
    extras, total = [], 0
    for n in names:
        if n in known or TMP_RE.match(n):
            continue
        st = os.lstat(os.path.join(run_dir, n))
        if not EXTRA_NAME_RE.match(n) or not stat.S_ISREG(st.st_mode) or st.st_size > EXTRA_MAX_EACH:
            raise Refused("unexpected_entry", n[:60])
        total += st.st_size
        if total > EXTRA_MAX_TOTAL:
            raise Refused("unexpected_entry", "extra_troppo_grandi")
        extras.append(n)
    return extras


def discover_runs(runs_root):
    """(nomi delle run, nomi ignorati). Una cartella chiamata come una run ma collegamento simbolico = rifiuto."""
    if os.path.islink(runs_root) or (os.path.lexists(runs_root) and not os.path.isdir(runs_root)):
        raise Refused("run_dir_unsafe", "cartella delle run non valida (collegamento o non e' una cartella)")
    if not os.path.isdir(runs_root):
        return [], []
    runs, ignored = [], []
    for n in sorted(os.listdir(runs_root)):
        full = os.path.join(runs_root, n)
        if RUN_DIR_RE.match(n):
            if os.path.islink(full) or not os.path.isdir(full):
                raise Refused("run_dir_unsafe", n)
            runs.append(n)
        else:
            ignored.append(n[:80])
    return runs, ignored


# ---- copia di una run ---------------------------------------------------------------------------------------

def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(path, 0o600)


def capture_db(src, dst, fingerprint):
    """Copia consistente (API di backup) e impronta presa nella STESSA transazione di lettura."""
    conn = open_source_db(src)
    try:
        conn.execute("BEGIN")
        fp = fingerprint(conn)
        out = sqlite3.connect(dst)
        try:
            conn.backup(out)
            out.execute("PRAGMA journal_mode=DELETE")
        finally:
            out.close()
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        raise Refused("sqlite_copy_failed", os.path.basename(src))
    finally:
        conn.close()
    for ext in ("-wal", "-shm", "-journal"):
        if os.path.lexists(dst + ext):
            raise Refused("stage_sidecar_leftover", os.path.basename(dst))
    os.chmod(dst, 0o600)
    return fp


def _present_sidecars(run_dir):
    return sorted(n for n in SIDECARS if os.path.lexists(os.path.join(run_dir, n)))


def _observe(run_dir):
    """Impronta leggera della sorgente (per accorgersi di modifiche durante la copia)."""
    jc = open_source_db(os.path.join(run_dir, "journal.db"))
    try:
        j = fingerprint_journal(jc)
    finally:
        jc.close()
    bc = open_source_db(os.path.join(run_dir, "budget.db"))
    try:
        b = fingerprint_budget(bc)
    finally:
        bc.close()
    files = {}
    for n in tuple(n for n in DURABLE_REQUIRED if n.endswith(".json")) + DURABLE_OPTIONAL + CONTROL:
        raw = read_small(os.path.join(run_dir, n), MAX_SMALL[n], required=n in DURABLE_REQUIRED)
        files[n] = None if raw is None else sha256_bytes(raw)
    return {"journal": j, "budget": b, "files": files, "sidecars": _present_sidecars(run_dir)}


def _capture_once(run_dir, stage, extras):
    sidecars_before = _present_sidecars(run_dir)
    j = capture_db(os.path.join(run_dir, "journal.db"), os.path.join(stage, "journal.db"), fingerprint_journal)
    b = capture_db(os.path.join(run_dir, "budget.db"), os.path.join(stage, "budget.db"), fingerprint_budget)
    files = {}
    for n in tuple(n for n in DURABLE_REQUIRED if n.endswith(".json")) + DURABLE_OPTIONAL + CONTROL:
        raw = read_small(os.path.join(run_dir, n), MAX_SMALL[n], required=n in DURABLE_REQUIRED)
        files[n] = None if raw is None else sha256_bytes(raw)
        if raw is not None:
            _write(os.path.join(stage, n), raw)
    tdir = os.path.join(stage, "transient")
    for n in TRANSIENT:
        raw = read_small(os.path.join(run_dir, n), MAX_SMALL[n], required=False)
        if raw is not None:
            os.makedirs(tdir, mode=0o700, exist_ok=True)
            _write(os.path.join(tdir, n), raw)
    for n in extras:
        raw = read_small(os.path.join(run_dir, n), EXTRA_MAX_EACH, required=False)
        if raw is not None:
            os.makedirs(os.path.join(stage, "extra"), mode=0o700, exist_ok=True)
            _write(os.path.join(stage, "extra", n), raw)
    return {"journal": j, "budget": b, "files": files, "sidecars": sidecars_before}


def capture_run(run_dir, stage, now_ms, attempts=3, wait=1.0, hooks=None, anchor=None):
    """Copia + verifica di una run. `stage` e' la cartella di destinazione (creata qui). Restituisce i fatti."""
    run_name = os.path.basename(run_dir.rstrip(os.sep))
    if not RUN_DIR_RE.match(run_name) or os.path.islink(run_dir) or not os.path.isdir(run_dir):
        raise Refused("run_dir_unsafe", run_name)
    hash_at = (anchor["seq_max"],) if anchor else ()
    prefix_ids = (anchor["budget_id_max"],) if anchor and anchor.get("budget_id_max") else ()
    for attempt in range(1, max(1, attempts) + 1):
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage, mode=0o700)
        try:
            extras = scan_run_dir(run_dir)
            cap = _capture_once(run_dir, stage, extras)
            if hooks and hooks.get("after_copy"):
                hooks["after_copy"](attempt)
            if _observe(run_dir) != cap or _present_sidecars(run_dir) != cap["sidecars"]:
                raise Refused("source_changed_during_capture", run_name)
            facts = facts_from_files(stage, run_name, now_ms, hash_at, prefix_ids)
            j, b = facts["journal"], facts["budget"]
            if ({"eventi": j["eventi"], "seq_max": j["seq_max"], "testa": j["testa"]} != cap["journal"]
                    or {"righe": b["righe"], "id_max": b["id_max"], "unita": b["unita"]} != cap["budget"]):
                raise Refused("snapshot_mismatch", run_name)
            facts["file_sha256"] = {k: v for k, v in cap["files"].items() if v is not None}
            facts["extra"] = list(extras)
            facts["database_sorgente"] = {"journal": "ro", "budget": "ro"}
            return facts
        except Refused as e:
            if e.code in ("source_changed_during_capture", "sqlite_busy") and attempt < attempts:
                time.sleep(wait)
                continue
            raise


# ---- vecchio database Brain Free (brain.sqlite3) -------------------------------------------------------------

def inspect_legacy(conn):
    """Stessa misura di backend/v3/backup_certification.py::_inspect (cosi' i valori sono confrontabili)."""
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise Refused("sqlite_integrity_failed", "brain.sqlite3")
        result = conn.execute("SELECT body FROM state WHERE id=1").fetchone()
        if result is None or not isinstance(result[0], str):
            raise Refused("legacy_state_missing")
        state = json.loads(result[0])
        if not isinstance(state, dict) or state.get("mode") != "paper" or not isinstance(state.get("positions"), dict):
            raise Refused("legacy_not_paper")
        stream, count, last = hashlib.sha256(), 0, 0
        for row in conn.execute("SELECT seq,id,kind,ts,body FROM events ORDER BY seq"):
            seq, eid, kind, ts, body = row
            if (type(seq) is not int or seq <= last or not isinstance(eid, str) or not eid
                    or not isinstance(kind, str) or not kind or type(ts) is not int or not isinstance(body, str)):
                raise Refused("legacy_events_invalid", "seq=%s" % seq)
            enc = json.dumps(row, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
            stream.update(len(enc).to_bytes(8, "big"))
            stream.update(enc)
            count, last = count + 1, seq
    except (sqlite3.Error, ValueError):
        raise Refused("legacy_schema_unexpected")
    return {"eventi": count, "seq_max": last, "events_sha256": stream.hexdigest(),
            "state_sha256": sha256_bytes(result[0].encode("utf-8")),
            "account_id": str(state.get("account_id"))[:64], "posizioni_aperte": len(state["positions"])}


def capture_legacy(src, stage, attempts=3, wait=1.0, hooks=None, prev=None):
    """Copia certificata di brain.sqlite3 in stage/brain.sqlite3. Il database storico resta separato dalle run V3."""
    if os.path.islink(src) or not os.path.isfile(src):
        raise Refused("file_missing", os.path.basename(src))
    dst = os.path.join(stage, "brain.sqlite3")
    for attempt in range(1, max(1, attempts) + 1):
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage, mode=0o700)
        conn = open_source_db(src)
        try:
            conn.execute("BEGIN")
            seen = inspect_legacy(conn)
            out = sqlite3.connect(dst)
            try:
                conn.backup(out)
                out.execute("PRAGMA journal_mode=DELETE")
            finally:
                out.close()
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            raise Refused("sqlite_copy_failed", "brain.sqlite3")
        finally:
            conn.close()
        for ext in ("-wal", "-shm", "-journal"):
            if os.path.lexists(dst + ext):
                raise Refused("stage_sidecar_leftover", "brain.sqlite3")
        os.chmod(dst, 0o600)
        if hooks and hooks.get("after_copy"):
            hooks["after_copy"](attempt)
        after = open_source_db(src)
        try:
            again = inspect_legacy(after)
        finally:
            after.close()
        if again != seen:
            if attempt < attempts:
                time.sleep(wait)
                continue
            raise Refused("source_changed_during_capture", "brain.sqlite3")
        copied = open_source_db(dst)
        try:
            checked = inspect_legacy(copied)
        finally:
            copied.close()
        if checked != seen:
            raise Refused("snapshot_mismatch", "brain.sqlite3")
        if prev and (seen["eventi"] < prev.get("eventi", 0) or seen["seq_max"] < prev.get("seq_max", 0)):
            raise Refused("legacy_regressed", "eventi=%d precedenti=%d" % (seen["eventi"], prev.get("eventi", 0)))
        seen["file_sha256"] = sha256_file(dst)
        seen["dimensione"] = os.path.getsize(dst)
        return seen


def verify_legacy_copy(path, expected=None):
    conn = open_source_db(path)
    try:
        facts = inspect_legacy(conn)
    finally:
        conn.close()
    if expected is not None:
        for k in ("eventi", "seq_max", "events_sha256", "state_sha256"):
            if facts[k] != expected.get(k):
                raise Refused("snapshot_mismatch", "legacy:" + k)
    return facts


# ---- ancore, impronta di stato, snapshot completo ----------------------------------------------------------

def anchors_from_facts(facts_list):
    out = {}
    for f in facts_list:
        j, b = f["journal"], f["budget"]
        out[f["run_name"]] = {"eventi": j["eventi"], "seq_max": j["seq_max"], "testa": j["testa"],
                              "budget_righe": b["righe"], "budget_id_max": b["id_max"], "budget_testa": b["testa"]}
    return out


def state_fingerprint(facts_list, legacy):
    core = {}
    for f in facts_list:
        j, b = f["journal"], f["budget"]
        core[f["run_name"]] = {"j": [j["eventi"], j["testa"]], "b": [b["righe"], b["unita"], b["testa"]],
                               "f": f["file_sha256"], "x": f["extra"]}
    return sha256_bytes(canon({"runs": core, "legacy": ({k: legacy[k] for k in ("eventi", "events_sha256",
                                                                               "state_sha256")} if legacy else None)}
                              ).encode())


def check_anchor(facts, anchor):
    j, b = facts["journal"], facts["budget"]
    if (j["eventi"] < anchor["eventi"] or j["seq_max"] < anchor["seq_max"]
            or j["hash_at"].get(anchor["seq_max"]) != anchor["testa"]):
        raise Refused("anchor_regressed", "journal")
    if b["righe"] < anchor["budget_righe"] or (
            anchor.get("budget_id_max") and b["prefisso"].get(anchor["budget_id_max"]) != anchor["budget_testa"]):
        raise Refused("budget_regressed", "budget")


class RunsNotCertifiable(Refused):
    def __init__(self, failures):
        super().__init__("runs_not_certifiable", "; ".join("%s=%s" % (n, c) for n, c, _d in failures))
        self.failures = failures


def build_runs_snapshot(runs_root, stage, now_ms, only=(), prev_anchors=None, attempts=3, wait=1.0, hooks=None):
    """Certifica e copia TUTTE le run (atomico: una sola non certificabile = nessuna copia). -> (fatti, ignorati)."""
    prev_anchors = prev_anchors or {}
    runs, ignored = discover_runs(runs_root)
    if only:
        missing = [n for n in only if n not in runs]
        if missing:
            raise Refused("run_not_found", ",".join(missing)[:200])
        runs = [n for n in runs if n in only]
    facts_list, failures = [], []
    os.makedirs(os.path.join(stage, "runs"), mode=0o700, exist_ok=True)
    for name in runs:
        try:
            anchor = prev_anchors.get(name)
            f = capture_run(os.path.join(runs_root, name), os.path.join(stage, "runs", name), now_ms, attempts,
                            wait, hooks, anchor)
            if anchor:
                check_anchor(f, anchor)
            for k in ("hash_at",):
                f["journal"].pop(k, None)
            f["budget"].pop("prefisso", None)
            facts_list.append(f)
        except Refused as e:
            failures.append((name, e.code, e.detail))
    seen_ids = {}
    for f in facts_list:
        for key in (("run_id", f["run_id"]), ("identita", f["identita_sha256"])):
            seen_ids.setdefault(key, []).append(f["run_name"])
    for names in seen_ids.values():
        if len(names) > 1:                                          # una copia di una run sotto un altro nome
            failures.extend((n, "identity_duplicated", ",".join(names)) for n in names
                            if not any(x[0] == n and x[1] == "identity_duplicated" for x in failures))
    if not only:
        for gone in sorted(set(prev_anchors) - set(runs)):
            failures.append((gone, "run_missing_since_last_backup", ""))
    if failures:
        raise RunsNotCertifiable(failures)
    return facts_list, ignored
