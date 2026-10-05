"""Exercise the actual Streamlit review workflow using isolated saved files."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from src.followup_store import FollowupStore
from src.metrics import get_followups

ROOT = Path(__file__).resolve().parents[1]


class ReviewPageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.draft_path = Path(temp.name) / 'review.md'
        self.working_path = Path(temp.name) / 'working.csv'
        for target, path in [('src.review_store.DEFAULT_DRAFT_PATH',self.draft_path),
                             ('src.followup_store.DEFAULT_WORKING_PATH',self.working_path)]:
            patcher = patch(target, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def review_app(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
        app.radio(key='page').set_value('活动复盘').run()
        self.assertFalse(app.exception)
        return app

    def test_summary_and_generate_with_observations(self):
        app = self.review_app()
        metrics = {m.label:m.value for m in app.metric}
        self.assertEqual(metrics, {'报名人数':'100','到场人数':'71','到场率':'71%',
                                  '到场创业者人数':'31','明确对接价值人数':'22',
                                  '待跟进':'13','已初步建联':'4','跟进中':'3','已完成对接':'2'})
        app.text_area(key='review_highlights').set_value('模拟验证：交流积极。').run()
        app.text_area(key='review_channel_judgment').set_value('模拟验证：临时取消较多。').run()
        app.button(key='generate_review').click().run()
        self.assertFalse(app.exception)
        draft = app.text_area(key='review_editor').value
        for phrase in ['模拟验证：交流积极。','模拟验证：临时取消较多。','**人工判断 · 渠道**','待跟进 13 人']:
            self.assertIn(phrase, draft)
        self.assertFalse(self.draft_path.exists())

    def test_edit_save_fresh_session_and_export_current_unsaved_text(self):
        app = self.review_app()
        app.button(key='generate_review').click().run()
        edited = app.text_area(key='review_editor').value.replace('## 1. 活动概况', '## 1. 活动概况\n\n人工确认后的措辞。')
        app.text_area(key='review_editor').set_value(edited).run()
        app.button(key='save_review').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(any('当前草稿有未保存' in item.value for item in app.caption))
        self.assertEqual(self.draft_path.read_text(encoding='utf-8'), edited)
        fresh = self.review_app()
        self.assertEqual(fresh.text_area(key='review_editor').value, edited)
        fresh.text_area(key='review_editor').set_value(edited + '\n尚未保存但应导出。').run()
        # Capture the real download component's payload at our UI boundary.
        payloads = []
        original = st.download_button
        def capture(*args, **kwargs):
            if kwargs.get('key') == 'export_review':
                payloads.append(kwargs['data'])
            return original(*args, **kwargs)
        with patch('streamlit.download_button', side_effect=capture):
            fresh.button(key='prepare_review_export').click().run()
        self.assertEqual(payloads[-1].decode('utf-8'), edited + '\n尚未保存但应导出。')
        self.assertEqual(self.draft_path.read_text(encoding='utf-8'), edited)

    def test_export_preparation_collects_last_edit_without_prior_rerun(self):
        app = self.review_app()
        app.button(key='generate_review').click().run()
        app.text_area(key='review_editor').set_value('最后输入的未保存正文')
        payloads = []
        original = st.download_button
        def capture(*args, **kwargs):
            if kwargs.get('key') == 'export_review':
                payloads.append(kwargs['data'])
            return original(*args, **kwargs)
        with patch('streamlit.download_button', side_effect=capture):
            app.button(key='prepare_review_export').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(payloads[-1], '最后输入的未保存正文'.encode('utf-8'))
        self.assertFalse(self.draft_path.exists())

    def test_regenerate_requires_confirmation_and_cancel_preserves_edits(self):
        app = self.review_app()
        app.button(key='generate_review').click().run()
        app.text_area(key='review_editor').set_value('人工编辑不要静默覆盖').run()
        app.button(key='generate_review').click().run()
        self.assertEqual(app.text_area(key='review_editor').value, '人工编辑不要静默覆盖')
        self.assertTrue(app.warning)
        app.button(key='cancel_regenerate_review').click().run()
        self.assertEqual(app.text_area(key='review_editor').value, '人工编辑不要静默覆盖')
        app.button(key='generate_review').click().run()
        app.button(key='confirm_regenerate_review').click().run()
        self.assertIn('100 人报名', app.text_area(key='review_editor').value)

    def test_saved_file_unchanged_by_regeneration_until_save(self):
        self.draft_path.write_text('此前保存的人工稿', encoding='utf-8')
        app = self.review_app()
        app.button(key='generate_review').click().run()
        self.assertEqual(app.text_area(key='review_editor').value, '此前保存的人工稿')
        app.button(key='confirm_regenerate_review').click().run()
        self.assertEqual(self.draft_path.read_text(encoding='utf-8'), '此前保存的人工稿')

    def test_page_switch_preserves_editor_and_human_inputs(self):
        app = self.review_app()
        app.text_area(key='review_problems').set_value('模拟测试：签到排队').run()
        app.button(key='generate_review').click().run()
        app.text_area(key='review_editor').set_value('未保存的人工版本').run()
        app.radio(key='page').set_value('活动观察').run()
        app.radio(key='page').set_value('活动复盘').run()
        self.assertEqual(app.text_area(key='review_editor').value, '未保存的人工版本')
        self.assertEqual(app.text_area(key='review_problems').value, '模拟测试：签到排队')

    def test_working_status_update_is_used_at_confirmation(self):
        app = self.review_app()
        app.button(key='generate_review').click().run()
        app.button(key='generate_review').click().run()
        store = FollowupStore(working_path=self.working_path)
        data, revision = store.load()
        edit = get_followups(data, status='待跟进').iloc[:1].copy()
        edit['followup_status'] = '跟进中'
        store.save_edits(data, edit, revision)
        app.button(key='confirm_regenerate_review').click().run()
        self.assertFalse(app.exception)
        draft = app.text_area(key='review_editor').value
        self.assertIn('待跟进 12 人', draft)
        self.assertIn('跟进中 4 人', draft)
        self.assertEqual({m.label:m.value for m in app.metric}['待跟进'], '12')

    def test_read_error_blocks_overwrite(self):
        self.draft_path.write_bytes(b'\xff\xfe')
        app = self.review_app()
        self.assertTrue(app.error)
        self.assertFalse(app.text_area)
        self.assertEqual(self.draft_path.read_bytes(), b'\xff\xfe')

    def test_save_failure_preserves_editor(self):
        app = self.review_app()
        app.button(key='generate_review').click().run()
        app.text_area(key='review_editor').set_value('人工编辑保留').run()
        with patch('src.review_store.os.replace', side_effect=PermissionError('locked')):
            app.button(key='save_review').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertEqual(app.text_area(key='review_editor').value, '人工编辑保留')
        self.assertFalse(self.draft_path.exists())


if __name__ == '__main__': unittest.main()
