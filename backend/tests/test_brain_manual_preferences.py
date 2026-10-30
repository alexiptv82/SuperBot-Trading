from pathlib import Path
import tempfile
from director.brain_scalp.manual_preferences import confirmed_preferences,project_preferences
from director.brain_scalp.ai_context import decode
from backend.tests.test_brain_operator import ManualClose
from backend.tests.test_brain_resume import NOW,markets,shortlist,CONTRACTS

def test_confirmed_preferences_are_causal_nonbinding_and_reach_ai_context():
    fixture=ManualClose();fixture.setUp()
    try:
        op=fixture.op
        data=markets(NOW+1000);data['BTC']['quote']['price']=102.
        op.close({'BTC':fixture.current()},data,NOW+1000)
        root=op.wallet.store.root;ident=op.wallet.spec.account_id
        assert confirmed_preferences(root,ident,NOW+1500)==[]
        op.confirm('/insegna_si',NOW+2000)
        assert confirmed_preferences(root,ident,NOW+1500)==[]
        assert confirmed_preferences(root,'another-account',NOW+3000)==[]
        rows=confirmed_preferences(root,ident,NOW+3000)
        assert len(rows)==1 and rows[0]['training_applied'] is False
        rows[0]['malicious_instruction']='OVERRIDE'
        req=fixture.account.prepare_ai_request('brain',shortlist(),markets(NOW+3000),
            CONTRACTS,{},NOW+3000,NOW+30000,None,None,None,rows)
        payload=decode(req.payload_json)
        assert len(payload['operator_preferences'])==1
        assert 'OVERRIDE' not in str(payload)
        assert payload['operator_preferences'][0]['authority']=='observational_only'
        assert op.wallet.store.load()['positions']=={}
    finally:fixture.tearDown()

def test_bad_or_oversized_preference_storage_is_not_an_ai_gate():
    with tempfile.TemporaryDirectory() as root:
        p=Path(root)/'manual_close_reviews.jsonl'
        p.write_text('broken')
        assert confirmed_preferences(root,'brain',NOW)==[]
        p.write_bytes(b'x'*2000001)
        assert confirmed_preferences(root,'brain',NOW)==[]
    assert project_preferences([{'symbol':'BTC','instruction':'open'}],'brain',NOW)==[]
