"""Pin calculated facts, attribution, edge cases, and privacy boundaries."""
import unittest

from src.data_loader import load_data
from src.review_generator import generate_review, summarize_review


class ReviewGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.data = load_data()

    def test_baseline_summary_and_draft(self):
        summary = summarize_review(self.data)
        self.assertEqual(summary['kpis'], {'registered':100, 'attended':71,
            'attendance_rate':.71, 'attended_founders':31,
            'valuable_connections':22, 'pending_followups':13})
        self.assertEqual(summary['progress'], {'待跟进':13,'已初步建联':4,'跟进中':3,'已完成对接':2})
        self.assertEqual(summary['roles'].set_index('role').loc['创业者', 'share'], .46)
        self.assertEqual(summary['top_fields']['field'].tolist(), ['AI Agent','AI 应用','企业服务 / SaaS'])
        self.assertEqual(summary['most_registered'], ['社群'])
        self.assertEqual(summary['highest_attendance'], ['合作机构'])
        self.assertEqual(summary['lowest_attendance'], ['社群'])
        draft = generate_review(self.data)
        for fact in ['100 人报名','实际到场 71 人','71%','创业者 31 人',
                     '创业者 46 人（46%）','社群：报名 40 人，到场 24 人，到场率 60%',
                     '合作机构：报名 15 人，到场 13 人，到场率 86.7%',
                     'AI Agent 26 人','明确对接价值的对象共 22 人','待跟进 13 人']:
            self.assertIn(fact, draft)
        self.assertEqual(draft.count('\n## '), 5)

    def test_changes_are_calculated_and_no_personal_fields_leak(self):
        changed = self.data.iloc[:3].copy()
        changed['name'] = '隐私姓名不要输出'
        changed['organization'] = '私密机构不要输出'
        changed['notes'] = '私密备注不要输出'
        changed['next_action'] = '联系私人电话123456'
        changed['attended'] = '是'
        changed['role'] = '投资人'
        changed['connection_intent'] = '寻找创业者'
        changed['followup_status'] = ['待跟进','跟进中','暂不跟进']
        draft = generate_review(changed)
        for fact in ['3 人报名','实际到场 3 人','100%','投资人 3 人','待跟进 1 人', '暂不跟进 1 人']:
            self.assertIn(fact, draft)
        for private in ['隐私姓名','私密机构','私密备注','123456','100 人报名','13 人']:
            self.assertNotIn(private, draft)

    def test_observations_are_preserved_and_attributed(self):
        observations = {'highlights':'模拟测试：问答交流充分。',
            'problems':'模拟测试：签到等待较久。',
            'channel_judgment':'模拟测试：社群临时取消较多。',
            'key_relationships':'模拟测试：关注两个 SaaS 合作意向。',
            'improvements':'模拟测试：提前准备签到名单。\n模拟测试：延长交流时间。'}
        draft = generate_review(self.data, observations)
        for value in observations.values():
            self.assertIn(value, draft)
        self.assertIn('**人工判断 · 渠道**', draft)
        self.assertIn('**人工补充 · 重点关系**', draft)
        self.assertIn('**人工建议**', draft)
        # Causal judgments absent from human input must not be generated.
        for claim in ['质量差','意愿不强','因为','不受欢迎','取消社群']:
            self.assertNotIn(claim, generate_review(self.data))

    def test_empty_observations_do_not_invent_events(self):
        draft = generate_review(self.data, {'highlights':'  ', 'problems':''})
        self.assertEqual(draft.count('暂无人工补充'), 1)
        self.assertNotIn('签到等待', draft)
        self.assertNotIn('现场氛围', draft)
        self.assertNotIn('**人工判断 · 渠道**', draft)

    def test_ties_and_zero_registration_channels(self):
        data = self.data.iloc[:4].copy()
        data['registration_channel'] = ['社群','社群','朋友推荐','朋友推荐']
        data['attended'] = ['是','否','是','否']
        summary = summarize_review(data)
        for key in ['most_registered','highest_attendance','lowest_attendance']:
            self.assertEqual(summary[key], ['社群','朋友推荐'])
        self.assertNotIn('公众号', summary['lowest_attendance'])
        self.assertIn('并列', generate_review(data))

    def test_no_attendance_or_registrations(self):
        data = self.data.copy()
        data['attended'] = '否'
        draft = generate_review(data)
        self.assertIn('实际到场 0 人', draft)
        self.assertIn('暂无到场人员', draft)
        self.assertNotIn('创业者 0 人，是', draft)
        self.assertNotIn('优先完成剩余 0', draft)
        empty = generate_review(data.iloc[:0])
        self.assertIn('0 人报名', empty)
        self.assertNotIn('nan', empty.lower())
        self.assertNotIn('到场率最低的渠道', empty)


if __name__ == '__main__': unittest.main()
