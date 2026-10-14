"""Valutazione del pool: giornale -> evidenze -> stati (promozione/ritiro)."""
from __future__ import annotations

from typing import Optional

from rule_pool import allocator as alloc
from rule_pool import evidence as ev
from rule_pool.journal import Journal
from rule_pool.rules import Rule, promotable_count


def rule_evidence(journal: Journal, rule: Rule, control: Optional[Rule], venue: str) -> alloc.RuleEvidence:
    times, net = journal.closed_arrays(rule.rule_id, rule.version, venue)
    summary = ev.summarize(times, net)
    excess = None
    if control is not None and len(net):
        _, cnet = journal.closed_arrays(control.rule_id, control.version, venue)
        if len(cnet):
            excess = float(net.mean() - cnet.mean())
    return alloc.RuleEvidence(
        summary=summary,
        halves_ok=ev.halves_positive(times, net) if len(net) >= 2 else False,
        excess=excess,
        live=ev.summarize(*journal.closed_arrays(rule.rule_id, rule.version, "live")))


def evaluate_pool(journal: Journal, rules: list, gate: ev.Gate = ev.Gate(), venue: str = "replay",
                  live_enabled: bool = False) -> dict:
    """Aggiorna e salva lo stato di ogni regola promuovibile. Il live e' spento di default."""
    for r in rules:
        journal.register_rule(r)
    k = promotable_count(rules)
    promos = [r for r in rules if r.kind == "promotable"]
    controls = [r for r in rules if r.kind == "control"]
    ctrl_for = {c.base_rule: c for c in controls}
    evidences = {r.rule_id: rule_evidence(journal, r, ctrl_for.get(r.rule_id), venue) for r in promos}
    alarm = ev.control_alarm(
        [ev.summarize(*journal.closed_arrays(c.rule_id, c.version, venue)) for c in controls], k, gate)
    states = {r.rule_id: alloc.State(journal.get_state(r.rule_id, r.version) or "CANDIDATA")
              for r in promos}
    decisions = alloc.decide(states, evidences, k, gate, live_enabled, alarm)
    by_id = {r.rule_id: r for r in promos}
    prior = {rid: journal.get_state(rid, by_id[rid].version) for rid in decisions}
    changed = [rid for rid, (st, why) in decisions.items()
               if journal.set_state(rid, by_id[rid].version, st.value, why)]
    # prior None = primo avvio: non e' una transizione da notificare
    transitions = [(rid, prior[rid], decisions[rid][0].value, decisions[rid][1]) for rid in changed]
    return {"k": k, "alarm": alarm, "decisions": decisions, "changed": changed,
            "transitions": transitions, "evidence": evidences}
