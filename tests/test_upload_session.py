"""Upload lifecycle, actual page rendering and separate visitor state."""
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
from src.metrics import get_followups
from test_upload_data import CSV, xlsx_bytes

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUP = ('姓名,身份,报名渠道,是否到场,对接意向,跟进负责人\n'
            '上传甲,研究员,官网,是,寻找合作伙伴,\n')


def uploaded(content=CSV, name='活动.csv'):
    file = BytesIO(content.encode('utf-8-sig') if isinstance(content, str) else content)
    file.name = name
    return file


class UploadStoreTests(unittest.TestCase):
    def test_export_escapes_formula_like_uploads_and_edits_without_changing_session_data(self):
        from src.upload_data import parse_upload
        from src.upload_session import UploadFollowupStore, confirm_upload
        state = {}
        frame = parse_upload(FOLLOWUP.replace('上传甲', '=1+1').encode(), 'a.csv')
        confirm_upload(state, frame)
        store = UploadFollowupStore(state['_upload_workspace'])
        for value in ['=2+2', '+1+1', '-1+1', '@SUM(1)', '  =1+1']:
            with self.subTest(value=value):
                snapshot, revision = store.load()
                edited = get_followups(snapshot)
                edited['notes'] = value
                store.save_edits(snapshot, edited, revision)
                exported = pd.read_csv(BytesIO(store.export_csv()), encoding='utf-8-sig')
                self.assertEqual(exported['姓名'][0], "'=1+1")
                self.assertEqual(exported['备注'][0], "'" + value.strip())
                self.assertEqual(store.load()[0].name[0], '=1+1')
                self.assertEqual(store.load()[0].notes[0], value.strip())

    def test_edit_export_revision_and_visitor_isolation_without_disk_access(self):
        from src.upload_data import parse_upload
        from src.upload_session import UploadFollowupStore, confirm_upload
        first, second = {}, {}
        frame = parse_upload(FOLLOWUP.encode(), 'a.csv')
        with patch('pathlib.Path.open', side_effect=AssertionError('No disk access allowed')):
            confirm_upload(first, frame)
            confirm_upload(second, frame)
            first_store = UploadFollowupStore(first['_upload_workspace'])
            second_store = UploadFollowupStore(second['_upload_workspace'])
            data, revision = first_store.load()
            edited = get_followups(data)
            edited['followup_status'] = '待跟进'
            edited['followup_owner'] = '景川'
            edited['next_action'] = '实际填写的动作'
            first_store.save_edits(data, edited, revision)
            self.assertEqual(first_store.load()[0].followup_owner[0], '景川')
            self.assertEqual(second_store.load()[0].followup_owner[0], '')
            self.assertEqual(frame.followup_owner[0], '')
            export = pd.read_csv(BytesIO(first_store.export_csv()), encoding='utf-8-sig')
            self.assertEqual(export['跟进负责人'][0], '景川')
            with self.assertRaises(DataValidationError):
                first_store.save_edits(data, edited, revision)
            latest, revision = first_store.load()
            altered = get_followups(latest)
            altered['name'] = '篡改姓名'
            with self.assertRaises(DataValidationError):
                first_store.save_edits(latest, altered, revision)
            altered = get_followups(latest)
            altered['followup_owner'] = ''
            with self.assertRaises(DataValidationError):
                first_store.save_edits(latest, altered, revision)

    def test_switching_sources_preserves_each_review_without_mixing(self):
        from src.upload_data import parse_upload
        from src.upload_session import confirm_upload, switch_context
        state = {}
        switch_context(state, 'demo')
        state['review_draft'] = 'demo draft'
        state['review_observations'] = {'highlights': 'demo observation'}
        confirm_upload(state, parse_upload(CSV.encode(), 'a.csv'))
        switch_context(state, 'upload')
        self.assertNotIn('review_draft', state)
        state['review_draft'] = 'uploaded draft'
        switch_context(state, 'demo')
        self.assertEqual(state['review_draft'], 'demo draft')
        switch_context(state, 'upload')
        self.assertEqual(state['review_draft'], 'uploaded draft')
        confirm_upload(state, parse_upload(FOLLOWUP.encode(), 'b.csv'))
        self.assertNotIn('review_draft', state)


class UploadPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.working = Path(self.temp.name) / 'working.csv'
        self.draft = Path(self.temp.name) / 'review.md'
        for patcher in [patch.dict(os.environ, {'APP_MODE': 'demo'}),
                        patch('src.followup_store.DEFAULT_WORKING_PATH', self.working),
                        patch('src.review_store.DEFAULT_DRAFT_PATH', self.draft)]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.baseline = DEFAULT_DATA_PATH.read_bytes()

    def app(self):
        return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()

    def confirm(self, app, file):
        with patch('streamlit.file_uploader', return_value=file):
            app.radio(key='data_source').set_value('上传自己的数据').run()
            self.assertFalse(app.exception)
            self.assertFalse(app.metric)
            self.assertEqual(len(app.dataframe[0].value), 2 if file.name == '活动.csv' else 1)
            app.button(key='confirm_upload').click().run()
            self.assertFalse(app.exception)

    def test_csv_preview_confirmation_four_pages_and_separate_visitors(self):
        first, second = self.app(), self.app()
        self.assertEqual(first.radio(key='data_source').value, '使用演示数据')
        self.confirm(first, uploaded())
        self.assertEqual({m.label: m.value for m in first.metric}['报名人数'], '2')
        first.radio(key='page').set_value('活动观察').run()
        self.assertFalse(first.exception)
        self.assertEqual(len(first.get('plotly_chart')), 3)
        first.radio(key='page').set_value('关系跟进').run()
        self.assertFalse(first.exception)
        self.assertTrue(first.info)
        self.assertNotIn('request_restore', [b.key for b in first.button])
        first.radio(key='page').set_value('活动复盘').run()
        first.button(key='generate_review').click().run()
        self.assertIn('2 人报名', first.text_area(key='review_editor').value)
        first.button(key='save_review').click().run()
        self.assertFalse(first.exception)
        self.assertFalse(self.working.exists())
        self.assertFalse(self.draft.exists())
        second.radio(key='page').set_value('活动复盘').run()
        self.assertEqual(second.text_area(key='review_editor').value, '')
        self.assertEqual({m.label: m.value for m in second.metric}['报名人数'], '100')
        self.assertEqual(DEFAULT_DATA_PATH.read_bytes(), self.baseline)

    def test_xlsx_confirmation_is_memory_only_even_in_local_mode(self):
        content = xlsx_bytes([['name', 'role', 'registration_channel', 'attended'],
                              ['上传甲', '创业者', '官网', True]])
        with patch.dict(os.environ, {'APP_MODE': 'local'}):
            app = self.app()
            self.confirm(app, uploaded(content, '活动.xlsx'))
            app.radio(key='page').set_value('活动复盘').run()
            app.button(key='generate_review').click().run()
            app.button(key='save_review').click().run()
            self.assertFalse(app.exception)
        self.assertFalse(self.draft.exists())
        self.assertFalse(self.working.exists())

    def test_failed_or_cancelled_replacement_keeps_confirmed_data(self):
        app = self.app()
        self.confirm(app, uploaded())
        with patch('streamlit.file_uploader', return_value=uploaded(b'bad', 'bad.xlsx')):
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertNotIn('confirm_upload', [b.key for b in app.button])
            self.assertEqual({m.label: m.value for m in app.metric}['报名人数'], '2')
        with patch('streamlit.file_uploader', return_value=uploaded(FOLLOWUP, 'b.csv')):
            app.run()
            self.assertEqual({m.label: m.value for m in app.metric}['报名人数'], '2')
        with patch('streamlit.file_uploader', return_value=None):
            app.run()
            self.assertNotIn('confirm_upload', [b.key for b in app.button])
            self.assertEqual({m.label: m.value for m in app.metric}['报名人数'], '2')

    def test_upload_edit_save_download_and_demo_draft_survive_source_switch(self):
        app = self.app()
        app.radio(key='page').set_value('活动复盘').run()
        app.text_area(key='review_editor').set_value('原来的演示草稿').run()
        app.radio(key='page').set_value('活动总览').run()
        self.confirm(app, uploaded(FOLLOWUP, 'followup.csv'))
        app.radio(key='page').set_value('关系跟进').run()
        key = app.session_state['active_editor_key']
        app.session_state[key] = {'edited_rows': {0: {'当前跟进状态': '待跟进', '跟进负责人': '真实负责人',
                                                      '下一步动作': '约沟通'}},
                                  'added_rows': [], 'deleted_rows': []}
        app.button(key='save_changes').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        app.radio(key='page').set_value('活动总览').run()
        self.assertEqual({m.label: m.value for m in app.metric}['待跟进人数'], '1')
        app.radio(key='page').set_value('活动复盘').run()
        self.assertEqual(app.text_area(key='review_editor').value, '')
        app.text_area(key='review_editor').set_value('上传活动的草稿').run()
        app.radio(key='data_source').set_value('使用演示数据').run()
        self.assertEqual(app.text_area(key='review_editor').value, '原来的演示草稿')
        app.radio(key='data_source').set_value('上传自己的数据').run()
        self.assertEqual(app.text_area(key='review_editor').value, '上传活动的草稿')
        self.assertFalse(self.working.exists())
        self.assertFalse(self.draft.exists())

    def test_invalid_first_upload_shows_friendly_message_without_metrics(self):
        app = self.app()
        with patch('streamlit.file_uploader', return_value=uploaded('姓名\n测试')):
            app.radio(key='data_source').set_value('上传自己的数据').run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertFalse(app.metric)

    def test_two_uploaded_visitors_replacement_and_new_session_reset(self):
        first, second = self.app(), self.app()
        self.confirm(first, uploaded())
        self.confirm(second, uploaded(FOLLOWUP, 'second.csv'))
        first.radio(key='page').set_value('活动复盘').run()
        first.text_area(key='review_highlights').set_value('旧活动观察').run()
        first.text_area(key='review_editor').set_value('旧活动草稿').run()
        first.button(key='save_review').click().run()
        second.radio(key='page').set_value('活动复盘').run()
        self.assertEqual(second.text_area(key='review_editor').value, '')
        self.assertEqual(second.text_area(key='review_highlights').value, '')
        with patch('streamlit.file_uploader', return_value=uploaded(FOLLOWUP, 'new.csv')):
            first.run()
            first.button(key='confirm_upload').click().run()
        self.assertFalse(first.exception)
        self.assertEqual(first.text_area(key='review_editor').value, '')
        self.assertEqual(first.text_area(key='review_highlights').value, '')
        fresh = self.app()
        self.assertEqual({m.label: m.value for m in fresh.metric}['报名人数'], '100')
        self.assertFalse(self.working.exists())
        self.assertFalse(self.draft.exists())


if __name__ == '__main__':
    unittest.main()
