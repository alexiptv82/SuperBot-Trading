import copy,importlib.util,json,sqlite3,tempfile,unittest,time,re
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('u',Path(__file__).with_name('brain_paired_update.py'));u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
class Checks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def account(self,p):return {'version':'classical-adaptive-v1','profile':p,'method':('a' if p=='hawk' else 'b')*64,'desk':{'main':{'name':'brain-'+p,'cash':800.,'positions':{'BTC':{'symbol':'BTC','id':3}}}},'contexts':{'3:9':{'cohort':'old'}},'operator_paused':True,'last_step_ms':int(time.time()*1000)+10000}
 def create(self,p):
  folder=self.root/('brain-'+p);folder.mkdir();(folder/'journal.jsonl').write_text('{"kind":"old"}\n');(folder/'writer.lock').touch()
  with sqlite3.connect(folder/'brain.sqlite3') as db:
   db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)');db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,body TEXT)');db.execute('INSERT INTO state VALUES(1,?)',(json.dumps(self.account(p)),));db.execute("INSERT INTO events VALUES(1,'journal','{}')")
  return folder
 def test_real_profile_archive_restore_and_source_preservation(self):
  folder=self.create('hawk');before=u.dbread(folder);u.archive(folder,self.root/'backup')
  self.assertEqual(u.dbread(folder),before);self.assertEqual(u.dbread(self.root/'backup'),before)
  self.assertEqual((self.root/'backup'/'journal.jsonl').read_bytes(),(folder/'journal.jsonl').read_bytes())
 def test_history_allows_documented_protective_close_not_silent_loss_or_new_entries(self):
  s=self.account('hawk');events=[(1,'journal','{}')];after=copy.deepcopy(s);after['desk']['main']['positions']={}
  with self.assertRaisesRegex(ValueError,'POSITION_DISAPPEARED'):u.history_preserved(s,events,after,events)
  u.history_preserved(s,events,after,events+[(2,'trade',json.dumps({'symbol':'BTC','id':3,'partial':False}))])
  after=copy.deepcopy(s);after['desk']['main']['positions']['ETH']={'symbol':'ETH','id':4}
  with self.assertRaisesRegex(ValueError,'NEW_EXPOSURE'):u.history_preserved(s,events,after,events)
 def test_metadata_migration_rejects_cash_change(self):
  s=self.account('hawk');after=copy.deepcopy(s);after['method']='c'*64;u.migrated_state(s,after,'c'*64)
  after['desk']['main']['cash']=1000
  with self.assertRaisesRegex(ValueError,'NONMETHOD'):u.migrated_state(s,after,'c'*64)
 def simulate(self,fail=False):
  for p in u.NAMES:self.create(p)
  with sqlite3.connect(self.root/'brain-api-budget.sqlite3') as db:db.execute('CREATE TABLE reservations(id TEXT,profile TEXT,cost REAL)');db.execute("INSERT INTO reservations VALUES('old','legacy',.35)")
  (self.root/'api_budget_baseline.json').write_text('{"old":0.35}')
  repo=self.root/'source';oldrepo=self.root/'old';repo.mkdir();oldrepo.mkdir()
  for p in u.NAMES:
   d=repo/'brain'/'backtest_seed'/p;d.mkdir(parents=True);(d/'backtest_seed.json').write_text(json.dumps({'profile':p,'source':'synthetic_backtest_test'}))
  backups=self.root/'backups';backups.mkdir();containers={}
  names=list(u.NAMES.values())+['superbot-desk-hawk','superbot-desk-bull','superbot-brain-pilot','superbot']
  for name in names:
   containers[name]={'Config':{'Env':['DESK_MODE=paper'],'Labels':{'superbot.sha':u.OLD if name in u.NAMES.values() else 'f'*40}},'State':{'Running':True,'StartedAt':'original','Health':{'Status':'healthy'}},'RestartCount':0,'Mounts':[{'Source':str(self.root),'Destination':'/out','RW':name!='superbot'}]}
  commands=[]
  def state_change(p,method=None):
   folder=self.root/('brain-'+p)
   with sqlite3.connect(folder/'brain.sqlite3') as db:
    s=json.loads(db.execute('SELECT body FROM state').fetchone()[0]);s['operator_paused']=(folder/'pause.flag').exists();s['last_step_ms']=int(time.time()*1000)+10000
    if method:s['method']=method
    db.execute('UPDATE state SET body=?',(json.dumps(s),))
   (folder/'status.json').write_text(json.dumps({'ts_ms':int(time.time()*1000)+10000,'fresh_fast_data':True}))
  def fake_run(args,**kwargs):
   commands.append(args)
   if args[0]=='git':return u.TARGET if args[2]==str(repo) else u.OLD
   if args[1]=='build':return 'image'
   if args[1]=='stop':containers[args[-1]]['State']['Running']=False;return ''
   if args[1]=='start':containers[args[-1]]['State']['Running']=True;return ''
   if args[1]=='rename':containers[args[-1]]=containers.pop(args[-2]);return ''
   if args[1]=='run' and '-c' in args:
    code=args[-1];p,old=re.search("m.migrate\\('([^']+)','([^']+)'",code).groups();rollback=u.OLD in code;new=(('a' if p=='hawk' else 'b') if rollback else ('c' if p=='hawk' else 'd'))*64
    if fail and p=='bull' and not rollback:raise ValueError('TEST_MIGRATION_FAILURE')
    if 'dry_run=False' in code:
     with sqlite3.connect(self.root/('brain-'+p)/'brain.sqlite3') as db:
      s=json.loads(db.execute('SELECT body FROM state').fetchone()[0]);self.assertEqual(s['method'],old);s['method']=new;db.execute('UPDATE state SET body=?',(json.dumps(s),));db.execute("INSERT INTO events(kind,body) VALUES('journal','{}')")
    return json.dumps({'to_method':new})
   if args[1]=='run' and '-d' in args:
    name=args[args.index('--name')+1];containers[name]=copy.deepcopy(containers[next(n for n in containers if n.startswith(name+'-previous-'))]);containers[name]['State']['Running']=True;containers[name]['Config']['Labels']['superbot.sha']=u.TARGET;return 'new'
   if args[1]=='run':return ''
   raise AssertionError(args)
  def wait(probe,seconds,code):
   for p in u.NAMES:state_change(p)
   self.assertTrue(probe(),code)
  def app():return {p:{'portfolio':{'equity':800},'execution':{'fresh_fast_data':True,'operator_paused':(self.root/('brain-'+p)/'pause.flag').exists()}} for p in u.NAMES}
  class Args:action='apply'
  args=Args();args.repo=str(repo);args.old_repo=str(oldrepo)
  with patch.object(u,'ROOT',self.root),patch.object(u,'BACKUPS',backups),patch.object(u,'run',side_effect=fake_run),patch.object(u,'inspect',side_effect=lambda n:copy.deepcopy(containers[n])),patch.object(u,'wait_until',side_effect=wait),patch.object(u,'paired_app',side_effect=app),patch.object(u,'emit'),patch.dict('os.environ',{'DEEPSEEK_API_KEY':'test','BRAIN_UPDATE_APPROVED':'paper:'+u.TARGET}):
   if fail:
    with self.assertRaisesRegex(ValueError,'TEST_MIGRATION_FAILURE'):u.main(args)
   else:u.main(args)
  self.assertFalse(any(c[1] in ('stop','start','rename') and any('superbot-desk-' in x or x=='superbot-brain-pilot' for x in c) for c in commands if len(c)>1))
  for p,n in u.NAMES.items():
   self.assertTrue(containers[n]['State']['Running']);s,_=u.dbread(self.root/('brain-'+p));self.assertEqual(s['desk']['main'],self.account(p)['desk']['main']);self.assertEqual(s['contexts'],self.account(p)['contexts'])
   self.assertEqual(s['method'],(('a' if p=='hawk' else 'b') if fail else ('c' if p=='hawk' else 'd'))*64)
   self.assertEqual((self.root/('brain-'+p)/'pause.flag').exists(),fail)
 def test_complete_rollout_simulation_preserves_existing_accounts(self):self.simulate()
 def test_partial_migration_failure_restarts_old_workers_without_state_restore(self):self.simulate(fail=True)
if __name__=='__main__':unittest.main()
