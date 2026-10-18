import json
import os
from pathlib import Path
import tempfile
from deploy_app_link import PIN, Target, public_check

TAG='r39119231791a1'
with tempfile.TemporaryDirectory(prefix='superbot-link-final-') as dirname:
    tmp=Path(dirname);tmp.chmod(0o700)
    old=Target('51.91.109.45','root',os.environ['OLD_SSH_KEY'],PIN,tmp)
    sg=Target('51.79.205.82','ubuntu',os.environ['SG_SSH_KEY'],os.environ['SG_KNOWN_HOSTS'],tmp,sudo=True)
    print(json.dumps(old.stage('verify_old',tag=TAG)),flush=True)
    print(json.dumps(sg.stage('verify_sg',tag=TAG)),flush=True)
    print(json.dumps(sg.stage('finalize',tag=TAG)),flush=True)
    print(json.dumps(old.stage('finalize',tag=TAG)),flush=True)
    print(json.dumps(public_check()),flush=True)
    print('APP_LINK_HANDOFF_VERIFIED',flush=True)
