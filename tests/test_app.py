"""Exercise rendered KPIs, page routing, chart traces, and filter intersections."""
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.data_loader import load_data
from src.metrics import channel_performance, field_distribution, role_distribution
from src.visualizations import channel_chart, field_chart, role_chart

ROOT = Path(__file__).resolve().parents[1]


class ChartTests(unittest.TestCase):
    def test_trace_values_match_demo(self):
        df = load_data()
        roles = role_chart(role_distribution(df))
        self.assertEqual(dict(zip(roles.data[0].y, roles.data[0].x)),
                         {'创业者':46, '投资人':10, '产业嘉宾':14, '科技从业者':22, '其他':8})
        fields = field_chart(field_distribution(df))
        self.assertEqual(dict(zip(fields.data[0].y, fields.data[0].x)),
                         {'AI Agent':26, 'AI 应用':22, '企业服务 / SaaS':18, 'Robotics':10, '开发者工具':10, '消费科技':8, '其他':6})
        channels = channel_chart(channel_performance(df))
        self.assertEqual(list(channels.data[0].y), [40,20,15,10,15])
        for actual, expected in zip(channels.data[1].y, [.6,.85,10/15,.7,13/15]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(channels.data[1].yaxis, 'y2')
        self.assertEqual(tuple(channels.layout.yaxis2.range), (0, 1))


class AppTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.working = Path(temporary.name) / 'working.csv'
        patched = patch('src.followup_store.DEFAULT_WORKING_PATH', self.working)
        patched.start()
        self.addCleanup(patched.stop)

    def new_app(self):
        return AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()

    def test_overview_kpis(self):
        app = self.new_app()
        self.assertFalse(app.exception)
        metrics = {m.label:m.value for m in app.metric}
        self.assertEqual(metrics['报名人数'], '100')
        self.assertEqual(metrics['到场人数'], '71')
        self.assertEqual(metrics['到场率'], '71%')
        self.assertEqual(metrics['明确对接价值人数'], '22')
        self.assertEqual(metrics['待跟进人数'], '13')
        self.assertEqual(len(metrics), 6)

    def test_observation_page_has_only_three_charts(self):
        app = self.new_app()
        app.radio(key='page').set_value('活动观察').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('plotly_chart')), 3)

    def test_owner_uses_fictional_display_name_and_filters_correctly(self):
        app = self.new_app()
        app.radio(key='page').set_value('关系跟进').run()
        self.assertIn('林舟', app.selectbox(key='owner_filter').options)
        self.assertNotIn('景川', app.selectbox(key='owner_filter').options)
        self.assertNotIn('景川', app.dataframe[0].value['跟进负责人'].tolist())
        app.selectbox(key='owner_filter').set_value('景川').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 9)
        self.assertTrue((app.dataframe[0].value['跟进负责人']=='林舟').all())

    def test_followup_controls_and_empty_combination(self):
        app = self.new_app()
        app.radio(key='page').set_value('关系跟进').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 22)
        self.assertEqual(app.dataframe[0].value.iloc[0]['当前跟进状态'], '待跟进')
        self.assertEqual(list(app.dataframe[0].value.columns),
                         ['报名编号','姓名','身份','公司 / 项目','方向','对接意向','当前跟进状态','跟进负责人','下一步动作','备注'])
        app.selectbox(key='status_filter').set_value('待跟进').run()
        self.assertEqual(len(app.dataframe[0].value), 13)
        app.selectbox(key='role_filter').set_value('投资人').run()
        self.assertTrue((app.dataframe[0].value['身份']=='投资人').all())
        app.selectbox(key='owner_filter').set_value('Mia').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 0)
        self.assertTrue(any('没有符合' in item.value for item in app.info))
        app.selectbox(key='status_filter').set_value('全部').run()
        app.selectbox(key='role_filter').set_value('全部').run()
        app.selectbox(key='owner_filter').set_value('无当前负责人').run()
        self.assertEqual(len(app.dataframe[0].value), 2)
        self.assertTrue((app.dataframe[0].value['当前跟进状态']=='已完成对接').all())
        app.selectbox(key='owner_filter').set_value('全部').run()
        self.assertEqual(len(app.dataframe[0].value), 22)
        app.radio(key='page').set_value('活动总览').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 6)

    def test_edit_save_new_session_kpis_export_and_confirmed_restore(self):
        app = self.new_app()
        app.radio(key='page').set_value('关系跟进').run()
        self.assertEqual({m.label:m.value for m in app.metric},
                         {'待跟进':'13','已初步建联':'4','跟进中':'3','已完成对接':'2'})
        key = app.session_state['active_editor_key']
        app.session_state[key] = {'edited_rows':{0:{'当前跟进状态':'跟进中', '跟进负责人':'Mia',
                                                   '下一步动作':'约线上沟通', '备注':'V02测试'}},
                                  'added_rows':[], 'deleted_rows':[]}
        app.button(key='save_changes').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(self.working.exists())
        self.assertTrue(any('已保存' in m.value for m in app.success))
        fresh = self.new_app()
        self.assertEqual({m.label:m.value for m in fresh.metric}['待跟进人数'],'12')
        fresh.radio(key='page').set_value('关系跟进').run()
        self.assertEqual({m.label:m.value for m in fresh.metric}['跟进中'],'4')
        self.assertIn('约线上沟通',fresh.dataframe[0].value['下一步动作'].tolist())
        fresh.button(key='request_restore').click().run()
        self.assertTrue(self.working.exists())
        fresh.button(key='cancel_restore').click().run()
        self.assertTrue(self.working.exists())
        fresh.button(key='request_restore').click().run()
        fresh.button(key='confirm_restore').click().run()
        self.assertFalse(fresh.exception)
        self.assertFalse(self.working.exists())
        self.assertEqual({m.label:m.value for m in fresh.metric}['待跟进'],'13')
        self.assertNotIn('约线上沟通',fresh.dataframe[0].value['下一步动作'].tolist())

    def test_illegal_editor_changes_show_error_without_file(self):
        app = self.new_app()
        app.radio(key='page').set_value('关系跟进').run()
        key = app.session_state['active_editor_key']
        app.session_state[key] = {'edited_rows':{0:{'跟进负责人':''}},'added_rows':[], 'deleted_rows':[]}
        app.button(key='save_changes').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse(self.working.exists())


if __name__ == '__main__':
    unittest.main()
