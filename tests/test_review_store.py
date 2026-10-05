"""Real file round-trips and failures in isolated temporary directories."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.review_store import ReviewStore, ReviewStoreError


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'draft.md'
        self.store = ReviewStore(self.path)

    def test_roundtrip_exact_edited_text_and_new_instance(self):
        text, revision = self.store.load()
        self.assertEqual(text, '')
        edited = '# 草稿\n\n人工修改后的段落。\n第二行\n'
        self.store.save(edited, revision)
        self.assertEqual(ReviewStore(self.path).load()[0], edited)
        self.assertEqual(self.path.read_bytes(), edited.encode('utf-8'))
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_stale_save_does_not_overwrite_newer_draft(self):
        _, revision = self.store.load()
        self.store.save('第一份', revision)
        with self.assertRaisesRegex(ReviewStoreError, '已更新'):
            self.store.save('陈旧编辑', revision)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '第一份')

    def test_failed_write_preserves_previous_draft(self):
        _, revision = self.store.load()
        self.store.save('原有人工编辑', revision)
        _, revision = self.store.load()
        with patch('src.review_store.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaisesRegex(ReviewStoreError, '保存失败'):
                self.store.save('新稿', revision)
        self.assertEqual(self.store.load()[0], '原有人工编辑')
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_invalid_encoding_and_read_permissions_are_friendly(self):
        self.path.write_bytes(b'\xff\xfe')
        with self.assertRaisesRegex(ReviewStoreError, '读取'):
            self.store.load()
        with patch('pathlib.Path.read_bytes', side_effect=PermissionError('locked')):
            with self.assertRaises(ReviewStoreError):
                self.store.load()

    def test_cleanup_failure_does_not_mask_save_error(self):
        _, revision = self.store.load()
        with patch('src.review_store.os.replace', side_effect=PermissionError('locked')), \
             patch('pathlib.Path.unlink', side_effect=PermissionError('locked')):
            with self.assertRaisesRegex(ReviewStoreError, '保存失败.*临时'):
                self.store.save('草稿', revision)
        self.assertFalse(self.path.exists())


if __name__ == '__main__': unittest.main()
