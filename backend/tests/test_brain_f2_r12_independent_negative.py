"""Independent adversarial regression tests for Grok Brain F2 R1.2.
Expected to PASS against the patched engine. Synthetic data only.
"""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import MarketContext, DecisionKind, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.risk import RiskPolicy
from backend.v3.events import EventJournal

# Hardening 04/11/2026: senza run_id e senza mandato con scope coerente il motore
# risponde NO_TRADE('invalid_input'/'policy_not_authorized') PRIMA di arrivare al
# controllo che ogni test dichiara di verificare (misurato: 8 test di questo file
# passavano per il motivo sbagliato). Ora l'helper costruisce un motore VALIDO,
# test_control_valid_engine_approves lo dimostra, e ogni test negativo asserisce
# il rationale esatto che prova che il controllo giusto ha scattato.
RUN = 'r12-run'


def context(): return MarketContext('BTCUSDT',Decimal('50000'),1700000000000,'TRENDING')
def policy(floor='450'):
    return RiskPolicy(Decimal('.02'),Decimal('.05'),Decimal('.1'),Decimal('.3'),Decimal(floor),Decimal('16'),Decimal('.5'))
def snapshot(): return BrainPortfolioSnapshot(Decimal('1000'),Decimal('1000'),Decimal('0'),Decimal('0'))
def params():
    return {'exchange_leverage_limit':10,'quantity_step':Decimal('.001'),
            'minimum_notional':Decimal('5'),'maintenance_fraction':Decimal('.004'),
            'market_data_fresh':True, 'paused': False, 'daily_loss_latched': False}
def engine(**kw):
    args={'analyst':MockDeepSeekAnalyst(), 'reviewer':MockClaudeReviewer(always_approve=True),
          'risk_policy':policy(),'portfolio_snapshot':snapshot(),'market_params':params(),
          'run_id':RUN}
    args.update(kw)
    args.setdefault('policy_verifier', lambda m,p: True)
    args.setdefault('policy_mandate', {'version':'r15-test','approved_by':'operator','approved':True,
                                       'portfolio_id':'brain','run_id':args['run_id'],
                                       'policy_hash':_policy_hash(args['risk_policy'])})
    return BrainEngine(**args)

def test_control_valid_engine_approves():
    """Controllo anti-test-vuoti: con input validi il motore DEVE approvare.
    Se questo fallisce, i NO_TRADE degli altri test non provano nulla."""
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(journal=journal).step(context())
    assert (decision.kind, decision.status, decision.rationale) == \
        (DecisionKind.OPEN, ProposalStatus.APPROVED, 'risk_quote_ok')

def test_must_not_approve_without_persistent_journal():
    # journal=None now raises ValueError at construction (fail-closed at constructor)
    with pytest.raises(ValueError, match='journal is required'):
        engine(journal=None)

def test_paused_state_must_be_explicit():
    # market_params lacks paused and daily_loss_latched
    mp = params()
    del mp['paused']
    del mp['daily_loss_latched']
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(market_params=mp,journal=journal).step(context())
    assert decision.kind==DecisionKind.NO_TRADE, 'Missing pause state was assumed false'
    assert decision.rationale=='invalid_input'  # rifiutato dal controllo sui parametri, non dal run_id

@pytest.mark.parametrize('floor', ['NaN','Infinity'])
def test_malformed_floor_fails_closed_without_crashing(floor):
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(risk_policy=policy(floor),journal=journal).step(context())
    assert decision.kind==DecisionKind.NO_TRADE
    assert decision.rationale=='invalid_input'  # floor malformato intercettato dal gate sulla policy

class SensitiveError(Analyst):
    def analyze(self, context, open_positions):
        raise RuntimeError('SensitiveHeader=example-private-credential-value')

def test_provider_exception_text_is_not_reflected():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(analyst=SensitiveError(),journal=journal).step(context())
        stored=[dict(s.event.payload) for s in journal.list_run('brain',RUN)]
    assert decision.rationale=='ai_unavailable'  # l'eccezione e' stata davvero lanciata e gestita
    assert 'example-private-credential-value' not in decision.rationale
    assert 'example-private-credential-value' not in repr(stored)  # ne' riflesso nel journal

def test_brain_engine_refuses_cross_portfolio_journal_writes():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(analyst=MockDeepSeekAnalyst(force_no_trade=True),journal=journal,portfolio_id='hawk').step(context())
        assert decision.rationale=='portfolio_boundary'
        # run realmente usato dal motore (prima si controllava un run inesistente: test vuoto)
        assert not journal.list_run('hawk',RUN), 'Brain engine wrote Hawk event'
        # il rifiuto puo' lasciare una traccia di audit nel proprio namespace 'brain',
        # ma mai una decisione operativa
        assert all(s.event.payload.get('kind')=='NO_TRADE' for s in journal.list_run('brain',RUN))

def test_missing_pause_state_rejected_even_with_real_journal():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        mp = params()
        del mp['paused']
        del mp['daily_loss_latched']
        decision=engine(journal=journal, market_params=mp).step(context())
        assert decision.kind == DecisionKind.NO_TRADE, 'Missing pause/latch flags approved despite real journal'
        assert decision.rationale == 'invalid_input'

class ReturnsNone(Analyst):
    def analyze(self, context, open_positions): return None

def test_malformed_analyst_return_fails_closed_without_crash():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(analyst=ReturnsNone(),journal=journal).step(context())
    assert decision.kind == DecisionKind.NO_TRADE
    assert decision.rationale == 'malformed_output'

class InvalidReviewer(MockClaudeReviewer):
    def review(self, decision, complexity_reason): return None

def test_malformed_reviewer_return_fails_closed_without_crash():
    with TemporaryDirectory() as td:
        journal=EventJournal(Path(td)/'j.sqlite');journal.init_schema()
        decision=engine(reviewer=InvalidReviewer(),journal=journal).step(context(),complexity_threshold=.9)
    assert decision.kind == DecisionKind.NO_TRADE
    # soglia .9 > confidence del mock: la revisione scatta davvero e restituisce None
    assert decision.rationale == 'malformed_output'
