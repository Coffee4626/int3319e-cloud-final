import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from app.datasets import profile, prepare, read_csv
from app.infrastructure.aws import S3ArtifactStore


class DatasetTests(unittest.TestCase):
    def test_quotes_bom_and_newlines_are_valid_csv(self):
        columns, rows = read_csv('\ufeffname,label\n"first, customer",yes\n"two\nlines",no\n')
        self.assertEqual(columns, ['name', 'label'])
        self.assertEqual(rows[1][0], 'two\nlines')

    def test_invalid_headers_and_ragged_rows_rejected(self):
        for text in ('a,a\n1,2\n3,4', 'a,b\n1\n2,3', 'a,b\n1,2,3\n4,5,6', 'a\n1\n2'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                profile(text)

    def test_metadata_preview_is_bounded_without_truncating_training_csv(self):
        long_value = 'v' * 1000
        text = f'x,y\n{long_value},1\n{long_value}2,2\n'
        self.assertEqual(len(profile(text)['preview'][0]['x']), 64)
        result, _ = prepare(text, {'target': 'y'})
        self.assertIn(long_value, result)

    def test_model_archive_cannot_escape_cache_directory(self):
        store = S3ArtifactStore(Mock(), 'test')
        def download(key, path):
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('../escaped.txt', 'unsafe')
        store.download = download
        with TemporaryDirectory() as folder:
            cache = Path(folder) / 'cache'
            cache.mkdir()
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                store.extract_model('models/test.zip', cache)
            self.assertFalse((Path(folder) / 'escaped.txt').exists())

    def test_preprocessing_never_fills_missing_target(self):
        with self.assertRaisesRegex(ValueError, 'fewer than two'):
            prepare('x,y\n1,\n2,yes\n', {'target': 'y'})
        prepared, report = prepare('x,y\n1,yes\n2,no\n3,null\n', {'target': 'y'})
        self.assertEqual(report['removed_missing_target'], 1)
        self.assertEqual(read_csv(prepared)[1], [['1', 'yes'], ['2', 'no']])
