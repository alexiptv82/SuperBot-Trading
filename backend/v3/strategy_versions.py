"""Brain Live Evolution (24/11/2026): strategie versionate e aggiornabili SENZA reset della run.

Regola principale: una versione vale solo per le NUOVE aperture. Ogni ``paper_open`` registra la versione e la
fotografia delle regole d'uscita con cui e' nato (``payload["strategy"]``); il servizio delle uscite gestisce ogni
posizione con la SUA fotografia (le posizioni senza fotografia restano sulla configurazione di base della run, che
non cambia mai). Journal, capitale e salvadanaio non si toccano.

* Base = ``runner_config.json`` della run (versione ``V1``, implicita). Una versione e' una SOVRAPPOSIZIONE cumulativa
  alla base, limitata ai parametri di ``ALLOWED``: frequenza dei giri, uscite (take profit, pareggio, trailing,
  protezione), presa parziale, consulti di Claude, revisione delle posizioni, note strategiche per il prompt.
  Rischio, leva, margini, capitale, perdite giornaliere, Guardian, salvadanaio, budget AI, mercati, modello e mandato
  NON sono modificabili da qui: richiedono le autorizzazioni e i rilasci di sempre.
* Journal (append-only, mai riscritto): ``strategy_version`` (registrazione: versione, genitore, sovrapposizione,
  impronte, motivo, approvazione) e ``strategy_switch`` (da quale a quale versione, motivo, approvazione, rollback).
  La versione attiva e' l'ultimo ``strategy_switch`` (nessuno = ``V1``).
* Canale dell'operatore (solo root, ``strategia.py``): ``proponi`` interpreta la richiesta in italiano e salva una
  proposta strutturata; ``approva`` scrive ``strategy_request.json``. Il runner, fra un giro e l'altro, la rivalida,
  scrive gli eventi (un solo ``append`` per evento: atomico), poi si ricostruisce con la nuova versione: vale dal
  giro successivo. Il servizio delle uscite non si ferma mai. DeepSeek e Claude non scrivono mai richieste.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.v3.events import Event, EventJournal

VERSION_KIND, SWITCH_KIND = "strategy_version", "strategy_switch"
BASE_VERSION = "V1"
REQUEST_FILE, RESULT_FILE, PROPOSALS_DIR = "strategy_request.json", "strategy_result.json", "strategy_proposals"
NOTES_KEY = "strategy_notes"
_VERSION_RE = re.compile(r"V([1-9][0-9]{0,3})")
_ID_RE = re.compile(r"[0-9a-f]{10}")
MAX_NOTES = 600


class StrategyError(ValueError):
    """Richiesta non valida, non compresa o non consentita (messaggio in italiano per l'operatore)."""


def _dec(lo: str, hi: str, *, nullable: bool = False):
    def check(v):
        if v is None and nullable:
            return None
        try:
            d = Decimal(str(v).replace(",", "."))
        except (InvalidOperation, ValueError):
            raise StrategyError("valore non numerico") from None
        if not d.is_finite() or not Decimal(lo) <= d <= Decimal(hi):
            raise StrategyError(f"valore fuori intervallo ({lo}-{hi})")
        return str(d.normalize()) if d != d.to_integral() else str(d.quantize(Decimal(1)))
    return check


def _int(allowed):
    def check(v):
        if type(v) is not int or v not in allowed:
            raise StrategyError("valore non ammesso: " + ", ".join(str(x) for x in sorted(allowed)))
        return v
    return check


def _choice(allowed):
    def check(v):
        if v not in allowed:
            raise StrategyError("valore non ammesso: " + ", ".join(allowed))
        return v
    return check


def _bool(v):
    if type(v) is not bool:
        raise StrategyError("valore non ammesso (si/no)")
    return v


def _notes(v):
    if v is None:
        return None
    if type(v) is not str or not 1 <= len(v.strip()) <= MAX_NOTES or any(ord(c) < 32 and c != " " for c in v):
        raise StrategyError(f"note strategiche: testo semplice, al massimo {MAX_NOTES} caratteri")
    return " ".join(v.split())


# percorso nella configurazione -> controllo (intervalli prudenti; i limiti di rischio restano al RiskManager)
ALLOWED: dict[str, Any] = {
    "cycle_minutes": _int({15, 30, 45, 60}),
    "exit_policy.take_profit_r": _dec("1", "10"),
    "exit_policy.be_at_r": _dec("0.5", "5", nullable=True),
    "exit_policy.trail_at_r": _dec("0.5", "10", nullable=True),
    "exit_policy.trail_dist_r": _dec("0.25", "5", nullable=True),
    "exit_policy.protect_at_r": _dec("0.5", "10", nullable=True),
    "exit_policy.protect_frac": _dec("0.1", "0.9", nullable=True),
    "brain_unico.partial_take_profit.fraction": _dec("0.1", "0.9"),
    "brain_unico.partial_take_profit.at_r": _dec("0.5", "5"),
    "brain_unico.claude_consult.max_per_cycle": _int(set(range(0, 9))),
    "brain_unico.claude_consult.cooldown_minutes": _int(set(range(0, 721))),
    "brain_unico.position_review": _bool,
    # politica d'ingresso e di gestione (entry_policy.py): filtri, consulto, guardia sugli stop, secondo ingresso
    "brain_unico.entry_policy.long_trend_filter": _bool,
    "brain_unico.entry_policy.max_cost_fraction_r": _dec("0.05", "1", nullable=True),
    "brain_unico.entry_policy.consult_conf_tier_a": _dec("0.4", "0.9"),
    "brain_unico.entry_policy.consult_conf_other": _dec("0.4", "0.9"),
    "brain_unico.entry_policy.consult_on_expansion": _bool,
    "brain_unico.entry_policy.consult_limit_fallback": _choice(("veto", "half_risk")),
    "brain_unico.entry_policy.stop_guard_atr_mult": _dec("0.1", "5", nullable=True),
    "brain_unico.entry_policy.stop_guard_cost_zone": _bool,
    "brain_unico.entry_policy.scale_in_min_gap_r": _dec("0.1", "2"),
    "brain_unico.entry_policy.scale_in_min_stop_room_r": _dec("0.1", "2"),
    NOTES_KEY: _notes,                                   # fuori dalla configurazione: entra nel prompt di DeepSeek
}
LABELS = {
    "cycle_minutes": "frequenza di analisi (minuti)",
    "exit_policy.take_profit_r": "take profit finale (R)",
    "exit_policy.be_at_r": "stop a pareggio da (R)",
    "exit_policy.trail_at_r": "trailing da (R)",
    "exit_policy.trail_dist_r": "distanza del trailing (R)",
    "exit_policy.protect_at_r": "protezione del profitto da (R)",
    "exit_policy.protect_frac": "quota di profitto protetta",
    "brain_unico.partial_take_profit.fraction": "chiusura parziale (quota)",
    "brain_unico.partial_take_profit.at_r": "chiusura parziale a (R)",
    "brain_unico.claude_consult.max_per_cycle": "consulti di Claude per giro",
    "brain_unico.claude_consult.cooldown_minutes": "attesa fra consulti sullo stesso mercato (minuti)",
    "brain_unico.position_review": "revisione AI delle posizioni",
    "brain_unico.entry_policy.long_trend_filter": "LONG solo con trend 1h e 4h a favore",
    "brain_unico.entry_policy.max_cost_fraction_r": "costi massimi in quota di 1R",
    "brain_unico.entry_policy.consult_conf_tier_a": "consulto sotto confidenza (BTC, ETH, oro, argento)",
    "brain_unico.entry_policy.consult_conf_other": "consulto sotto confidenza (altri)",
    "brain_unico.entry_policy.consult_on_expansion": "consulto anche per il solo regime EXPANSION",
    "brain_unico.entry_policy.consult_limit_fallback": "se Claude non e' consultabile",
    "brain_unico.entry_policy.stop_guard_atr_mult": "stop AI: distanza minima in ATR 1h",
    "brain_unico.entry_policy.stop_guard_cost_zone": "stop AI: rifiuto nella zona dei costi",
    "brain_unico.entry_policy.scale_in_min_gap_r": "secondo ingresso: miglioramento minimo (R)",
    "brain_unico.entry_policy.scale_in_min_stop_room_r": "secondo ingresso: distanza minima dallo stop (R)",
    NOTES_KEY: "note strategiche per DeepSeek",
}
FORBIDDEN = re.compile(r"\b(leva|leve|leverage|rischi\w*|risk\w*|margin\w*|capitale|perdit\w* giornalier\w*|daily loss"
                       r"|mandat\w*|budget|salvadanaio|guardian|equity|slot|posizioni massime|simboli|strumenti"
                       r"|modello|chiav\w*|live|denaro reale)\b")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_overlay(overlay: Mapping) -> dict:
    """Solo percorsi ammessi, valori normalizzati. Un percorso non ammesso e' un rifiuto, mai un'omissione."""
    if not isinstance(overlay, Mapping):
        raise StrategyError("sovrapposizione non valida")
    out = {}
    for k, v in overlay.items():
        if k not in ALLOWED:
            raise StrategyError(f"parametro non modificabile senza autorizzazione: {k}")
        out[k] = ALLOWED[k](v)
    return out


def apply_overlay(base_bytes: bytes, overlay: Mapping) -> bytes:
    """Byte della configurazione effettiva = base + sovrapposizione (note escluse), validati dal caricatore ufficiale."""
    from backend.v3.runner.config import load_runner_config
    data = json.loads(base_bytes.decode("utf-8"))
    for path, value in validate_overlay(overlay).items():
        if path == NOTES_KEY:
            continue
        node, keys = data, path.split(".")
        for k in keys[:-1]:
            if not isinstance(node.get(k), dict):
                raise StrategyError(f"la configurazione di base non ha {path}")
            node = node[k]
        if keys[-1] not in node:
            raise StrategyError(f"la configurazione di base non ha {path}")
        node[keys[-1]] = value
    raw = json.dumps(data, indent=2).encode()
    try:
        load_runner_config(raw)
    except ValueError:
        raise StrategyError("la configurazione risultante non e' valida") from None
    return raw


@dataclass(frozen=True)
class Version:
    name: str
    parent: Optional[str]
    overlay: dict
    description: str = ""
    registered_at_ms: Optional[int] = None


@dataclass
class Registry:
    versions: dict = field(default_factory=lambda: {BASE_VERSION: Version(BASE_VERSION, None, {}, "configurazione di base")})
    active: str = BASE_VERSION
    history: list = field(default_factory=list)          # strategy_switch, dal piu' vecchio

    def previous(self) -> Optional[str]:
        return self.history[-1]["from"] if self.history else None

    def next_name(self) -> str:
        return f"V{max(int(v[1:]) for v in self.versions) + 1}"


def base_version_of(base_bytes: Optional[bytes]) -> str:
    try:
        name = json.loads(base_bytes.decode("utf-8"))["brain_unico"].get("strategy_version", BASE_VERSION)
    except Exception:
        return BASE_VERSION
    return name if isinstance(name, str) and _VERSION_RE.fullmatch(name) else BASE_VERSION


def read_registry(journal: EventJournal, run_id: str, base_bytes: Optional[bytes] = None) -> Registry:
    base = base_version_of(base_bytes)
    reg = Registry(versions={base: Version(base, None, {}, "configurazione di base")}, active=base)
    for r in journal.list_run_kinds_since("brain", run_id, (VERSION_KIND, SWITCH_KIND), 0):
        p = r.event.payload if isinstance(r.event.payload, dict) else {}
        if r.event.kind == VERSION_KIND and _VERSION_RE.fullmatch(str(p.get("version"))):
            try:
                ov = validate_overlay(p.get("overlay") or {})
            except StrategyError:
                continue                                  # mai: le registrazioni sono validate prima di scriverle
            reg.versions[p["version"]] = Version(p["version"], p.get("parent"), ov, str(p.get("description", "")),
                                                 r.event.occurred_at_ms)
        elif r.event.kind == SWITCH_KIND and p.get("to") in reg.versions:
            reg.active = p["to"]
            reg.history.append(dict(p, at_ms=r.event.occurred_at_ms))
    return reg


@dataclass(frozen=True)
class Effective:
    config: Any                                           # RunnerConfig
    version: str
    notes: Optional[str]
    raw: bytes

    def snapshot(self) -> dict:
        """Fotografia per ``paper_open``: versione e regole d'uscita con cui la posizione nasce."""
        data = json.loads(self.raw.decode("utf-8"))
        snap = {"version": self.version, "exit_policy": data.get("exit_policy")}
        part = (data.get("brain_unico") or {}).get("partial_take_profit")
        if part is not None:
            snap["partial_take_profit"] = part
        entry = (data.get("brain_unico") or {}).get("entry_policy")
        if entry is not None:                    # guardia sugli stop e secondo ingresso della versione della posizione
            snap["entry_policy"] = entry
        return snap


def effective(base_bytes: bytes, registry: Registry) -> Effective:
    from backend.v3.runner.config import load_runner_config
    v = registry.versions[registry.active]
    raw = apply_overlay(base_bytes, v.overlay) if v.overlay else base_bytes
    return Effective(load_runner_config(raw), v.name, v.overlay.get(NOTES_KEY), raw)


# ----------------------------------------------------------------------------- interprete delle richieste
_NUM = r"(\d+(?:[.,]\d+)?)"
SUPPORTED = (
    "«Da questo momento esamina i mercati ogni 15 minuti» (15, 30, 45 o 60)",
    "«Per le nuove aperture usa la strategia V3» · «Torna alla versione precedente» · «Rollback a V2»",
    "«Take profit finale a 3 R»",
    "«Chiusura parziale del 35 % a 2 R»",
    "«Stop a pareggio da 1,5 R» · «Senza pareggio»",
    "«Trailing da 2,5 R a distanza 1 R» · «Senza trailing»",
    "«Proteggi il 50 % del profitto da 2 R» · «Senza protezione»",
    "«Massimo 2 consulti di Claude per giro» · «Attesa fra consulti 60 minuti»",
    "«Revisione delle posizioni attiva/disattiva»",
    "«Nota strategica: …» (testo per DeepSeek, al massimo 600 caratteri) · «Rimuovi le note»",
)


@dataclass(frozen=True)
class Proposal:
    id: str
    text: str
    action: str                                           # new_version | activate
    version: str
    parent: str
    overlay: dict                                         # cumulativa rispetto alla base (new_version)
    changes: tuple                                        # (percorso, prima, dopo)
    rollback: bool
    created_ms: int

    def as_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "action": self.action, "version": self.version,
                "parent": self.parent, "overlay": self.overlay, "changes": [list(c) for c in self.changes],
                "rollback": self.rollback, "created_ms": self.created_ms, "overlay_sha": _sha(self.overlay)}


