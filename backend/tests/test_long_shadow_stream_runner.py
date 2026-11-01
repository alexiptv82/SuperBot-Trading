"""Read-only capture watcher: incremental/rotation and corruption contracts."""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from long_shadow_stream_runner import CaptureTail, FeedNotReady

def envelope(raw, ts=1793549782000, session=1):
    return json.dumps({'raw_frame':raw,'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                       'received_at_ms':ts,'session':session})

class CaptureTailTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.part=self.root/'ws_raw_frames_00001.jsonl'
        self.tail=CaptureTail(self.root)
    def test_partial_line_not_consumed_before_newline(self):
        line=envelope('pong')
        self.part.write_text(line[:30]);self.tail.poll()
        self.assertEqual(self.tail.counts['HEARTBEAT'],0)
        with self.part.open('a') as f:f.write(line[30:]+'\n')
        self.tail.poll();self.assertEqual(self.tail.counts['HEARTBEAT'],1)
    def test_incremental_poll_does_not_duplicate(self):
        self.part.write_text(envelope('pong')+'\n')
        self.tail.poll();self.tail.poll()
        self.assertEqual(self.tail.counts['HEARTBEAT'],1)
    def test_rotated_part_is_consumed(self):
        self.part.write_text(envelope('pong')+'\n');self.tail.poll()
        (self.root/'ws_raw_frames_00002.jsonl').write_text(envelope('pong')+'\n')
        self.tail.poll();self.assertEqual(self.tail.counts['HEARTBEAT'],2)
    def test_symlink_rejected(self):
        self.part.symlink_to(self.root/'missing')
        with self.assertRaisesRegex(FeedNotReady,'part_type'):
            self.tail.poll()
    def test_corrupted_frame_fail_closed(self):
        self.part.write_text('{"not":"valid capture"}\n')
        with self.assertRaisesRegex(FeedNotReady,'corrupt_capture'):
            self.tail.poll()
        self.assertEqual(self.tail.feed.snapshots,{})
    def test_never_reports_orders(self):
        s=self.tail.status();self.assertFalse(s['can_execute_orders']);self.assertEqual(s['orders_created'],0)
if __name__=='__main__':unittest.main()
