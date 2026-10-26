"""Operator intent is explicit without misrepresenting installed capabilities."""
import copy
import json
import tempfile
import unittest

from director.brain_pilot import mandate, learning as lm, prompt_builder as pb
from director.brain_pilot.pilot import Pilot, config
from test_brain_pilot_v1 import NOW, Cache, Model
from test_brain_pilot_learning import CFG, memory, SUMMARIES


class OperatorMandateTests(unittest.TestCase):
    def test_prompt_receives_user_objective_and_real_capabilities_without_risk_change(self):
        with tempfile.TemporaryDirectory() as root:
            model=Model();p=Pilot(root,"fake",Cache(),model,cfg=CFG)
            self.addCleanup(p.close)
            before=copy.deepcopy(p.portfolio.account.to_dict()["limits"])
            p.run_once(NOW+15000)
            m=model.calls[0]["operator_mandate"]
            self.assertEqual(m["requested_style"],"adaptive_scalp")
            self.assertFalse(m["duration"]["fixed_exit_timer"])
            self.assertEqual(m["duration"]["reference_minutes"],[[1,5],[5,15]])
            self.assertEqual(m["classical_basis"]["history_status"],"not_imported")
            self.assertEqual(m["classical_basis"]["live_classical_signals"],"not_connected")
            self.assertEqual(m["active_execution"]["decision_interval_minutes"],15)
            self.assertFalse(m["active_execution"]["fast_exit_supervisor"])
            self.assertEqual(m["active_execution"]["max_margin_per_position"],100)
            self.assertEqual(m["requested_margin_reference"]["maximum"],350)
            self.assertEqual(m["readiness"],"full_scalp_engine_not_implemented")
            self.assertEqual(before,p.portfolio.account.to_dict()["limits"])
            attempts=[json.loads(row[0]) for row in p.store.db.execute("SELECT body FROM events WHERE kind='journal'")]
            self.assertEqual(next(e for e in attempts if e["kind"]=="model_attempt")["operator_mandate"],m)

    def test_no_fixed_high_roi_or_aged_winner_requirement(self):
        self.assertNotIn("about 25-30%",pb.SYSTEM)
        self.assertNotIn("an aged winner",pb.SYSTEM)
        self.assertIn("NET profit",pb.SYSTEM)
        self.assertIn("Actual active_execution limits",pb.SYSTEM)
        self.assertIn("not forced exit timers",pb.SYSTEM)
        self.assertIn(mandate.VERSION,config().prompt_version)

    def test_absent_capabilities_and_sources_never_fabricated(self):
        m=mandate.build({},None)
        self.assertEqual(m["active_execution"],{"status":"unknown"})
        self.assertEqual(m["classical_basis"]["history_status"],"not_imported")
        self.assertEqual(mandate.build({}, {"transferred_experience":{"status":"unavailable"}})["classical_basis"]["history_status"],"unavailable")

    def test_legacy_context_does_not_gain_new_operator_version(self):
        ctx=lm.entry_context({"trend":{"1d":"down","4h":"down"}},"test-model")
        ctx.pop("operator_policy_version")
        self.assertEqual(lm.context(ctx)["operator_policy_version"],"unknown")

    def test_old_and_new_mandates_cannot_pool_evidence(self):
        m=memory()
        for episode in m["episodes"][:6]:episode["context"].pop("operator_policy_version")
        self.assertFalse(lm.build_view(m,SUMMARIES,NOW-12*lm.DAY)["lessons"])


if __name__=="__main__":unittest.main()