def _parse_changes(text: str) -> dict:
    t = " ".join(text.lower().replace("’", "'").split())
    ch: dict = {}
    m = re.match(r"^\s*(?:nota|note)(?: strategic[ah]e?)?\s*:\s*(.+)$", text.strip(), re.I | re.S)
    if m:
        return {NOTES_KEY: m.group(1).strip()}
    if re.search(r"(rimuovi|togli|cancella|elimina) (le |la )?not", t):
        ch[NOTES_KEY] = None
    if re.search(r"ogni ora\b", t):
        ch["cycle_minutes"] = 60
    elif re.search(r"ogni mezz'?ora", t):
        ch["cycle_minutes"] = 30
    else:
        m = re.search(r"ogni (\d+) ?min", t)
        if m:
            ch["cycle_minutes"] = int(m.group(1))
    m = re.search(r"take[ -]?profit(?: finale)?(?: a| di| al)? " + _NUM + r" ?r\b", t)
    if m:
        ch["exit_policy.take_profit_r"] = m.group(1)
    m = re.search(r"(?:chiusura |presa )?parziale(?: del| di| al)? " + _NUM + r" ?%(?: a| al)? " + _NUM + r" ?r\b", t)
    if m:
        ch["brain_unico.partial_take_profit.fraction"] = str(Decimal(m.group(1).replace(",", ".")) / 100)
        ch["brain_unico.partial_take_profit.at_r"] = m.group(2)
    if re.search(r"senza (?:stop a )?(?:pareggio|break[ -]?even)", t):
        ch["exit_policy.be_at_r"] = None
    else:
        m = re.search(r"(?:pareggio|break[ -]?even)(?: da| a)? " + _NUM + r" ?r\b", t)
        if m:
            ch["exit_policy.be_at_r"] = m.group(1)
    if re.search(r"senza trailing", t):
        ch["exit_policy.trail_at_r"] = None
        ch["exit_policy.trail_dist_r"] = None
    else:
        m = re.search(r"trailing(?: da| a)? " + _NUM + r" ?r(?:.*?distanza(?: di)? " + _NUM + r" ?r)?", t)
        if m:
            ch["exit_policy.trail_at_r"] = m.group(1)
            if m.group(2):
                ch["exit_policy.trail_dist_r"] = m.group(2)
    if re.search(r"senza protezione", t):
        ch["exit_policy.protect_at_r"] = None
        ch["exit_policy.protect_frac"] = None
    else:
        m = re.search(r"protegg\w* (?:il )?" + _NUM + r" ?% (?:del (?:profitto|guadagno) )?(?:da|a) " + _NUM + r" ?r\b", t)
        if m:
            ch["exit_policy.protect_frac"] = str(Decimal(m.group(1).replace(",", ".")) / 100)
            ch["exit_policy.protect_at_r"] = m.group(2)
    m = re.search(r"(?:massimo |al massimo )?(\d+) consult\w*(?: di claude)? (?:per|a|ogni) giro", t)
    if m:
        ch["brain_unico.claude_consult.max_per_cycle"] = int(m.group(1))
    m = re.search(r"attesa fra (?:i )?consulti(?: di)? (\d+) ?min", t)
    if m:
        ch["brain_unico.claude_consult.cooldown_minutes"] = int(m.group(1))
    if re.search(r"revisione (?:delle |della )?posizion\w* (?:attiva|accesa|on)\b", t):
        ch["brain_unico.position_review"] = True
    elif re.search(r"revisione (?:delle |della )?posizion\w* (?:disattiva|spenta|off)\b", t):
        ch["brain_unico.position_review"] = False
    return ch


