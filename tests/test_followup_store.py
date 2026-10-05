"""Exercise persistence without ever writing to the real demo or working file."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO

import pandas as pd

from src.data_loader import DEFAULT_DATA_PATH, DataValidationError
from src.followup_store import FollowupStore
from src.metrics import calculate_kpis, get_followups, followup_progress


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.demo = Path(self.temp.name) / 'demo.csv'
        self.demo.write_bytes(DEFAULT_DATA_PATH.read_bytes())
        self.working = self.demo.with_name('working.csv')
        self.store = FollowupStore(self.demo, self.working)
        self.original_hash = hashlib.sha256(self.demo.read_bytes()).hexdigest()
        self.df, self.revision = self.store.load()
        self.edits = get_followups(self.df, status='待跟进').iloc[:1].copy()
        self.person = self.edits.attendee_id.iloc[0]
        self.edits.loc[:, 'followup_status'] = '跟进中'
        self.edits.loc[:, 'followup_owner'] = 'Mia'
        self.edits.loc[:, 'next_action'] = '约线上沟通，确认合作需求'
        self.edits.loc[:, 'notes'] = 'Synthetic Demo Data · V0.2验证'

    def test_save_reload_progress_and_export(self):
        self.assertFalse(self.working.exists())
        self.store.save_edits(self.df, self.edits, self.revision)
        fresh = FollowupStore(self.demo, self.working)
        data, revision = fresh.load()
        self.assertNotEqual(revision, self.revision)
        self.assertEqual(len(data), 100)
        self.assertEqual(calculate_kpis(data)['pending_followups'], 12)
        self.assertEqual(calculate_kpis(data)['valuable_connections'], 22)
        self.assertEqual(followup_progress(data), {'待跟进':12,'已初步建联':4,'跟进中':4,'已完成对接':2})
        changed = data.set_index('attendee_id').loc[self.person]
        self.assertEqual(changed.next_action, self.edits.next_action.iloc[0])
        exported = pd.read_csv(BytesIO(fresh.export_csv()), encoding='utf-8-sig', keep_default_na=False)
        self.assertEqual(len(exported), 22)
        match = exported[exported['姓名'] == changed['name']].iloc[0]
        self.assertEqual(match['当前跟进状态'], '跟进中')
        self.assertEqual(match['跟进负责人'], 'Mia')
        self.assertEqual(match['下一步动作'], changed.next_action)
        self.assertNotIn('景川', exported['跟进负责人'].tolist())
        self.assertEqual(hashlib.sha256(self.demo.read_bytes()).hexdigest(), self.original_hash)
        untouched = ~data.attendee_id.eq(self.person)
        pd.testing.assert_frame_equal(data[untouched], self.df[untouched])

    def test_restore_and_repeat_save(self):
        self.store.save_edits(self.df, self.edits, self.revision)
        current, rev = self.store.load()
        again = get_followups(current).iloc[:1].copy()
        again.loc[:, 'notes'] = '二次保存'
        self.store.save_edits(current, again, rev)
        _, rev = self.store.load()
        self.store.restore(rev)
        self.assertFalse(self.working.exists())
        restored, _ = self.store.load()
        pd.testing.assert_frame_equal(restored, self.df)
        self.store.restore(self.revision)
        self.assertEqual(hashlib.sha256(self.demo.read_bytes()).hexdigest(), self.original_hash)

    def test_reject_invalid_subset_without_writing(self):
        bad_cases = []
        for column, value in [('attendee_id',''), ('name','其他姓名'), ('followup_status','未知'),
                              ('followup_owner','任意姓名'), ('next_action',''), ('followup_owner','')]:
            bad = self.edits.copy()
            bad.loc[:, column] = value
            bad_cases.append(bad)
        bad_cases.extend([pd.concat([self.edits,self.edits]), self.df[self.df.attended.eq('否')].iloc[:1],
                          self.df[self.df.connection_intent.eq('行业交流')].iloc[:1], self.edits.drop(columns='attendee_id')])
        for bad in bad_cases:
            with self.subTest(columns=list(bad.columns)):
                with self.assertRaises(DataValidationError):
                    self.store.save_edits(self.df, bad, self.revision)
                self.assertFalse(self.working.exists())

    def test_reject_snapshot_row_count_or_core_tampering(self):
        for bad in [self.df.iloc[:-1], pd.concat([self.df, self.df.iloc[:1]]), self.df.assign(name='篡改')]:
            with self.assertRaises(DataValidationError):
                self.store.save_edits(bad, self.edits, self.revision)
            self.assertFalse(self.working.exists())

    def test_pause_and_complete_are_valid_but_require_no_assignment(self):
        for status in ['暂不跟进', '已完成对接']:
            edits = self.edits.copy()
            edits.loc[:, 'followup_status'] = status
            with self.assertRaises(DataValidationError):
                self.store.save_edits(self.df, edits, self.revision)
            edits.loc[:, 'followup_owner'] = ''
            edits.loc[:, 'next_action'] = '暂无'
            self.store.save_edits(self.df, edits, self.revision)
            data, rev = self.store.load()
            self.assertEqual(len(get_followups(data)), 22)
            self.assertEqual(len(get_followups(data, status=status)), 1 if status == '暂不跟进' else 3)
            self.store.restore(rev)

    def test_stale_save_and_restore_rejected(self):
        self.store.save_edits(self.df, self.edits, self.revision)
        with self.assertRaisesRegex(DataValidationError, '更新'):
            self.store.save_edits(self.df, self.edits, self.revision)
        with self.assertRaisesRegex(DataValidationError, '更新'):
            self.store.restore(self.revision)
        self.assertTrue(self.working.exists())

    def test_write_failure_keeps_previous_file_and_cleans_temporary(self):
        self.store.save_edits(self.df, self.edits, self.revision)
        before = self.working.read_bytes()
        df, rev = self.store.load()
        edits = get_followups(df).iloc[:1].copy()
        edits.loc[:, 'notes'] = '这次不应写入'
        with patch('src.followup_store.os.replace', side_effect=PermissionError):
            with self.assertRaisesRegex(DataValidationError, '保存'):
                self.store.save_edits(df, edits, rev)
        self.assertEqual(self.working.read_bytes(), before)
        self.assertEqual(len(list(self.working.parent.glob('*.tmp'))), 0)

    def test_corrupt_or_tampered_working_is_not_silently_ignored(self):
        self.working.write_text('bad,csv\n1,2', encoding='utf-8')
        with self.assertRaises(DataValidationError): self.store.load()
        self.df.iloc[:-1].to_csv(self.working,index=False,encoding='utf-8-sig')
        with self.assertRaises(DataValidationError): self.store.load()
        bad = self.df.copy()
        bad.loc[0,'organization'] = '不应改动'
        bad.to_csv(self.working,index=False,encoding='utf-8-sig')
        with self.assertRaises(DataValidationError): self.store.load()

    def test_save_and_cleanup_failure_still_shows_friendly_error(self):
        self.store.save_edits(self.df, self.edits, self.revision)
        before = self.working.read_bytes()
        current, rev = self.store.load()
        edits = get_followups(current).iloc[:1].copy()
        edits.loc[:, 'notes'] = '保存应失败'
        with patch('src.followup_store.os.replace', side_effect=PermissionError), \
             patch('src.followup_store.Path.unlink', side_effect=PermissionError):
            with self.assertRaisesRegex(DataValidationError, '保存.*临时'):
                self.store.save_edits(current, edits, rev)
        self.assertEqual(self.working.read_bytes(), before)
        self.assertEqual(len(list(self.working.parent.glob('*.tmp'))), 1)

    def test_restore_can_recover_invalid_working(self):
        self.working.write_text('invalid',encoding='utf-8')
        self.store.restore(self.store.revision())
        restored, _ = self.store.load()
        pd.testing.assert_frame_equal(restored,self.df)


if __name__ == '__main__': unittest.main()
