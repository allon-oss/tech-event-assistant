"""Verify generation selection without enabling an external service."""
import unittest
from unittest.mock import patch

from src.data_loader import load_data
from src.review_generator import generate_review


class ReviewBackendTests(unittest.TestCase):
    def test_default_and_explicit_template_preserve_facts_and_observations(self):
        data = load_data()
        observations = {'highlights': '现场演示讨论充分'}
        default = generate_review(data, observations)
        explicit = generate_review(data, observations, backend='template')
        self.assertEqual(default, explicit)
        self.assertIn('100 人报名', explicit)
        self.assertIn('实际到场 71 人', explicit)
        self.assertIn('现场演示讨论充分', explicit)

    def test_llm_is_disabled_without_network_access(self):
        data = load_data()
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            with self.assertRaisesRegex(NotImplementedError, '尚未配置.*尚未启用'):
                generate_review(data, {'highlights': '人工观察'}, backend='llm')

    def test_unknown_backend_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '不支持'):
            generate_review(load_data(), backend='unknown')
