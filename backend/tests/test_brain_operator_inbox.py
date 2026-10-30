import tempfile
from pathlib import Path
from unittest.mock import Mock
import pytest
from director.brain_scalp.operator_inbox import OperatorInbox

def test_confirmations_execute_once_and_never_modify_wallet_from_submit():
    with tempfile.TemporaryDirectory() as root:
        queue=OperatorInbox(Path(root)/'inbox.sqlite')
        try:
            op=Mock()
            queue.submit_confirmation('a'*32,'b'*16,'yes',1000)
            op.confirm.assert_not_called()
            queue.submit_confirmation('a'*32,'b'*16,'yes',1001)
            assert queue.consume(op,2000)[0]['status']=='confirmed'
            op.confirm.assert_called_once_with('/insegna_si '+'b'*16,2000)
            assert queue.consume(op,3000)==[]
            with pytest.raises(ValueError):
                queue.submit_confirmation('a'*32,'b'*16,'no',3000)
        finally:queue.close()

def test_stale_or_uncertain_confirmations_are_not_retried():
    with tempfile.TemporaryDirectory() as root:
        queue=OperatorInbox(Path(root)/'inbox.sqlite')
        try:
            op=Mock()
            queue.submit_confirmation('a'*32,'b'*16,'yes',1000)
            assert queue.consume(op,200000)[0]['status']=='expired'
            op.confirm.assert_not_called()
            queue.submit_confirmation('c'*32,'d'*16,'no',200000)
            op.confirm.side_effect=OSError('after write')
            assert queue.consume(op,200001)[0]['status']=='needs_reconciliation'
            assert queue.consume(op,200002)==[]
            assert op.confirm.call_count==1
        finally:queue.close()
