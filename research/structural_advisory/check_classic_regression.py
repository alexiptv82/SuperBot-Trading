"""Run pytest legacy suite; compare exact failed test IDs, never hide collection errors."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
report=out.with_suffix('.xml')
env=dict(os.environ,PYTHONPATH=str(root/'backend'))
result=subprocess.run([sys.executable,'-m','pytest','-q','backend/tests/test_desk.py',
                       '--junitxml='+str(report)],cwd=root,env=env,check=False)
if result.returncode not in (0,1) or not report.exists():
    raise SystemExit('suite_collection_or_execution_error')
tree=ET.parse(report)
cases=list(tree.iter('testcase'))
payload={'tests':len(cases),'failures':sorted(
    c.get('classname','')+'::'+c.get('name','') for c in cases
    if c.find('failure') is not None or c.find('error') is not None)}
out.write_text(json.dumps(payload,sort_keys=True))
if len(cases)<90:
    raise SystemExit('suite_not_collected')
