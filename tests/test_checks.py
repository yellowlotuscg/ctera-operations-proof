"""Deterministic tests for ctera_ops.checks over synthetic fixtures.

Run from the project root:
    python3 -m unittest discover -s tests -t . -v
"""

import json
import os
import unittest

from ctera_ops import checks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_fixture(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def finding(severity, summary, check=None):
    return [f for f in summary["findings"]
            if f["severity"] == severity
            and (check is None or f["check"] == check)]


class TestFleetHealth(unittest.TestCase):

    def setUp(self):
        self.fixture = load_fixture("devices.json")
        self.as_of = self.fixture["as_of"]
        self.firmware = self.fixture["expected_firmware"]

    def test_healthy_device_passes(self):
        device = self.fixture["devices"][0]  # edge-syd-01
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        self.assertTrue(summary["healthy"])
        self.assertEqual(summary["counters"]["crit"], 0)
        self.assertEqual(finding("warn", summary), [])

    def test_connected_but_silent_device_is_critical(self):
        device = self.fixture["devices"][1]  # edge-nyc-02, silent 40 min
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        self.assertFalse(summary["healthy"])
        hits = finding("crit", summary)
        self.assertEqual(len(hits), 1)
        self.assertIn("40 minutes old", hits[0]["detail"])

    def test_disconnected_device_is_critical(self):
        device = self.fixture["devices"][2]  # edge-lon-03
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        self.assertFalse(summary["healthy"])
        hits = finding("crit", summary)
        self.assertEqual(len(hits), 1)
        self.assertIn("disconnected", hits[0]["detail"])

    def test_firmware_mismatch_is_warning(self):
        device = self.fixture["devices"][3]  # edge-fra-04
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        hits = finding("warn", summary)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["check"], "firmware")
        self.assertIn("!= required", hits[0]["detail"])

    def test_fleet_fixture_finds_expected_issues(self):
        summary = checks.fleet_health(
            self.fixture["devices"], self.firmware, self.as_of)
        self.assertFalse(summary["healthy"])
        crits = [f for f in summary["findings"] if f["severity"] == "crit"]
        self.assertEqual(len(crits), 2)  # silent device, disconnected device
        warns = [f for f in summary["findings"] if f["severity"] == "warn"]
        self.assertEqual(len(warns), 1)  # firmware mismatch

    def test_unknown_connection_status_is_critical(self):
        device = dict(self.fixture["devices"][0])
        device["deviceConnectionStatus"] = "reconnecting"
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        self.assertFalse(summary["healthy"])
        self.assertEqual(len(finding("crit", summary)), 1)

    def test_missing_connection_status_is_warning(self):
        device = dict(self.fixture["devices"][0])
        del device["deviceConnectionStatus"]
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        hits = finding("warn", summary, check="connection")
        self.assertEqual(len(hits), 1)
        self.assertIn("missing", hits[0]["detail"])

    def test_stale_firmware_report_is_warning(self):
        device = dict(self.fixture["devices"][0])
        device["deviceReportedStatus"]["reportedAtUtc"] = "2026-09-01T08:00:00Z"
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        hits = finding("warn", summary)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["check"], "firmware")
        self.assertIn("stale", hits[0]["detail"])

    def test_malformed_as_of_raises(self):
        with self.assertRaises(ValueError):
            checks.fleet_health([], self.firmware, "not-a-timestamp")

    def test_empty_fleet_is_healthy(self):
        summary = checks.fleet_health([], self.firmware, self.as_of)
        self.assertTrue(summary["healthy"])
        self.assertEqual(summary["counters"]["devices"], 0)

    def test_future_report_time_is_tolerated(self):
        device = dict(self.fixture["devices"][0])
        device["deviceReportedStatus"]["lastReportedTimeUtc"] = "2026-09-05T14:30:00Z"
        summary = checks.fleet_health([device], self.firmware, self.as_of)
        self.assertTrue(summary["healthy"])  # age is negative, below threshold


