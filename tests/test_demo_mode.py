"""Exercise public demo isolation, downloads and the absence of file writes."""
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.data_loader import DEFAULT_DATA_PATH, DataValidationError
from src.metrics import calculate_kpis, get_followups
from src.followup_store import FollowupStore

ROOT = Path(__file__).resolve().parents[1]


class DemoModeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.demo = Path(temp.name) / 'demo.csv'
        self.baseline = DEFAULT_DATA_PATH.read_bytes()
        self.demo.write_bytes(self.baseline)
        self.working = self.demo.with_name('working.csv')
        self.draft = self.demo.with_name('draft.md')

    def test_session_store_isolation_validation_restore_and_export(self):
        from src.session_store import SessionFollowupStore, SessionReviewStore
        first, second = {}, {}
        store = SessionFollowupStore(first, self.demo)
        other = SessionFollowupStore(second, self.demo)
        data, revision = store.load()
        edits = get_followups(data, status='待跟进').iloc[:1].copy()
        edits['followup_status'] = '跟进中'
        edits['notes'] = '模拟验证：仅访问者一可见'
        store.save_edits(data, edits, revision)
        fresh = SessionFollowupStore(first, self.demo)
        changed, current = fresh.load()
        self.assertEqual(calculate_kpis(changed)['pending_followups'], 12)
        self.assertEqual(calculate_kpis(other.load()[0])['pending_followups'], 13)
        exported = pd.read_csv(BytesIO(fresh.export_csv()), encoding='utf-8-sig')
        self.assertEqual(len(exported), 22)
        self.assertIn('模拟验证：仅访问者一可见', exported['备注'].tolist())
        changed.loc[:, 'notes'] = '返回值不能修改保存状态'
        self.assertNotIn('返回值不能修改保存状态', fresh.load()[0].notes.tolist())
        with self.assertRaises(DataValidationError):
            fresh.save_edits(data, edits, revision)
        invalid = get_followups(fresh.load()[0]).iloc[:1].copy()
        invalid['followup_owner'] = ''
        with self.assertRaises(DataValidationError):
            fresh.save_edits(fresh.load()[0], invalid, current)
        review = SessionReviewStore(first)
        text, rev = review.load()
        self.assertEqual(text, '')
        review.save('# 模拟验证\n访问者一草稿', rev)
        self.assertEqual(SessionReviewStore(first).load()[0], '# 模拟验证\n访问者一草稿')
        self.assertEqual(SessionReviewStore(second).load()[0], '')
        fresh.restore(current)
        self.assertEqual(calculate_kpis(fresh.load()[0])['pending_followups'], 13)
        self.assertEqual(self.demo.read_bytes(), self.baseline)
        self.assertEqual(list(self.demo.parent.iterdir()), [self.demo])

    def test_modes_default_local_explicit_demo_and_invalid_stop(self):
        from src.app_mode import get_app_mode
        without_mode = {k:v for k,v in os.environ.items() if k != 'APP_MODE'}
        with patch.dict(os.environ, without_mode, clear=True):
            self.assertEqual(get_app_mode(), 'local')
        with patch.dict(os.environ, {'APP_MODE':'demo'}):
            self.assertEqual(get_app_mode(), 'demo')
        with patch.dict(os.environ, {'APP_MODE':'unknown'}):
            app = AppTest.from_file(str(ROOT / 'app.py')).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertFalse(app.metric)

    def test_cloud_mode_setting_and_environment_precedence(self):
        from src.app_mode import get_app_mode
        without_mode = {k:v for k,v in os.environ.items() if k != 'APP_MODE'}
        with patch.dict(os.environ, without_mode, clear=True), patch('src.app_mode.st.secrets', {'APP_MODE':'demo'}):
            self.assertEqual(get_app_mode(), 'demo')
        with patch.dict(os.environ, {'APP_MODE':'local'}), patch('src.app_mode.st.secrets', {'APP_MODE':'demo'}):
            self.assertEqual(get_app_mode(), 'local')

    def test_public_ui_edit_kpi_review_download_and_two_visitors(self):
        # Real local files deliberately contain private-looking fixture text.
        # The public app must never read them, even when they exist.
        local = FollowupStore(self.demo, self.working)
        data, rev = local.load()
        edits = get_followups(data, status='待跟进').iloc[:1].copy()
        edits['notes'] = 'LOCAL_ONLY_FIXTURE'
        local.save_edits(data, edits, rev)
        self.draft.write_text('LOCAL_ONLY_DRAFT', encoding='utf-8')
        original_working = self.working.read_bytes()
        original_draft = self.draft.read_bytes()
        with patch.dict(os.environ, {'APP_MODE':'demo'}), \
             patch('src.followup_store.DEFAULT_WORKING_PATH', self.working), \
             patch('src.review_store.DEFAULT_DRAFT_PATH', self.draft):
            first = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
            second = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
            first.radio(key='page').set_value('关系跟进').run()
            self.assertNotIn('LOCAL_ONLY_FIXTURE', first.dataframe[0].value['备注'].tolist())
            key = first.session_state['active_editor_key']
            first.session_state[key] = {
                'edited_rows':{0:{'当前跟进状态':'跟进中', '跟进负责人':'Mia',
                                  '下一步动作':'模拟验证：约线上沟通', '备注':'DEMO_VISITOR_ONE'}},
                'added_rows':[], 'deleted_rows':[],
            }
            payloads = {}
            original_download = st.download_button
            def capture(*args, **kwargs):
                payloads[kwargs.get('key')] = kwargs.get('data')
                return original_download(*args, **kwargs)
            with patch('streamlit.download_button', side_effect=capture):
                first.button(key='save_changes').click().run()
                self.assertFalse(first.exception)
                self.assertEqual({m.label:m.value for m in first.metric}['待跟进'], '12')
                exported = pd.read_csv(BytesIO(payloads['export_followups']), encoding='utf-8-sig')
                self.assertEqual(len(exported), 22)
                self.assertIn('DEMO_VISITOR_ONE', exported['备注'].tolist())
                first.radio(key='page').set_value('活动总览').run()
                self.assertEqual({m.label:m.value for m in first.metric}['待跟进人数'], '12')
                second.run()
                self.assertEqual({m.label:m.value for m in second.metric}['待跟进人数'], '13')
                first.radio(key='page').set_value('活动复盘').run()
                self.assertEqual(first.text_area(key='review_editor').value, '')
                first.text_area(key='review_highlights').set_value('模拟验证：访客一观察').run()
                first.button(key='generate_review').click().run()
                self.assertIn('待跟进 12 人', first.text_area(key='review_editor').value)
                self.assertIn('模拟验证：访客一观察', first.text_area(key='review_editor').value)
                first.text_area(key='review_editor').set_value('访客一编辑后全文').run()
                first.button(key='save_review').click().run()
                first.text_area(key='review_editor').set_value('访客一最后未保存正文')
                first.button(key='prepare_review_export').click().run()
                self.assertEqual(payloads['export_review'], '访客一最后未保存正文'.encode('utf-8'))
                first.button(key='return_from_review_export').click().run()
                first.radio(key='page').set_value('活动观察').run()
                first.radio(key='page').set_value('活动复盘').run()
                self.assertEqual(first.text_area(key='review_editor').value, '访客一最后未保存正文')
                second.radio(key='page').set_value('活动复盘').run()
                self.assertEqual(second.text_area(key='review_editor').value, '')
                self.assertEqual(second.text_area(key='review_highlights').value, '')
                first.radio(key='page').set_value('关系跟进').run()
                first.button(key='request_restore').click().run()
                first.button(key='cancel_restore').click().run()
                self.assertEqual({m.label:m.value for m in first.metric}['待跟进'], '12')
                first.button(key='request_restore').click().run()
                first.button(key='confirm_restore').click().run()
                self.assertEqual({m.label:m.value for m in first.metric}['待跟进'], '13')
        self.assertEqual(self.working.read_bytes(), original_working)
        self.assertEqual(self.draft.read_bytes(), original_draft)
        self.assertEqual(DEFAULT_DATA_PATH.read_bytes(), self.baseline)

    def test_public_save_does_not_create_working_or_draft_files(self):
        with patch.dict(os.environ, {'APP_MODE':'demo'}), \
             patch('src.followup_store.DEFAULT_WORKING_PATH', self.working), \
             patch('src.review_store.DEFAULT_DRAFT_PATH', self.draft):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
            app.radio(key='page').set_value('关系跟进').run()
            key = app.session_state['active_editor_key']
            app.session_state[key] = {'edited_rows':{0:{'备注':'模拟验证'}},
                                      'added_rows':[], 'deleted_rows':[]}
            app.button(key='save_changes').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(self.working.exists())
            app.radio(key='page').set_value('活动复盘').run()
            app.button(key='generate_review').click().run()
            app.button(key='save_review').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(self.draft.exists())
            self.assertEqual(list(self.demo.parent.iterdir()), [self.demo])

    def test_missing_demo_shows_error_without_crashing_or_writing(self):
        with patch.dict(os.environ, {'APP_MODE':'demo'}), \
             patch('src.session_store.DEFAULT_DATA_PATH', self.demo.with_name('missing.csv')):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertFalse(app.metric)

    def test_demo_starts_from_another_working_directory(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.demo.parent)
        with patch.dict(os.environ, {'APP_MODE':'demo'}):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual({m.label:m.value for m in app.metric}['报名人数'], '100')


if __name__ == '__main__':
    unittest.main()
