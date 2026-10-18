"""Regression checks for Docker negotiation and preserving existing API configuration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app_link_remote as ops

class RemoteConfigTests(unittest.TestCase):
    def test_preserve_api_database_mounts_ports_and_credentials(self):
        original={'Image':'sha256:original','Config':{'Cmd':['python','-m','uvicorn','backend.server:app','--port','8001'],
            'Env':['UNRELATED=preserve','DESK_MODE=live'],'WorkingDir':'/app','Entrypoint':None},
            'HostConfig':{'NetworkMode':'bridge','Binds':['/live-db:/app/data','/private-env:/app/backend/.env'],
                'PortBindings':{'8001/tcp':[{'HostPort':'8002'}]},'RestartPolicy':{'Name':'always'}}}
        saved=copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'remote-url').write_text('http://172.18.0.2:18002')
            config=ops.api_config(original,p,'entry')
        self.assertEqual(original,saved)
        self.assertEqual(config['HostConfig']['Binds'][:2],saved['HostConfig']['Binds'])
        self.assertEqual(config['HostConfig']['PortBindings'],saved['HostConfig']['PortBindings'])
        self.assertIn('UNRELATED=preserve',config['Env'])
        self.assertIn('DESK_MODE=paper',config['Env'])
        self.assertIn('app_link.entry:app',config['Cmd'])
        self.assertEqual(config['Image'],'sha256:original')

    def test_negotiate_engine_api_instead_of_unsupported_legacy_version(self):
        calls=[]
        replies=[{'ApiVersion':'1.52'}, {'Id':'synthetic-container'}]
        class Connection:
            def __init__(self):self.result=replies.pop(0)
            def request(self,method,path,**kw):calls.append((method,path,kw))
            def getresponse(self):return self
            @property
            def status(self):return 200
            def read(self):return json.dumps(self.result).encode()
            def close(self):pass
        with patch.object(ops,'DockerConnection',Connection):
            self.assertEqual(ops.docker_api('POST','/containers/create',{'Image':'synthetic'})['Id'],'synthetic-container')
        self.assertEqual(calls[0][1],'/version')
        self.assertEqual(calls[1][1],'/v1.52/containers/create')

if __name__=='__main__':unittest.main(verbosity=2)
