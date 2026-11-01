"""Frozen research bytes: require exact original V6.1.1, no source edits."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_materialize_frozen_long_v611 import (
    read_frozen_engine_bytes,materialize_for_research,MAX_ENGINE_BYTES,
)
from long_shadow_offline_probe import PINNED_ENGINE_SHA256,frozen_engine


class FrozenV611Bytes(unittest.TestCase):
    def test_byte_exact_frozen_source_and_version(self):
        original=read_frozen_engine_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),PINNED_ENGINE_SHA256)
        self.assertLess(len(original),MAX_ENGINE_BYTES)
        self.assertIn(b"VERSION = '3.0.0'",original)
    def test_materialized_file_remains_pinned_and_valid_import(self):
        with tempfile.TemporaryDirectory() as folder:
            f=materialize_for_research(folder)
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),
                             PINNED_ENGINE_SHA256)
            engine=frozen_engine(f)
            self.assertEqual(engine.VERSION,'3.0.0')
            self.assertEqual(engine.DEFAULT_SLOW_WARMUP,200)
    def test_no_overwrite_of_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            first=materialize_for_research(folder)
            with self.assertRaises(FileExistsError):
                materialize_for_research(folder)
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                             PINNED_ENGINE_SHA256)
    def test_corrupted_source_hash_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bogus=Path(folder)/'blob'
            bogus.write_bytes(b'not the genuine frozen engine')
            with patch('research_materialize_frozen_long_v611.SOURCE',bogus):
                with self.assertRaises(ValueError):
                    read_frozen_engine_bytes()
    def test_symlinked_blob_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            blob=Path(folder)/'blob'
            blob.symlink_to(Path(folder)/'other')
            with patch('research_materialize_frozen_long_v611.SOURCE',blob):
                with self.assertRaisesRegex(ValueError,'source_unavailable'):
                    read_frozen_engine_bytes()

if __name__=='__main__':
    unittest.main()