def _current_value(base: dict, overlay: Mapping, path: str):
    if path in overlay:
        return overlay[path]
    if path == NOTES_KEY:
        return None
    node = base
    for k in path.split("."):
        node = node.get(k) if isinstance(node, dict) else None
    return node


def propose(text: str, registry: Registry, base_bytes: bytes, now_ms: int) -> Proposal:
    """Richiesta in linguaggio naturale -> proposta strutturata e validata (nessuna scrittura)."""
    if type(text) is not str or not 3 <= len(text.strip()) <= 1000:
        raise StrategyError("richiesta vuota o troppo lunga")
    pid = hashlib.sha256(f"{text}|{now_ms}".encode()).hexdigest()[:10]
    t = text.lower()
    is_note = re.match(r"^\s*(?:nota|note)", t) is not None
    m = re.search(r"\b(?:usa|attiva|passa a|adotta)\b.*?\b(?:strategia|versione)\s+(v\d+)", t)
    rb = re.search(r"\b(?:torna|ritorna|ripristina|rollback)\b(?:.*?\b(v\d+)\b)?", t)
    if (m or rb) and not is_note:
        target = (m.group(1) if m else (rb.group(1) or "")).upper()
        if not target:
            target = registry.previous() or ""
            if not target:
                raise StrategyError("non c'e' una versione precedente a cui tornare")
        if target not in registry.versions:
            raise StrategyError(f"la versione {target} non esiste; versioni: " + ", ".join(sorted(registry.versions)))
        if target == registry.active:
            raise StrategyError(f"{target} e' gia' la versione attiva")
        return Proposal(pid, text, "activate", target, registry.active, registry.versions[target].overlay,
                        (("versione per le nuove aperture", registry.active, target),), bool(rb) and not m, now_ms)
    if not is_note and FORBIDDEN.search(t):
        raise StrategyError("rischio, leva, margini, capitale, perdite, mandato, budget, mercati e modello non si "
                            "cambiano con un comando: servono autorizzazione e rilascio")
    ch = _parse_changes(text)
    if not ch:
        raise StrategyError("richiesta non compresa. Esempi: " + " | ".join(SUPPORTED))
    ch = validate_overlay(ch)
    cur = registry.versions[registry.active].overlay
    base = json.loads(base_bytes.decode("utf-8"))
    overlay = dict(cur)
    changes = []
    for k, v in ch.items():
        before = _current_value(base, cur, k)
        if before == v:
            continue
        changes.append((k, before, v))
        if v is None and k == NOTES_KEY:
            overlay.pop(k, None)
        else:
            overlay[k] = v
    if not changes:
        raise StrategyError("nessuna differenza rispetto alla versione attiva " + registry.active)
    for k in list(overlay):                              # niente sovrapposizioni uguali alla base
        if k != NOTES_KEY and _current_value(base, {}, k) == overlay[k]:
            overlay.pop(k)
    apply_overlay(base_bytes, overlay)                   # la configurazione risultante deve essere valida
    for name, v in registry.versions.items():
        if v.overlay == overlay:
            return Proposal(pid, text, "activate", name, registry.active, overlay, tuple(changes), False, now_ms)
    return Proposal(pid, text, "new_version", registry.next_name(), registry.active, overlay, tuple(changes),
                    False, now_ms)


