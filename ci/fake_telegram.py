"""Finto server Telegram per i test: registra i messaggi inviati."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUT = '/tmp/telegram_messages.jsonl'


class H(BaseHTTPRequestHandler):
    def _reply(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = json.loads(self.rfile.read(length) or b'{}')
        if self.path.endswith('/sendMessage'):
            with open(OUT, 'a') as f:
                f.write(json.dumps({'chat_id': data.get('chat_id'), 'text': data.get('text')}) + '\n')
        self._reply({'ok': True, 'result': {}})

    def do_GET(self):
        if self.path.split('?')[0].endswith('/getUpdates'):
            time.sleep(2)
        self._reply({'ok': True, 'result': []})

    def log_message(self, *a):
        pass


ThreadingHTTPServer(('127.0.0.1', 9100), H).serve_forever()
