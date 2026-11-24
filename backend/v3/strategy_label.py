"""L1 — etichetta della strategia (``strategy_id`` + ``strategy_origin``): regola unica.

Il Brain deve poter dire *quale strategia* ha motivato un'apertura, perché ogni
esito possa essere attribuito e il tabellone dei voti (F7) possa misurare
strategia × regime × lato. Questa è l'UNICA definizione di cosa è un'etichetta
valida; la usano il motore (prima di scrivere nel journal) e l'estrattore degli
esiti (quando rilegge il journal), così le due parti non possono divergere.

Regole
------
* Un'etichetta è una coppia ``(strategy_id, strategy_origin)``. O vale tutta o non
  vale: se una delle due parti manca o non è valida si restituisce ``("", "")``.
  Un'etichetta cattiva NON blocca mai un trade e non viene mai riparata: viene
  scartata (il trade resta, senza attribuzione).
* ``strategy_origin``: ``"library"`` (una scheda della biblioteca strategica, per
  esempio ``S07``) oppure ``"ai_proposed"`` (una proposta del Brain, ``AI_...``).
* ``strategy_id``: token chiuso ``^[A-Z][A-Z0-9_]{0,31}$`` (nessun testo libero,
  nessuno spazio, nessun carattere di controllo): il testo di un modello non
  entra mai nel journal. Gli identificatori ``ai_proposed`` iniziano per ``AI_``
  e hanno almeno un carattere dopo il prefisso; quelli ``library`` non possono
  iniziare per ``AI_`` (i due spazi dei nomi non si sovrappongono).
* Se si passa ``allowed_library_ids`` (insieme), un'etichetta ``library`` vale
  solo se l'id è nell'insieme (il motore passa sempre l'elenco; un insieme vuoto
  scarta ogni etichetta ``library``). Con ``None`` l'appartenenza non si controlla
  (l'estrattore degli esiti registra ciò che il journal dice).
* Tipi esatti: ``bool``, ``bytes``, sottoclassi di ``str`` e valori non stringa
  vengono scartati. Nessuna eccezione esce da qui.

Nessuna soglia, nessun limite di rischio, nessun parametro di strategia.
"""
from __future__ import annotations

import re
from typing import AbstractSet, Optional

STRATEGY_ORIGINS = frozenset({"library", "ai_proposed"})
AI_PREFIX = "AI_"
STRATEGY_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def is_valid_strategy_id(value: object) -> bool:
    """True se ``value`` è una ``str`` esatta che rispetta il token chiuso."""
    return type(value) is str and STRATEGY_ID_RE.fullmatch(value) is not None


def normalize_label(strategy_id: object, strategy_origin: object,
                    allowed_library_ids: Optional[AbstractSet[str]] = None) -> tuple[str, str]:
    """-> ``(strategy_id, strategy_origin)`` validi, oppure ``("", "")``."""
    if type(strategy_origin) is not str or strategy_origin not in STRATEGY_ORIGINS:
        return "", ""
    if not is_valid_strategy_id(strategy_id):
        return "", ""
    sid = strategy_id  # type: ignore[assignment]
    if strategy_origin == "ai_proposed":
        if not sid.startswith(AI_PREFIX) or len(sid) == len(AI_PREFIX):
            return "", ""
        return sid, strategy_origin
    if sid.startswith(AI_PREFIX):
        return "", ""
    if allowed_library_ids is not None and sid not in allowed_library_ids:
        return "", ""
    return sid, strategy_origin
