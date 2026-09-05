#!/usr/bin/env python3
"""Demo: run all CTERA offline operations checks over the synthetic fixtures.

Outputs a JSON summary to stdout. Purely local; no network access.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ctera_ops import checks  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    devices = load("devices.json")
    report = load("backup_report.json")
    portal = load("portal_backup.json")
    policies = {"Finance": 24, "Hr": 24, "Legal": 24, "Lab": 24, "Archive": 48}
    summary = checks.run_all(
        devices["devices"], devices["expected_firmware"], report, policies,
        portal, devices["as_of"])
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
