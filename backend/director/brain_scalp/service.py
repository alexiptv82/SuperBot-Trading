"""Explicit opt-in host loop for the NEW isolated Brain Scalp PAPER wallet.

Never auto-initializes, joins old accounts, alters classical bots or deploys.
Prices, fees, budget and account mandate must be supplied explicitly by the
operator. No defaults from synthetic test fixtures are promoted to production.
"""
from dataclasses import dataclass,fields
import argparse
import json
import os
from pathlib import Path
import time

from .config import WalletSpec,validate_spec
from .coordinator import BrainAccount
from .market_bridge import PublicBrainFeed
from director.trend_advisory import observe_many
from .operator import BrainOperator
from .telegram_commands import PaperTelegramCommands
from .supervisor import PaperSupervisor
from .transports import PriceLimit,make_primary,make_reviewer


MANDATE_FIELDS={f.name for f in fields(WalletSpec)}
REQUIRED_ENV=('BRAIN_SINGLE_MANDATE_JSON','BRAIN_SINGLE_DATA_DIR',
              'BRAIN_SINGLE_SNAPSHOT_PATH','BRAIN_AI_BUDGET_USD',
              'BRAIN_DEEPSEEK_INPUT_USD_M','BRAIN_DEEPSEEK_OUTPUT_USD_M',
              'BRAIN_AI_MAX_INPUT_BYTES','BRAIN_AI_MAX_OUTPUT_TOKENS',
              'DEEPSEEK_API_KEY')


def mandate_from_json(source):
    """Every parameter is mandatory: no unused dataclass default is accepted."""
    try:
        obj=json.loads(source)
    except (TypeError,ValueError):
        raise ValueError('invalid_brain_mandate_json') from None
    if not isinstance(obj,dict) or set(obj)!=MANDATE_FIELDS:
        raise ValueError('complete_explicit_brain_mandate_required')
    try:
        spec=WalletSpec(**obj)
    except TypeError:
        raise ValueError('invalid_brain_mandate') from None
    validate_spec(spec)
    if spec.name!='brain' or spec.account_id!='brain-scalp-single-paper':
        raise ValueError('single_brain_identity_required')
    return spec


def required_env(env):
    if env.get('DESK_MODE','paper')!='paper' or env.get('BRAIN_SINGLE_ENABLED')!='paper':
        raise ValueError('single_brain_paper_mode_required')
    missing=[k for k in REQUIRED_ENV if not env.get(k)]
    if missing:
        # Only variable names, never any supplied values.
        raise ValueError('brain_env_missing:'+','.join(missing))
    spec=mandate_from_json(env['BRAIN_SINGLE_MANDATE_JSON'])
    data_dir=Path(env['BRAIN_SINGLE_DATA_DIR']).absolute()
    snapshot=Path(env['BRAIN_SINGLE_SNAPSHOT_PATH']).absolute()
    if not (data_dir.is_absolute() and snapshot.is_absolute() and
            snapshot.parent.is_dir() and not snapshot.is_symlink()):
        raise ValueError('invalid_brain_paths')
    if data_dir.is_symlink() or snapshot.parent.is_symlink():
        raise ValueError('unsafe_brain_path')
    def strictly_int(key,low,high):
        try:
            s=env[key]
            if str(int(s))!=s or not low<=int(s)<=high:raise ValueError()
            return int(s)
        except (ValueError,KeyError,TypeError):
            raise ValueError('invalid_env_'+key) from None
    max_bytes=strictly_int('BRAIN_AI_MAX_INPUT_BYTES',1000,130000)
    max_tokens=strictly_int('BRAIN_AI_MAX_OUTPUT_TOKENS',256,16384)
    primary_timeout=strictly_int('BRAIN_AI_TIMEOUT_S',1,12) if 'BRAIN_AI_TIMEOUT_S' in env else 10
    reviewer_key=env.get('ANTHROPIC_API_KEY') or None
    reviewer_model=env.get('BRAIN_CLAUDE_MODEL')
    if bool(reviewer_key)!=bool(reviewer_model):
        raise ValueError('reviewer_key_model_must_be_paired')
    prices=PriceLimit(
        deepseek_input_m=env['BRAIN_DEEPSEEK_INPUT_USD_M'],
        deepseek_output_m=env['BRAIN_DEEPSEEK_OUTPUT_USD_M'],
        claude_input_m=env.get('BRAIN_CLAUDE_INPUT_USD_M',''),
        claude_output_m=env.get('BRAIN_CLAUDE_OUTPUT_USD_M',''),
        daily_usd=env['BRAIN_AI_BUDGET_USD'],
        max_input_bytes=max_bytes,max_output_tokens=max_tokens,
        reviewer_enabled=bool(reviewer_key))
    daily,per_analysis=prices.reservation()
    return {'spec':spec,'data_dir':data_dir,'snapshot_path':snapshot,
            'daily_budget_micro_usd':daily,'reservation_micro_usd':per_analysis,
            'primary':make_primary(env['DEEPSEEK_API_KEY'],max_input_bytes=max_bytes,
                max_tokens=max_tokens,timeout_s=primary_timeout),
            'reviewer':make_reviewer(reviewer_key,reviewer_model,
                max_input_bytes=max_bytes,max_tokens=max_tokens,
                timeout_s=primary_timeout) if reviewer_key else None}


