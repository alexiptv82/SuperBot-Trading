"""Standalone continuous READ-ONLY watcher of Bitget capture files.

No orders, no wallet, no exchange network. Reports readiness of an external
append-only public market data capture; does not evaluate trading decisions.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import time

from long_shadow_stream import ObservedFeed, FeedNotReady, SYMBOLS

PART = re.compile(r'ws_raw_frames_\d{5}\.jsonl\Z')


class CaptureTail:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.offsets = {}
        self.partial = {}
        self.feed = ObservedFeed()
        self.counts = Counter()

    def poll(self):
        """Read only newline-complete appended frames in part order."""
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise FeedNotReady('missing_or_symlink_capture_dir')
        parts = sorted(x for x in self.directory.iterdir() if PART.fullmatch(x.name))
        for path in parts:
            if path.is_symlink() or not path.is_file():
                raise FeedNotReady('unexpected_part_type')
            length = path.stat().st_size
            offset = self.offsets.get(path.name, 0)
            if length < offset:
                self.feed.reset(self.feed.session)
                raise FeedNotReady('capture_part_truncated')
            if length == offset:
                continue
            with path.open('rb') as stream:
                stream.seek(offset)
                chunk = stream.read(min(8_000_000, length-offset))
            self.offsets[path.name] = offset+len(chunk)
            data = self.partial.pop(path.name, b'')+chunk
            lines = data.split(b'\n')
            if lines[-1]:
                if len(lines[-1]) > 3_000_000:
                    raise FeedNotReady('unbounded_partial_frame')
                self.partial[path.name] = lines[-1]
            for line in lines[:-1]:
                if not line:
                    continue
                try:
                    kind = self.feed.ingest(json.loads(line))
                except (ValueError,UnicodeError) as exc:
                    self.feed.reset(self.feed.session)
                    raise FeedNotReady('invalid_or_corrupt_capture_frame') from exc
                self.counts[kind] += 1

    def status(self, now_ms=None):
        now=int(time.time()*1000) if now_ms is None else now_ms
        readiness={}
        for symbol in SYMBOLS:
            try:
                self.feed.context(symbol, now)
                readiness[symbol]='SNAPSHOT_CONTEXT_READY_NOT_LIVE_CLOSE_CONFIRMED'
            except FeedNotReady as exc:
                readiness[symbol]='NOT_READY:'+str(exc)
        return {'schema':'long-shadow-stream-readiness-v1',
                'source':'external_public_capture_jsonl',
                'session':self.feed.session, 'last_receipt_ms':self.feed.last_receipt_ms,
                'counts':dict(self.counts),'readiness':readiness,
                'engine_evaluated':False,'orders_created':0,
                'can_execute_orders':False,'paper_eligible':False}


def main():
    p=argparse.ArgumentParser(description='Read-only Bitget public WS capture tail; NO TRADING')
    p.add_argument('--input-dir',required=True)
    p.add_argument('--poll-seconds',type=float,default=1)
    p.add_argument('--duration-seconds',type=int,default=60,
                   help='0 runs until explicitly stopped; 60 seconds by default')
    args=p.parse_args()
    if not .1 <= args.poll_seconds <= 30 or args.duration_seconds < 0:
        p.error('invalid polling interval or duration')
    reader=CaptureTail(args.input_dir)
    begin=time.monotonic()
    next_report=begin
    while args.duration_seconds == 0 or time.monotonic()-begin < args.duration_seconds:
        reader.poll()
        if time.monotonic() >= next_report:
            print(json.dumps(reader.status(),sort_keys=True),flush=True)
            next_report=time.monotonic()+10
        time.sleep(args.poll_seconds)
    print(json.dumps(reader.status(),sort_keys=True),flush=True)

if __name__=='__main__':main()