class TestBackupFreshness(unittest.TestCase):

    def setUp(self):
        self.report = load_fixture("backup_report.json")
        self.as_of = self.report["as_of"]
        self.policies = {"Finance": 24, "Hr": 24, "Legal": 24,
                         "Lab": 24, "Archive": 48}

    def test_on_time_backup_passes(self):
        entry = self.report["entries"][0]  # bf-finance, ~5h old
        summary = checks.backup_freshness(
            {"entries": [entry]}, {"Finance": 24}, self.as_of)
        self.assertTrue(summary["healthy"])
        self.assertEqual(summary["counters"]["ok"], 1)

    def test_overdue_backup_is_critical(self):
        entry = self.report["entries"][1]  # bf-hr, ~36h old
        summary = checks.backup_freshness(
            {"entries": [entry]}, {"Hr": 24}, self.as_of)
        self.assertFalse(summary["healthy"])
        hits = finding("crit", summary)
        self.assertEqual(len(hits), 1)
        self.assertIn("36", hits[0]["detail"])

    def test_missing_completion_timestamp_is_critical(self):
        entry = self.report["entries"][2]  # bf-legal, null
        summary = checks.backup_freshness(
            {"entries": [entry]}, {"Legal": 24}, self.as_of)
        self.assertFalse(summary["healthy"])
        self.assertIn("no lastCompletedBackupUtc",
                      finding("crit", summary)[0]["detail"])

    def test_future_completion_timestamp_is_warning(self):
        entry = self.report["entries"][3]  # bf-lab, in the future
        summary = checks.backup_freshness(
            {"entries": [entry]}, {"Lab": 24}, self.as_of)
        hits = finding("warn", summary)
        self.assertEqual(len(hits), 1)
        self.assertIn("future", hits[0]["detail"])

    def test_group_without_entries_is_critical_gap(self):
        summary = checks.backup_freshness(
            {"entries": []}, self.policies, self.as_of)
        crits = finding("crit", summary)
        self.assertEqual(len(crits), len(self.policies))
        self.assertTrue(all("appears in report" in c["detail"] for c in crits))

    def test_unknown_group_without_policy_is_warning(self):
        entry = {"folder": "bf-x", "group": "Mystery",
                 "lastCompletedBackupUtc": "2026-09-05T10:00:00Z"}
        summary = checks.backup_freshness(
            {"entries": [entry]}, self.policies, self.as_of)
        hits = finding("warn", summary)
        self.assertEqual(len(hits), 1)
        self.assertIn("no freshness policy", hits[0]["detail"])

    def test_full_report_matches_expected_counts(self):
        summary = checks.backup_freshness(
            self.report, self.policies, self.as_of)
        self.assertFalse(summary["healthy"])
        self.assertEqual(summary["counters"]["folders"], 4)
        # ok: bf-finance; crit: bf-hr, bf-legal, Archive gap; warn: bf-lab
        self.assertEqual(summary["counters"]["ok"], 1)
        self.assertEqual(summary["counters"]["crit"], 3)
        self.assertEqual(summary["counters"]["warn"], 1)


class TestPortalDatabaseBackup(unittest.TestCase):

    def test_healthy_state_passes(self):
        state = load_fixture("portal_backup.json")
        summary = checks.portal_database_backup(state)
        self.assertTrue(summary["healthy"])
        self.assertEqual(summary["counters"]["ok"], 1)

    def test_disabled_backup_is_critical(self):
        state = {"enabled": False, "connected": True, "intervalMinutes": 60}
        summary = checks.portal_database_backup(state)
        self.assertFalse(summary["healthy"])
        self.assertIn("disabled", finding("crit", summary)[0]["detail"])

    def test_enabled_but_disconnected_is_warning(self):
        state = {"enabled": True, "connected": False, "intervalMinutes": 60}
        summary = checks.portal_database_backup(state)
        hits = finding("warn", summary)
        self.assertEqual(len(hits), 1)
        self.assertIn("not currently connected", hits[0]["detail"])

    def test_missing_interval_is_critical(self):
        state = {"enabled": True, "connected": True, "intervalMinutes": None}
        summary = checks.portal_database_backup(state)
        self.assertFalse(summary["healthy"])
        self.assertIn("intervalMinutes", finding("crit", summary)[0]["detail"])


class TestAggregate(unittest.TestCase):

    def test_run_all_flags_unhealthy_fixture(self):
        devices = load_fixture("devices.json")
        report = load_fixture("backup_report.json")
        portal = load_fixture("portal_backup.json")
        policies = {"Finance": 24, "Hr": 24, "Legal": 24, "Lab": 24, "Archive": 48}
        summary = checks.run_all(
            devices["devices"], devices["expected_firmware"], report, policies,
            portal, devices["as_of"])
        self.assertFalse(summary["healthy"])
        self.assertEqual(summary["checks"],
                         ["fleet_health", "backup_freshness", "portal_database_backup"])
        # Fixture is intentionally unhealthy: fleet and backup findings exist.
        total_crit = sum(r["counters"]["crit"] for r in summary["results"])
        self.assertGreaterEqual(total_crit, 5)


if __name__ == "__main__":
    unittest.main()