class BrainService:
    """The owner thread alone touches the wallet SQLite database."""
    def __init__(self,config,*,feed=None,clock_ms=None,initialize=False):
        self.feed=feed if feed is not None else PublicBrainFeed()
        self.clock=clock_ms if clock_ms is not None else lambda:int(time.time()*1000)
        self.account=None;self.supervisor=None;self.operator=None;self.telegram=None
        self.last_markets={}
        try:
            self.account=BrainAccount(config['data_dir'],spec=config['spec'],
                initialize=initialize,now_ms=self.clock(),
                candle_backfill=self.feed.backfill)
            self.operator=BrainOperator(self.account)
            self.operator.sync()
            self.supervisor=PaperSupervisor(
                self.account,primary_call=config['primary'],
                reviewer_call=config['reviewer'],clock_ms=self.clock,
                daily_budget_micro_usd=config['daily_budget_micro_usd'],
                reservation_micro_usd=config['reservation_micro_usd'],
                analysis_interval_ms=300000,deadline_ms=30000,
                snapshot_path=config['snapshot_path'])
        except BaseException:
            self.close()
            raise

    def tick(self):
        now=self.clock()
        state=self.account.brain.store.load()
        markets,contracts=self.feed.poll(state['positions'],now)
        self.last_markets=markets
        try:
            observations=observe_many({
                sym:(m.get('bars') or {}).get('5m',())
                for sym,m in markets.items() if isinstance(m,dict)
            },now,300000)
        except Exception:
            observations={}
        # The sensor cannot block protection, change orders or veto DeepSeek.
        return self.supervisor.step(markets,contracts,observations=observations)

    def enable_telegram_commands(self,*,allowed_chat_id,allowed_user_id):
        if self.telegram is not None:
            raise ValueError('telegram_handler_already_enabled')
        self.telegram=PaperTelegramCommands(self.operator,
            allowed_chat_id=allowed_chat_id,allowed_user_id=allowed_user_id)

    def handle_telegram_update(self,update):
        if self.telegram is None:
            raise ValueError('telegram_control_not_enabled')
        # Called ONLY on the wallet-owner thread, after protective ticks.
        return self.telegram.handle(update,self.last_markets,self.clock())

    def backup(self,path):
        return self.account.brain.store.backup(path)

    def close(self):
        if self.supervisor is not None:
            self.supervisor.close()
        if self.account is not None:
            self.account.close()
        if self.feed is not None:
            self.feed.close()


def main(argv=None,env=None):
    parser=argparse.ArgumentParser(description='Isolated single-account PAPER Brain; no implicit startup')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--validate',action='store_true')
    mode.add_argument('--initialize-new',action='store_true')
    mode.add_argument('--serve',action='store_true')
    args=parser.parse_args(argv)
    env=os.environ if env is None else env
    config=required_env(env)
    if args.validate:
        return {'status':'valid_offline_configuration','paper':True}
    if args.initialize_new:
        if env.get('BRAIN_INIT_ACK')!='CREATE_NEW_EMPTY_PAPER_ACCOUNT':
            raise ValueError('new_account_initialization_not_approved')
        # No existing directory contents may be replaced by the engine.
        account=BrainAccount(config['data_dir'],spec=config['spec'],
                             initialize=True,now_ms=int(time.time()*1000))
        account.close()
        return {'status':'new_paper_wallet_initialized'}
    # Serving is deliberately opt-in and requires a backup before any call.
    backup_path=env.get('BRAIN_SINGLE_BACKUP_PATH')
    if not backup_path or env.get('BRAIN_SERVE_ACK')!='PAPER_ONLY_EXPLICIT_START':
        raise ValueError('backup_and_explicit_paper_start_required')
    service=BrainService(config)
    try:
        service.backup(Path(backup_path))
        while True:
            start=time.monotonic()
            try:service.tick()
            except Exception:
                # No AI fallback; the next tick attempts protection again.
                # Only exception types, never market/keys/payloads, in logs.
                import logging
                logging.getLogger(__name__).exception('brain_paper_tick_failed')
            time.sleep(max(0,5-(time.monotonic()-start)))
    finally:
        service.close()


if __name__=='__main__':
    main()
