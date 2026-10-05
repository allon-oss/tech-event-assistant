"""Catch wrong denominators, silent invalid data, and inconsistent follow-up filters."""
import csv
import hashlib
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from src.data_loader import DataValidationError, load_data, validate_data
from src.metrics import (
    calculate_kpis, channel_performance, field_distribution,
    get_followups, role_distribution,
)

ROOT = Path(__file__).resolve().parents[1]


class DataMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_data()

    def test_demo_unchanged(self):
        digest = hashlib.sha256((ROOT / 'data/demo_tech_event.csv').read_bytes()).hexdigest()
        self.assertEqual(digest, '6bae9989b305c488eecd303cbc7776b3a11d60e7b7ff6f1ab127f4eeb9cea7e3')

    def test_demo_kpis_match_csv(self):
        with (ROOT / 'data/demo_tech_event.csv').open(encoding='utf-8-sig') as f:
            founder_count = sum(r['role'] == '创业者' and r['attended'] == '是' for r in csv.DictReader(f))
        self.assertEqual(calculate_kpis(self.df), {
            'registered': 100, 'attended': 71, 'attendance_rate': .71,
            'attended_founders': founder_count, 'valuable_connections': 22, 'pending_followups': 13,
        })

    def test_kpis_use_input_and_exclude_no_shows_from_value(self):
        sample = self.df.iloc[:3].copy()
        sample['role'] = ['创业者', '投资人', '创业者']
        sample['attended'] = ['是', '是', '否']
        sample['connection_intent'] = ['寻找投资', '行业交流', '寻找投资']
        sample['followup_status'] = ['待跟进', '暂不跟进', '未到场']
        self.assertEqual(calculate_kpis(sample), {
            'registered': 3, 'attended': 2, 'attendance_rate': 2/3,
            'attended_founders': 1, 'valuable_connections': 1, 'pending_followups': 1,
        })

    def test_empty_metrics_safe(self):
        empty = self.df.iloc[:0]
        self.assertTrue(all(v == 0 for v in calculate_kpis(empty).values()))
        self.assertTrue(get_followups(empty).empty)
        self.assertTrue((channel_performance(empty)['attendance_rate'] == 0).all())

    def test_distributions(self):
        self.assertEqual(role_distribution(self.df).set_index('role')['count'].to_dict(),
                         {'创业者':46, '投资人':10, '产业嘉宾':14, '科技从业者':22, '其他':8})
        self.assertEqual(field_distribution(self.df).set_index('field')['count'].to_dict(),
                         {'AI Agent':26, 'AI 应用':22, '企业服务 / SaaS':18, 'Robotics':10, '开发者工具':10, '消费科技':8, '其他':6})
        channels = channel_performance(self.df).set_index('registration_channel')
        for channel, n, arrived in [('社群',40,24), ('朋友推荐',20,17), ('公众号',15,10), ('小红书',10,7), ('合作机构',15,13)]:
            self.assertEqual(channels.loc[channel, 'registered'], n)
            self.assertEqual(channels.loc[channel, 'attended'], arrived)
            self.assertAlmostEqual(channels.loc[channel, 'attendance_rate'], arrived/n)

    def test_followup_sort_filter_and_no_mutation(self):
        before = self.df.copy(deep=True)
        all_rows = get_followups(self.df)
        self.assertEqual(len(all_rows), 22)
        self.assertEqual(all_rows['followup_status'].tolist(),
                         ['待跟进']*13 + ['已初步建联']*4 + ['跟进中']*3 + ['已完成对接']*2)
        self.assertEqual(len(get_followups(self.df, status='待跟进')), 13)
        self.assertEqual(len(get_followups(self.df, owner='')), 2)
        expected = all_rows[(all_rows.role == '创业者') & (all_rows.followup_owner == '景川') & (all_rows.followup_status == '待跟进')]
        pd.testing.assert_frame_equal(get_followups(self.df, status='待跟进', role='创业者', owner='景川'), expected)
        self.assertTrue(get_followups(self.df, role='投资人', owner='Mia').empty)
        pd.testing.assert_frame_equal(self.df, before)

    def test_optional_missing_values_are_blank(self):
        self.assertEqual((self.df.organization == '').sum(), 2)
        self.assertEqual((self.df.notes == '').sum(), 2)
        self.assertFalse(self.df.isna().any().any())

    def test_rejects_bad_core_data(self):
        mutations = [
            ('attendee_id', '', '编号'), ('name', '', '姓名'),
            ('role', '未知身份', 'role'), ('attended', 'maybe', 'attended'),
            ('startup_stage', '未知阶段', 'startup_stage'),
        ]
        for key, value, message in mutations:
            with self.subTest(key=key):
                bad = self.df.copy()
                bad.loc[0, key] = value
                with self.assertRaisesRegex(DataValidationError, message): validate_data(bad)
        bad = self.df.copy()
        bad.loc[1, 'attendee_id'] = bad.loc[0, 'attendee_id']
        with self.assertRaisesRegex(DataValidationError, '重复'): validate_data(bad)
        with self.assertRaisesRegex(DataValidationError, '缺少'): validate_data(self.df.drop(columns=['attended']))

    def test_rejects_contradictory_followup(self):
        bad = self.df.copy()
        idx = bad.index[bad.attended == '否'][0]
        bad.loc[idx, 'followup_status'] = '已完成对接'
        with self.assertRaisesRegex(DataValidationError, '未到场'): validate_data(bad)
        bad = self.df.copy()
        idx = bad.index[bad.followup_status == '待跟进'][0]
        bad.loc[idx, 'followup_owner'] = ''
        with self.assertRaisesRegex(DataValidationError, '负责人'): validate_data(bad)

    def test_friendly_file_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.csv'
            with self.assertRaisesRegex(DataValidationError, '找不到'): load_data(path)
            for payload, message in [(b'', '空'), (b'\xff\xfe\x00', 'UTF-8'), (b'name,name\na,b\n', '重复'), (b'name,role\na,b,c\n', '列数')]:
                path.write_bytes(payload)
                with self.assertRaisesRegex(DataValidationError, message): load_data(path)
            path.write_text(','.join(self.df.columns)+'\n', encoding='utf-8')
            with self.assertRaisesRegex(DataValidationError, '记录'): load_data(path)


if __name__ == '__main__':
    unittest.main()