def describe(p: Proposal) -> list[str]:
    out = [f"Proposta {p.id}: " + ("NUOVA versione " if p.action == "new_version" else "attiva la versione ")
           + f"{p.version} (ora attiva: {p.parent})" + (" — ROLLBACK" if p.rollback else "")]
    for k, a, b in p.changes:
        out.append(f"  · {LABELS.get(k, k)}: {a if a is not None else 'nessuno'} → {b if b is not None else 'nessuno'}")
    out.append("  Vale per le NUOVE aperture dal giro successivo; le posizioni aperte completano la loro versione.")
    return out


# ----------------------------------------------------------------------------- file di proposta / richiesta
def _atomic_write(path: Path, obj, *, like: Optional[Path] = None) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, sort_keys=True, indent=1)
        if like is not None:
            st = like.stat()
            os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_proposal(data_dir: Path, p: Proposal) -> Path:
    d = data_dir / PROPOSALS_DIR
    d.mkdir(mode=0o750, exist_ok=True)
    st = data_dir.stat()
    try:
        os.chown(d, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    path = d / f"{p.id}.json"
    _atomic_write(path, p.as_dict(), like=data_dir)
    return path


def load_proposal(data_dir: Path, pid: str) -> dict:
    if type(pid) is not str or not _ID_RE.fullmatch(pid):
        raise StrategyError("identificativo di proposta non valido")
    try:
        return json.loads((data_dir / PROPOSALS_DIR / f"{pid}.json").read_text())
    except (OSError, ValueError):
        raise StrategyError("proposta inesistente") from None


def approve(data_dir: Path, pid: str, approved_by: str, reason: str, now_ms: int) -> dict:
    """Scrive ``strategy_request.json`` (atomico). Una sola richiesta alla volta."""
    req_path = data_dir / REQUEST_FILE
    if req_path.exists():
        raise StrategyError("c'e' gia' una richiesta in attesa del runner")
    prop = load_proposal(data_dir, pid)
    req = {"proposal": prop, "approved_by": str(approved_by)[:60], "approved_at_ms": now_ms,
           "reason": " ".join(str(reason or prop.get("text", "")).split())[:300]}
    _atomic_write(req_path, req, like=data_dir)
    return req


# ----------------------------------------------------------------------------- applicazione (solo runner)
def apply_request(*, journal: EventJournal, data_dir: Path, run_id: str, base_bytes: bytes, now_ms: int) -> Optional[dict]:
    """Se c'e' una richiesta approvata: la rivalida sulla situazione ATTUALE, scrive gli eventi e l'esito.
    Restituisce l'esito (``ok`` True/False) oppure None se non c'e' nessuna richiesta."""
    req_path = data_dir / REQUEST_FILE
    if not req_path.is_file():
        return None
    try:
        req = json.loads(req_path.read_text())
        prop = req["proposal"]
        reg = read_registry(journal, run_id, base_bytes)
        if prop.get("parent") != reg.active:
            raise StrategyError(f"proposta superata: era per {prop.get('parent')}, ora e' attiva {reg.active}")
        overlay = validate_overlay(prop.get("overlay") or {})
        if _sha(overlay) != prop.get("overlay_sha"):
            raise StrategyError("proposta alterata")
        apply_overlay(base_bytes, overlay)
        name = prop.get("version")
        if not _VERSION_RE.fullmatch(str(name)):
            raise StrategyError("nome di versione non valido")
        approval = {"approved_by": req.get("approved_by"), "approved_at_ms": req.get("approved_at_ms"),
                    "request_id": prop.get("id"), "request_text": str(prop.get("text", ""))[:500]}
        if prop.get("action") == "new_version":
            if name in reg.versions or name != reg.next_name():
                raise StrategyError("versione gia' esistente")
            journal.append(Event(f"strategy_version.{run_id}.{name}", "brain", run_id, VERSION_KIND, now_ms,
                                 "operator.strategy", {"version": name, "parent": reg.active, "overlay": overlay,
                                                        "overlay_sha": _sha(overlay),
                                                        "base_sha": hashlib.sha256(base_bytes).hexdigest(),
                                                        "description": "; ".join(f"{LABELS.get(k, k)}: {b}"
                                                                                 for k, _a, b in prop["changes"])[:500],
                                                        **approval}))
        elif name not in reg.versions or reg.versions[name].overlay != overlay:
            raise StrategyError("versione da attivare inesistente o diversa")
        journal.append(Event(f"strategy_switch.{run_id}.{prop['id']}", "brain", run_id, SWITCH_KIND, now_ms,
                             "operator.strategy", {"from": reg.active, "to": name, "rollback": bool(prop.get("rollback")),
                                                    "reason": str(req.get("reason", ""))[:300],
                                                    "effective": "next_cycle_new_opens_only", **approval}))
        result = {"ok": True, "id": prop.get("id"), "from": reg.active, "to": name, "at_ms": now_ms}
    except (StrategyError, KeyError, TypeError, ValueError, OSError) as exc:
        result = {"ok": False, "error": str(exc)[:300] or type(exc).__name__, "at_ms": now_ms}
    try:
        _atomic_write(data_dir / RESULT_FILE, result)
    finally:
        try:
            req_path.unlink()
        except OSError:
            pass
    return result


def strategy_view(journal: EventJournal, run_id: str, base_bytes: Optional[bytes] = None) -> dict:
    """Per la dashboard: versione attiva, versioni e cronologia dei cambi (sola lettura)."""
    reg = read_registry(journal, run_id, base_bytes)
    return {"active": reg.active,
            "versions": [{"version": v.name, "parent": v.parent, "description": v.description,
                          "registered_at_ms": v.registered_at_ms} for v in reg.versions.values()],
            "history": [{"from": h.get("from"), "to": h.get("to"), "rollback": bool(h.get("rollback")),
                         "reason": h.get("reason"), "approved_by": h.get("approved_by"), "at_ms": h.get("at_ms")}
                        for h in reg.history[-20:]]}
