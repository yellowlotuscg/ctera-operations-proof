import unittest
from ctera_ops.checks import fleet_health


class CounterIntegrity(unittest.TestCase):
    def test_warning_count_matches_findings(self):
        result = fleet_health([{'name': 'synthetic-edge'}], {}, '2026-09-05T14:00:00Z')
        expected = sum(f['severity'] == 'warn' for f in result['findings'])
        self.assertGreater(expected, 0)
        self.assertEqual(result['counters']['warn'], expected)
