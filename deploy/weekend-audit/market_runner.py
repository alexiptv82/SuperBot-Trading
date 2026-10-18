import base64,hashlib,json,os,pathlib,secrets,sys,tempfile
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'work-audit'))
from deploy_app_link import Target
pub=serialization.load_pem_public_key((HERE/'transfer-public.pem').read_bytes())
with tempfile.TemporaryDirectory(prefix='superbot-market-audit-') as dirname:
 p=pathlib.Path(dirname);p.chmod(0o700)
 target=Target('51.79.205.82','ubuntu',os.environ['SG_SSH_KEY'],os.environ['SG_KNOWN_HOSTS'],p,sudo=True)
 result=target.call((HERE/'market_remote.py').read_text(),{},timeout=600)
 raw=base64.b64decode(result.pop('tar_b64'))
 assert hashlib.sha256(raw).hexdigest()==result['sha256']
 key=secrets.token_bytes(32);nonce=secrets.token_bytes(12)
 cipher=AESGCM(key).encrypt(nonce,raw,result['host'].encode())
 wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
 metadata={**result,'nonce':base64.b64encode(nonce).decode(),'wrapped_key':base64.b64encode(wrapped).decode(),
   'cipher_sha256':hashlib.sha256(cipher).hexdigest(),'cipher_bytes':len(cipher)}
 print('AUDIT_META '+json.dumps(metadata),flush=True)
 encoded=base64.b64encode(cipher).decode()
 for i in range(0,len(encoded),16000):print('AUDIT_CIPHER '+result['host']+' '+str(i//16000)+' '+encoded[i:i+16000],flush=True)
 print('PUBLIC_MARKET_EVIDENCE_CAPTURED',flush=True)
