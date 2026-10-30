"""Execute only the real diagnostic function, without importing trading CLI."""
import ast
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class ClassicsStructure(unittest.TestCase):
    def function(self):
        # In CI use repository CLI; in the split local checkout use classic/.
        path=Path(__file__).parents[1]/'desk'/'cli.py'
        if not path.exists():
            path=Path(__file__).parents[3]/'classic'/'backend'/'desk'/'cli.py'
        tree=ast.parse(path.read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                  and n.name=='_poll_structure_advisory')
        scope={'os':os,'time':SimpleNamespace(time=lambda:1800000000),
               'SYMBOLS':['BTC'],'fetch_candles':Mock(side_effect=AssertionError('owner fetch'))}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
        return scope['_poll_structure_advisory'],scope

    def test_default_off_is_noop(self):
        fn,scope=self.function();state={'main':{'positions':{'BTC':'unchanged'}}}
        with patch.dict(os.environ,{},clear=True):
            fn(state,{})
        self.assertEqual(set(state),{'main'})
        scope['fetch_candles'].assert_not_called()

    def test_opposite_advice_changes_only_diagnostic_state(self):
        fn,scope=self.function();state={'main':{'positions':{'BTC':'SHORT'}},'score':88}
        worker=Mock();worker.poll.return_value={'BTC':{'phase':'UP_REASSESSMENT'}}
        ctl={'_structure_advisory':worker}
        with patch.dict(os.environ,{'DESK_STRUCTURE_ADVISORY':'on'}),redirect_stdout(io.StringIO()) as out:
            fn(state,ctl);fn(state,ctl)
        self.assertEqual(state['main'],{'positions':{'BTC':'SHORT'}})
        self.assertEqual(state['score'],88)
        self.assertEqual(out.getvalue().count('[STRUTTURA AVVISO]'),1)
        scope['fetch_candles'].assert_not_called()

    def test_failed_observer_does_not_raise_or_retain_advice(self):
        fn,_=self.function();worker=Mock();worker.poll.side_effect=ValueError('network')
        state={'main':{'positions':{}},'structure_advisory':{'BTC':'old'}}
        with patch.dict(os.environ,{'DESK_STRUCTURE_ADVISORY':'on'}):
            fn(state,{'_structure_advisory':worker})
        self.assertEqual(state,{'main':{'positions':{}},'structure_advisory':{}})


if __name__=='__main__':unittest.main()
