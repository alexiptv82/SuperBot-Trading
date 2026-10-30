"""Run the real legacy suite, preserving exact failure identities for A/B."""
import json
import os
from pathlib import Path
import sys
import unittest
root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
os.chdir(root)
sys.path[:0]=[str(root),str(root/'backend')]
suite=unittest.defaultTestLoader.loadTestsFromName('backend.tests.test_desk')
result=unittest.TextTestRunner(verbosity=1).run(suite)
payload={'tests':result.testsRun,'failures':sorted(t.id() for t,_ in result.failures+result.errors)}
out.write_text(json.dumps(payload,sort_keys=True))
if result.testsRun < 90:
    raise SystemExit('suite_not_collected')
