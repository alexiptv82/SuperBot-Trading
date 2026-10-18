"""Only authenticated ciphertext goes to Actions logs. No plaintext trading history or secrets."""
import base64,hashlib,json,os,pathlib,secrets,sys,tempfile
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'work-audit'))
from deploy_app_link import Target,PIN,BACKUP
source=(HERE/'collect_remote.py').read_text()
pub=serialization.load_pem_public_key((HERE/'transfer-public.pem').read_bytes())
with tempfile.TemporaryDirectory(prefix='superbot-weekend-') as dirname:
 p=pathlib.Path(dirname);p.chmod(0o700)
 targets=[Target('51.91.109.45','root',os.environ['OLD_SSH_KEY'],PIN,p),
          Target('51.79.205.82','ubuntu',os.environ['SG_SSH_KEY'],os.environ['SG_KNOWN_HOSTS'],p,sudo=True)]
 for target in targets:
  backup=target.call(BACKUP,{})
  if not backup['restore_regular_files_verified']:raise RuntimeError('Backup not verified')
  print(json.dumps({'phase':'verified_copy','host':target.host,'backup':backup['backup_directory'],'verified':True}),flush=True)
  bundle=target.call(source,{'backup':backup['backup_directory']})
  raw=base64.b64decode(bundle.pop('tar_b64'))
  if hashlib.sha256(raw).hexdigest()!=bundle['sha256']:raise RuntimeError('Transfer checksum mismatch')
  key=secrets.token_bytes(32);nonce=secrets.token_bytes(12);aad=bundle['host'].encode()
  cipher=AESGCM(key).encrypt(nonce,raw,aad)
  wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
  metadata={**bundle,'nonce':base64.b64encode(nonce).decode(),'wrapped_key':base64.b64encode(wrapped).decode(),
     'cipher_sha256':hashlib.sha256(cipher).hexdigest(),'cipher_bytes':len(cipher)}
  print('AUDIT_META '+json.dumps(metadata),flush=True)
  encoded=base64.b64encode(cipher).decode()
  for i in range(0,len(encoded),16000):print('AUDIT_CIPHER '+bundle['host']+' '+str(i//16000)+' '+encoded[i:i+16000],flush=True)
 print('READ_ONLY_WEEKEND_EVIDENCE_CAPTURED',flush=True)
