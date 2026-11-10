"""Finto server delle API pubbliche di GitHub, SOLO per le prove automatiche (127.0.0.1, nessuna rete vera, nessuna credenziale).

Serve le sole quattro risorse che github_run_proof.py interroga: la run, il contenuto di un file a un commit, i job, le annotazioni.
Registra ogni richiesta, cosi' i test possono provare che si fanno solo GET e che non parte nessuna credenziale.
"""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = "alexiptv82/SuperBot-Trading"
WORKFLOW_PATH = ".github/workflows/age-v2-recovery-verify.yml"
SCRIPT_PATH = "deploy/extbackup/age-v2-recovery/verify_recovery.py"
BRANCH = "work/age-v2-recovery-run-20261110"
JOB_ID = 987654321


class FakeGitHub:
    def __init__(self, repo=REPO):
        self.repo = repo
        self.json_routes = {}          # percorso -> oggetto JSON
        self.raw_routes = {}           # (percorso, ref) -> byte
        self.log = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                outer.log.append({"metodo": "GET", "percorso": u.path, "intestazioni": sorted(k.lower() for k in self.headers.keys())})
                path = urllib.parse.unquote(u.path)
                pre = "/repos/%s/contents/" % outer.repo
                if path.startswith(pre):
                    body = outer.raw_routes.get((path[len(pre):], (q.get("ref") or [""])[0]))
                    return self.send(200, body) if body is not None else self.send(404, b'{"message":"Not Found"}')
                if path in outer.json_routes:
                    return self.send(200, json.dumps(outer.json_routes[path]).encode())
                self.send(404, b'{"message":"Not Found"}')

            def do_POST(self):
                outer.log.append({"metodo": "POST", "percorso": self.path, "intestazioni": []})
                self.send(405, b"{}")

            do_PUT = do_PATCH = do_DELETE = do_POST

            def send(self, code, body):
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def register_valid(self, cert, workflow_bytes, script_bytes, run=None, jobs=None, annotations=None, branch=BRANCH, files=None):
        """Registra una run RIUSCITA e coerente con il certificato; gli argomenti opzionali servono ai test per falsificare un pezzo."""
        rid, commit, attempt = str(cert["run_id"]), cert["commit"], str(cert["run_attempt"])
        base = "/repos/%s" % self.repo
        r = {"id": int(rid), "run_attempt": int(attempt), "status": "completed", "conclusion": "success", "head_sha": commit,
             "event": "push", "head_branch": branch, "path": WORKFLOW_PATH, "repository": {"full_name": self.repo},
             "head_repository": {"full_name": self.repo}}
        r.update(run or {})
        self.json_routes["%s/actions/runs/%s" % (base, rid)] = r
        self.json_routes["%s/actions/runs/%s/attempts/%s/jobs" % (base, rid, attempt)] = {
            "jobs": jobs if jobs is not None else [{"id": JOB_ID, "name": "verify", "conclusion": "success"}]}
        msg = json.dumps(cert, sort_keys=True, separators=(",", ":"))
        self.json_routes["%s/check-runs/%s/annotations" % (base, JOB_ID)] = (
            annotations if annotations is not None else [{"title": "CERTIFICATO", "message": msg}])
        self.raw_routes[(WORKFLOW_PATH, commit)] = (files or {}).get(WORKFLOW_PATH, workflow_bytes)
        self.raw_routes[(SCRIPT_PATH, commit)] = (files or {}).get(SCRIPT_PATH, script_bytes)
