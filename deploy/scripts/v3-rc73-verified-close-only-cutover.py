#!/usr/bin/env python3
"""RC73: guarded same-domain PAPER read-only dashboard cutover with rollback.

This replaces ONLY the authenticated web application, never the historic bot
containers or exit-only workers. The original app SQLite DB stays mounted in
place; no credentials/session material is copied into staging or logs.
Original Docker container and old frontend are kept for immediate rollback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

STAGE = Path('/opt/superbot-v3-rc73-release')
SNAP = Path('/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218')
BRAIN = Path('/opt/superbot-v3-paper-runs/brain-v3-rc20261106')
DB = Path('/opt/superbot/data/superbot.db')
WEB = Path('/opt/superbot-web')
NAME = 'superbot'
OLD = 'superbot-rc73-previous'
STATE = STAGE / 'rc73-stage-manifest.json'
FORBIDDEN = ('docker.sock', '\n', '\r')
REQUIRED = ('state_v2.json','trade_history.jsonl','learning_log.jsonl','lessons.md')
LIMITS = {'hawk':6, 'bull':2}


class Refuse(RuntimeError):
    pass


def docker(*args, timeout=35):
    try:
        p=subprocess.run(('docker',)+tuple(args),capture_output=True,text=True,
                         timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise Refuse('docker_unavailable') from None
    if p.returncode:
        raise Refuse('docker_command_failed_'+args[0])
    return p.stdout.strip()


def inspect(name):
    try:
        result=json.loads(docker('inspect',name,timeout=10))
        return result[0]
    except (ValueError,IndexError):
        raise Refuse('container_inspect_invalid') from None


def http(path, timeout=4):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8002'+path,timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def verify_historical():
    for p,expected in LIMITS.items():
        d=inspect('superbot-desk-'+p)
        env={n:v for n,v in (item.split('=',1) for item in d['Config']['Env'] if '=' in item)}
        if (d['State']['Running'] is not False
                or d['HostConfig']['RestartPolicy']['Name']!='no'
                or env.get('DESK_MODE')!='paper'):
            raise Refuse('historic_worker_not_stopped_disabled_paper')
        source=Path('/opt/superbot-desk-data')/p
        if not (source/'pause.flag').is_file():
            raise Refuse('historic_pause_missing')
        for n in ('reset.flag','reset.flag.work','close_position.flag','close_position.flag.work'):
            if (source/n).exists():
                raise Refuse('historic_close_pending_reconciliation')
        for f in REQUIRED:
            a,b=source/f,SNAP/p/f
            if (not a.is_file() or not b.is_file() or a.is_symlink() or b.is_symlink()
                    or sha(a)!=sha(b)):
                raise Refuse('historic_snapshot_missing_or_stale')
        try:
            positions=json.loads((source/'state_v2.json').read_text())['main']['positions']
            if type(positions) is not dict or len(positions)!=expected:
                raise Refuse('historic_position_count_changed')
        except (OSError,KeyError,ValueError,TypeError):
            raise Refuse('historic_state_invalid') from None


def verify_brain():
    for f in ('pause.flag','runner_config.json','PREPARED_PAUSED_ONLY.json','mandate.json','journal.db'):
        if not (BRAIN/f).is_file():
            raise Refuse('brain_paused_run_not_prepared')
    try:
        config=json.loads((BRAIN/'runner_config.json').read_text())
        prepared=json.loads((BRAIN/'PREPARED_PAUSED_ONLY.json').read_text())
        mandate=json.loads((BRAIN/'mandate.json').read_text())
    except (OSError,ValueError):
        raise Refuse('brain_config_invalid') from None
    if (str(config.get('initial_equity')) not in ('2000','2000.0')
            or prepared.get('run_id')!='brain-rc-2000-20261106'
            or prepared.get('paper_only') is not True
            or prepared.get('mandate_approved') is not False
            or mandate.get('approved') is not False):
        raise Refuse('brain_not_2000_paper_paused_unapproved')


def verify_exit_only_ready():
    """Precondition for permission switch: both independent PAPER workers, no pending commands."""
    for portfolio,name in (('hawk','falco'),('bull','toro')):
        service='superbot-v3-'+name+'-exit.service'
        active=subprocess.run(['systemctl','is-active','--quiet',service],
                              check=False,timeout=7)
        enabled=subprocess.run(['systemctl','is-enabled',service],
                               capture_output=True,text=True,check=False,timeout=7)
        if active.returncode!=0 or enabled.stdout.strip()!='disabled':
            raise Refuse('exit_only_service_not_ready_'+name)
        base=Path('/opt/superbot-desk-data')/portfolio
        try:
            h=json.loads((base/'exit_only_heartbeat.json').read_text())
        except (OSError,ValueError):
            raise Refuse('exit_only_heartbeat_unavailable_'+name) from None
        if (h.get('mode')!='paper-exit-only' or h.get('portfolio')!=portfolio
                or h.get('ready') is not True or
                type(h.get('ts')) not in (int,float) or
                not 0 <= time.time()-h['ts'] < 12):
            raise Refuse('exit_only_heartbeat_invalid_'+name)
        for req in ('reset.flag','reset.flag.work','close_position.flag',
                    'close_position.flag.work','reset_portfolio.flag'):
            if (base/req).exists():
                raise Refuse('existing_pending_request_'+name)


def stage_preflight():
    if STAGE.is_symlink() or not STAGE.is_dir():
        raise Refuse('stage_missing')
    if (STAGE/'Dockerfile').is_symlink() or not (STAGE/'Dockerfile').is_file():
        raise Refuse('stage_dockerfile_missing')
    for f in ('frontend/build/index.html','backend/server.py','backend/v3/cutover_gate.py','rc73-commit.txt'):
        if not (STAGE/f).is_file():
            raise Refuse('stage_code_missing')
    if ('V3_CUTOVER_READONLY' not in (STAGE/'backend/server.py').read_text()
            or 'classic_single_close_enabled' not in (STAGE/'backend/server.py').read_text()):
        raise Refuse('selective_paper_single_close_gate_not_in_release')
    if not (SNAP/'MANIFEST.json').is_file():
        raise Refuse('verified_snapshot_missing')
    if (WEB/'build.rc73-previous').exists() or (WEB/'build.rc73-new').exists():
        raise Refuse('frontend_rollback_paths_occupied')
    if not (WEB/'build/index.html').is_file():
        raise Refuse('current_frontend_missing')
    if (STAGE/'rc73-deploy-completed.json').exists():
        raise Refuse('cutover_already_completed')
    try:
        inspect(OLD)
    except Refuse:
        pass
    else:
        raise Refuse('previous_container_occupied')
    if not DB.is_file() or DB.is_symlink():
        raise Refuse('existing_auth_database_not_found')
    if http('/api/health')!=200:
        raise Refuse('existing_web_health_failed')
    if '/opt/superbot-web/build' not in Path('/etc/nginx/sites-available/superbot').read_text():
        raise Refuse('production_nginx_unexpected_root')
    verify_historical()
    verify_brain()
    verify_exit_only_ready()
    if shutil.disk_usage('/opt').free < 2_000_000_000:
        raise Refuse('not_enough_disk_for_candidate_and_backup')


def backup_auth_db():
    root=Path('/opt/superbot-backups')
    folder=root/('rc73-app-db-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+str(os.getpid()))
    folder.mkdir(mode=0o700)
    dest=folder/'superbot.db'
    try:
        source=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=15)
        copy=sqlite3.connect(str(dest))
        source.backup(copy)
        if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise Refuse('db_backup_integrity_failed')
        table_names={row[0] for row in copy.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        if not {'auth_settings','trades'}.issubset(table_names):
            raise Refuse('db_backup_schema_unexpected')
        # Hashing only, never revealing contents/keys or any account records.
        copy.close()
        source.close()
        os.chmod(dest,0o600)
        test=sqlite3.connect('file:'+str(dest)+'?mode=ro',uri=True)
        if test.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise Refuse('isolated_restore_integrity_failed')
        test.close()
        print('RC73_EXISTING_AUTH_DB_SNAPSHOT_RESTORE=PASS',flush=True)
        return folder
    except Exception:
        print('RC73_AUTH_DB_SNAPSHOT_FAILED',flush=True)
        raise


def create_env_file(existing):
    root=Path('/run') if Path('/run').is_dir() else STAGE
    fd,p=tempfile.mkstemp(prefix='.rc73-production-env-',dir=root)
    os.chmod(p,0o600)
    replaced={
        'TRADING_MODE':'paper', 'DESK_MODE':'paper',
        'TELEGRAM_COMMANDS_ENABLED':'false',
        'DB_PATH':'/app/data/superbot.db',
        'V3_CUTOVER_READONLY':'1',
        'V3_ALLOW_CLASSIC_SINGLE_CLOSE':'1',
        'V3_BRAIN_PEER_OBSERVATIONS':'disabled',
        'V3_RUN_ID':'brain-rc-2000-20261106',
        'V3_JOURNAL_PATH':str(BRAIN/'journal.db'),
        'V3_BUDGET_DB_PATH':str(BRAIN/'budget.db'),
        'V3_HEARTBEAT_PATH':str(BRAIN/'heartbeat.json'),
        'V3_PAUSE_FLAG_PATH':str(BRAIN/'pause.flag'),
        'V3_RUNNER_CONFIG_PATH':str(BRAIN/'runner_config.json'),
        'V3_CLOSE_REQUEST_PATH':str(BRAIN/'manual_close_request.json'),
        'V3_CLOSE_RESULT_PATH':str(BRAIN/'manual_close_result.json'),
        'DESK_DATA_DIR':'/opt/superbot-desk-data/hawk',
        'DESK_DATA_DIR_BULL':'/opt/superbot-desk-data/bull',
    }
    env=dict(replaced)
    for item in existing.get('Config',{}).get('Env',[]):
        if '=' not in item:
            raise Refuse('unexpected_old_env_format')
        k,v=item.split('=',1)
        if not k.replace('_','').isalnum() or any(z in v for z in ('\n','\r','\0')):
            raise Refuse('unsafe_old_env_entry')
        if k not in replaced:
            env[k]=v
    try:
        with os.fdopen(fd,'w',encoding='utf8') as out:
            for k,v in sorted(env.items()):
                out.write(k+'='+v+'\n')
            out.flush()
            os.fsync(out.fileno())
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(p).unlink(missing_ok=True)
        raise
    return Path(p)


def mount_flags(existing):
    result=[]
    destinations=set()
    for m in existing.get('Mounts',[]):
        typ=m.get('Type')
        if typ not in ('bind','volume'):
            raise Refuse('unexpected_original_mount_type')
        source=m.get('Source') if typ=='bind' else m.get('Name')
        dest=m.get('Destination')
        if not source or not dest or not dest.startswith('/') or ':' in str(source)+dest:
            raise Refuse('bad_original_mount')
        if dest in destinations or 'docker.sock' in dest:
            raise Refuse('duplicate_or_docker_socket_mount')
        destinations.add(dest)
        option='rw' if m.get('RW') else 'ro'
        result+=['-v',str(source)+':'+dest+':'+option]
    for dest in ('/app/data','/app/backend/.env','/opt/superbot-desk-data/hawk',
                 '/opt/superbot-desk-data/bull'):
        if dest not in destinations:
            raise Refuse('required_original_mount_missing')
    if str(BRAIN) in destinations:
        # RC71 already mounted the prepared Brain run read-only.
        brain_mount = next((m for m in existing.get('Mounts',[])
                            if m.get('Destination') == str(BRAIN)),None)
        if not brain_mount or brain_mount.get('Source') != str(BRAIN) or brain_mount.get('RW'):
            raise Refuse('brain_existing_mount_not_verified_readonly')
    else:
        result+=['-v',str(BRAIN)+':'+str(BRAIN)+':ro']
    return result


def assert_web_app_safe():
    if http('/api/health')!=200:
        raise Refuse('new_app_health_failed')
    if http('/api/v3/overview')!=401:
        raise Refuse('new_v3_api_not_authenticated')
    if http('/api/auth/password-status')!=401:
        raise Refuse('new_login_check_not_authenticated')
    try:
        req=urllib.request.Request('http://127.0.0.1:8002/api/desk/close-all',
                                   method='POST')
        urllib.request.urlopen(req,timeout=4)
        response=0
    except urllib.error.HTTPError as e:
        response=e.code
    except Exception:
        response=0
    if response!=423:
        raise Refuse('readonly_close_block_not_effective')
    for endpoint,expected in (
            ('/api/desk/close-position',401),
            ('/api/desk/bull/close-position',401),
            ('/api/desk/close-all',423),
            ('/api/desk/bull/close-all',423),
            ('/api/desk/resume',423),
            ('/api/desk/bull/resume',423),
            ('/api/v3/brain/close',423),
        ):
        try:
            req=urllib.request.Request('http://127.0.0.1:8002'+endpoint,
                                       method='POST')
            with urllib.request.urlopen(req,timeout=4) as r:
                code=r.status
        except urllib.error.HTTPError as e:
            code=e.code
        except Exception:
            code=0
        if code!=expected:
            raise Refuse('permission_gate_unexpected_'+endpoint.replace('/','_'))
    if http('/api/health')!=200:
        raise Refuse('new_app_health_lost')


def rollback(*, old_renamed, old_stopped, new_exists, web_switched):
    print('RC73_ROLLBACK_STARTED=True',flush=True)
    try:
        if web_switched and (WEB/'build.rc73-previous').exists():
            if (WEB/'build').exists():
                moved=WEB/'build.rc73-failed'
                if moved.exists():
                    raise Refuse('rollback_failed_frontend_path_exists')
                (WEB/'build').replace(moved)
            (WEB/'build.rc73-previous').replace(WEB/'build')
        if new_exists:
            subprocess.run(['docker','rm','-f',NAME],capture_output=True,timeout=30)
        if old_renamed:
            subprocess.run(['docker','update','--restart','always',OLD],
                           capture_output=True,timeout=10)
            docker('rename',OLD,NAME)
            if not inspect(NAME).get('State',{}).get('Running'):
                docker('start',NAME,timeout=30)
        time.sleep(2)
        print('RC73_ROLLBACK_OLD_WEB_HEALTHY='+str(http('/api/health')==200),flush=True)
    except Exception:
        print('RC73_ROLLBACK_REQUIRES_OPERATOR=True',flush=True)
        raise


def main():
    if os.geteuid()!=0:
        raise Refuse('root_required')
    ap=argparse.ArgumentParser()
    exclusive=ap.add_mutually_exclusive_group(required=True)
    exclusive.add_argument('--paper-readonly-cutover',action='store_true')
    exclusive.add_argument('--preflight-only',action='store_true')
    ap.add_argument('--expected-commit',required=True)
    args=ap.parse_args()
    if len(args.expected_commit)!=40 or any(c not in '0123456789abcdef' for c in args.expected_commit):
        raise Refuse('invalid_expected_release_commit')
    if (STAGE/'rc73-commit.txt').read_text().strip()!=args.expected_commit:
        raise Refuse('release_commit_mismatch')
    stage_preflight()
    print('RC73_PAPER_READONLY_PREFLIGHT=PASS',flush=True)
    if args.preflight_only:
        print('RC73_PREVIEW_ONLY_NO_PRODUCTION_CHANGED=True',flush=True)
        return
    # Build new image and copy static assets before stopping the old app.
    tag='superbot:rc73-'+args.expected_commit[:10]
    docker('build','--pull=false','-q','-t',tag,str(STAGE),timeout=300)
    fresh=WEB/'build.rc73-new'
    shutil.copytree(STAGE/'frontend/build',fresh,symlinks=False)
    if not (fresh/'index.html').is_file():
        raise Refuse('staged_frontend_incomplete')
    print('RC73_NEW_APP_IMAGE_AND_FRONTEND_READY=True',flush=True)
    backup_folder=backup_auth_db()
    old=inspect(NAME)
    if (old.get('State',{}).get('Running') is not True
            or old.get('HostConfig',{}).get('RestartPolicy',{}).get('Name')!='always'):
        raise Refuse('existing_web_container_changed')
    binds=old.get('HostConfig',{}).get('PortBindings',{}).get('8001/tcp') or []
    if len(binds)!=1 or binds[0].get('HostIp')!='127.0.0.1' or binds[0].get('HostPort')!='8002':
        raise Refuse('existing_web_bind_unexpected')
    mounts=mount_flags(old)
    env_path=create_env_file(old)
    old_renamed=False
    old_stopped=False
    new_exists=False
    web_switched=False
    try:
        verify_historical()
        verify_exit_only_ready()
        docker('rename',NAME,OLD,timeout=20)
        old_renamed=True
        docker('stop','-t','12',OLD,timeout=25)
        old_stopped=True
        args_docker=['create','--name',NAME,'--restart','no',
             '--security-opt','no-new-privileges:true',
             '-p','127.0.0.1:8002:8001',
             '--env-file',str(env_path)]
        args_docker.extend(mounts)
        args_docker.append(tag)
        docker(*args_docker,timeout=35)
        new_exists=True
        docker('start',NAME,timeout=35)
        ok=False
        for _ in range(15):
            time.sleep(2)
            try:
                assert_web_app_safe()
                ok=True
                break
            except Refuse:
                pass
        if not ok:
            raise Refuse('new_web_app_safe_checks_failed')
        print('RC73_AUTHENTICATED_READONLY_BACKEND=PASS',flush=True)
        (WEB/'build').replace(WEB/'build.rc73-previous')
        fresh.replace(WEB/'build')
        web_switched=True
        if http('/api/health')!=200:
            raise Refuse('web_health_lost_after_static_swap')
        if sha(WEB/'build/index.html')!=sha(STAGE/'frontend/build/index.html'):
            raise Refuse('deployed_frontend_does_not_match_candidate')
        # Confirm all eight original PAPER positions and both stopped workers.
        verify_historical()
        verify_exit_only_ready()
        inspect_new=inspect(NAME)
        new_env=dict(x.split('=',1) for x in inspect_new['Config']['Env'] if '=' in x)
        if (new_env.get('V3_CUTOVER_READONLY')!='1'
                or new_env.get('TRADING_MODE')!='paper'
                or new_env.get('DESK_MODE')!='paper'
                or new_env.get('V3_ALLOW_CLASSIC_SINGLE_CLOSE')!='1'
                or new_env.get('TELEGRAM_COMMANDS_ENABLED')!='false'
                or new_env.get('V3_BRAIN_PEER_OBSERVATIONS')!='disabled'):
            raise Refuse('new_web_unsafe_environment')
        docker('update','--restart','always',NAME)
        docker('update','--restart','no',OLD)
        results={
            'schema':'v3-rc73-paper-readonly-cutover',
            'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'release_commit':args.expected_commit,
            'auth_db_backup_present':backup_folder.is_dir(),
            'original_container_saved':True,
            'original_web_build_saved':True,
            'classic_workers_stopped':True,
            'exit_only_units_started':True,
            'manual_closes_executed':False,
            'classic_single_close_allowed':True,
            'new_app_readonly_gate':True,
        }
        (STAGE/'rc73-deploy-completed.json').write_text(
            json.dumps(results,sort_keys=True,indent=2)+'\n')
        print('RC73_NEW_WEB_LOGIN_DATABASE_PRESERVED=True',flush=True)
        print('RC73_OLD_CONTAINER_AND_FRONTEND_AVAILABLE_FOR_ROLLBACK=True',flush=True)
        print('RC73_CLASSIC_POSITIONS_6_AND_2_PRESERVED=True',flush=True)
        print('RC73_CUTOVER_READONLY=True',flush=True)
        print('RC73_CLASSIC_SINGLE_CLOSE_ONLY_ENABLED=True',flush=True)
        print('RC73_ALL_START_RESUME_RESET_CLOSE_ALL_STILL_BLOCKED=True',flush=True)
        print('RC73_PRODUCTION_WEB_CUTOVER_SUCCESS=True',flush=True)
    except BaseException:
        rollback(old_renamed=old_renamed,old_stopped=old_stopped,
                 new_exists=new_exists,web_switched=web_switched)
        raise
    finally:
        try:
            env_path.unlink()
        except OSError:
            print('RC73_TEMP_ENV_CLEANUP_FAILED=True',flush=True)


if __name__=='__main__':
    try:
        main()
    except Refuse as err:
        # Only fixed reason codes, never token/DB/auth content.
        print('RC73_REFUSED='+str(err),file=sys.stderr,flush=True)
        sys.exit(2)
