"""Offline operations health checks for a CTERA fleet.

Scope: pure, deterministic logic evaluated over SYNTHETIC fixture data.
This package never talks to a CTERA Portal or Edge Filer. The fixture
schema deliberately mirrors field paths that the official CTERA SDK for
Python documents as retrievable include fields, so the offline checks
can inform a future adapter with explicit field and value validation.

Documented SDK field paths mirrored here (see SOURCES.md for URLs):
- admin.devices.filers(include=['name', 'portal', 'deviceType', 'owner',
  'deviceConnectionStatus', 'deviceReportedStatus.status.device.runningFirmware',
  'deviceReportedStatus.status.agent.details.osName'])
- admin.cloudfs.backups.all()  (portal backup folders)
- admin.servers.backup.connected() / Backup.enable(bucket, interval)
  (portal main database backup to S3)

Any fixture field NOT in that list is a declared synthetic extension used
only for the offline demonstration (for example last backup completion
timestamps, which a live portal would surface through reports or the
portal UI rather than through the include paths listed above).
"""

import datetime as _dt
import re
from typing import Any, Dict, List, Optional, Tuple

UTC = _dt.timezone.utc
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class CheckFinding(object):
    """A single health finding. severity is one of ok, warn, crit."""

    def __init__(self, check: str, target: str, severity: str, detail: str):
        self.check = check
        self.target = target
        self.severity = severity
        self.detail = detail

    def as_dict(self) -> Dict[str, str]:
        return {
            "check": self.check,
            "target": self.target,
            "severity": self.severity,
            "detail": self.detail,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "CheckFinding(%s, %s, %s, %s)" % (
            self.check, self.target, self.severity, self.detail)


def parse_utc(value: Any) -> Optional[_dt.datetime]:
    """Parse an ISO-8601 UTC timestamp (Z or explicit offset) to naive UTC.

    Returns None when the value is missing or malformed so callers can
    emit an explicit finding instead of crashing.
    """
    if not isinstance(value, str) or not _ISO_RE.match(value):
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _field(device: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """Read a dotted path such as deviceReportedStatus.status.device.runningFirmware."""
    node = device
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


CONNECTED_STATES = {"connected", "ok"}


def fleet_health(devices: List[Dict[str, Any]],
                 expected_firmware: Dict[str, str],
                 as_of: str,
                 offline_after_minutes: int = 15,
                 firmware_reported_stale_after_minutes: int = 24 * 60) -> Dict[str, Any]:
    """Evaluate fleet connectivity and firmware posture.

    devices: list of synthetic device records (see fixtures/devices.json).
    expected_firmware: deviceType (for example C200) to required firmware version.
    as_of: ISO-8601 UTC "observation time" carried by the fixture, so every
        run is deterministic without mocking a clock.
    Returns a summary dict with findings and counters.
    """
    now = parse_utc(as_of)
    if now is None:
        raise ValueError("as_of must be an ISO-8601 UTC timestamp")
    findings: List[CheckFinding] = []
    counters = {"devices": len(devices), "ok": 0, "warn": 0, "crit": 0}

    for device in devices:
        name = str(device.get("name", "<unnamed>"))
        dtype = str(_field(device, "deviceType", "unknown"))
        conn_raw = _field(device, "deviceConnectionStatus")
        last_report = parse_utc(_field(device, "deviceReportedStatus.lastReportedTimeUtc"))

        # Check 1: connection state reported by the portal.
        if conn_raw is None:
            findings.append(CheckFinding(
                "connection", name, "warn",
                "deviceConnectionStatus missing in synthetic record"))
        elif str(conn_raw).lower() in CONNECTED_STATES:
            counters["ok"] += 1
            # Check 2: connected devices should still report recently.
            if last_report is not None:
                age_min = (now - last_report).total_seconds() / 60.0
                if age_min > offline_after_minutes:
                    counters["crit"] += 1
                    findings.append(CheckFinding(
                        "connection", name, "crit",
                        "status connected but last report is %.0f minutes old" % age_min))
        else:
            counters["crit"] += 1
            findings.append(CheckFinding(
                "connection", name, "crit",
                "deviceConnectionStatus is %r" % (conn_raw,)))

        # Check 3: firmware parity against the required baseline per model.
        required = expected_firmware.get(dtype)
        firmware = _field(device, "deviceReportedStatus.status.device.runningFirmware")
        reported_at = parse_utc(_field(device, "deviceReportedStatus.reportedAtUtc"))
        if required is None:
            findings.append(CheckFinding(
                "firmware", name, "warn",
                "no baseline defined for deviceType %r; skip parity" % dtype))
        elif firmware is None:
            findings.append(CheckFinding(
                "firmware", name, "warn",
                "runningFirmware not present in synthetic record"))
        else:
            if firmware != required:
                findings.append(CheckFinding(
                    "firmware", name, "warn",
                    "runningFirmware %r != required %r" % (firmware, required)))
            elif reported_at is None or (now - reported_at).total_seconds() > (
                    firmware_reported_stale_after_minutes * 60):
                findings.append(CheckFinding(
                    "firmware", name, "warn",
                    "firmware report is stale (older than %d minutes)"
                    % firmware_reported_stale_after_minutes))
            else:
                counters["ok"] += 1

    # Warning counters count findings, not devices or successful checks.
    counters["warn"] = sum(f.severity == "warn" for f in findings)
    return {
        "check": "fleet_health",
        "as_of": as_of,
        "counters": counters,
        "findings": [f.as_dict() for f in findings],
        "healthy": counters["crit"] == 0,
    }


def backup_freshness(backup_report: Dict[str, Any],
                     policies: Dict[str, int],
                     as_of: str) -> Dict[str, Any]:
    """Evaluate backup freshness from a SYNTHETIC backup report.

    backup_report: fixture with an explicit schema_note declaring it
        synthetic; body holds per-folder completion entries.
    policies: folder group name to target interval in hours.
    as_of: observation time carried by the fixture.
    A completion entry older than its group interval (or missing entirely
    for a folder that has an entry list but no completion in the window)
    is flagged crit. This mirrors the operational question a CTERA admin
    asks about portal backup folders; live wiring would fetch per-device
    sync state or portal reports through a separately validated adapter (outside this example).
    """
    now = parse_utc(as_of)
    if now is None:
        raise ValueError("as_of must be an ISO-8601 UTC timestamp")
    findings: List[CheckFinding] = []
    counters = {"folders": 0, "ok": 0, "warn": 0, "crit": 0}
    entries = backup_report.get("entries", [])
    counters["folders"] = len(entries)

    for entry in entries:
        name = str(entry.get("folder", "<unnamed>"))
        group = str(entry.get("group", ""))
        interval_h = policies.get(group)
        if interval_h is None:
            findings.append(CheckFinding(
                "backup_freshness", name, "warn",
                "no freshness policy for folder group %r" % group))
            counters["warn"] += 1
            continue
        completed_at = parse_utc(entry.get("lastCompletedBackupUtc"))
        if completed_at is None:
            findings.append(CheckFinding(
                "backup_freshness", name, "crit",
                "no lastCompletedBackupUtc in synthetic entry"))
            counters["crit"] += 1
            continue
        age_h = (now - completed_at).total_seconds() / 3600.0
        if age_h < 0:
            findings.append(CheckFinding(
                "backup_freshness", name, "warn",
                "lastCompletedBackupUtc is in the future relative to as_of"))
            counters["warn"] += 1
        elif age_h > interval_h:
            findings.append(CheckFinding(
                "backup_freshness", name, "crit",
                "last backup %.1f hours ago exceeds %d hour policy"
                % (age_h, interval_h)))
            counters["crit"] += 1
        else:
            counters["ok"] += 1

    # Folders tracked in policies but absent from the report count as gaps.
    for group in sorted(policies):
        if group and not any(e.get("group") == group for e in entries):
            findings.append(CheckFinding(
                "backup_freshness", "group:" + group, "crit",
                "policy exists but no folder in group %r appears in report" % group))
            counters["crit"] += 1

    return {
        "check": "backup_freshness",
        "as_of": as_of,
        "counters": counters,
        "findings": [f.as_dict() for f in findings],
        "healthy": counters["crit"] == 0,
    }


def portal_database_backup(portal_state: Dict[str, Any]) -> Dict[str, Any]:
    """Verify portal main database backup configuration and connectivity.

    Mirrors the documented CTERA SDK surface: Backup.enable(bucket, interval)
    and user.servers.backup.connected(). The synthetic state carries
    enabled, connected, targetBucket, intervalMinutes, lastRunUtc.
    """
    findings: List[CheckFinding] = []
    counters = {"checks": 0, "ok": 0, "warn": 0, "crit": 0}
    enabled = bool(portal_state.get("enabled"))
    connected = bool(portal_state.get("connected"))
    interval_min = portal_state.get("intervalMinutes")
    counters["checks"] = 1

    if not enabled:
        findings.append(CheckFinding(
            "portal_db_backup", "main-database", "crit",
            "main database backup to S3 is disabled"))
        counters["crit"] += 1
    elif not isinstance(interval_min, int) or interval_min <= 0:
        findings.append(CheckFinding(
            "portal_db_backup", "main-database", "crit",
            "intervalMinutes missing or non-positive in synthetic state"))
        counters["crit"] += 1
    elif not connected:
        findings.append(CheckFinding(
            "portal_db_backup", "main-database", "warn",
            "backup enabled but S3 bucket not currently connected"))
        counters["warn"] += 1
    else:
        counters["ok"] += 1

    return {
        "check": "portal_database_backup",
        "counters": counters,
        "findings": [f.as_dict() for f in findings],
        "healthy": counters["crit"] == 0,
    }


def run_all(devices, expected_firmware, backup_report, policies,
            portal_state, as_of: str) -> Dict[str, Any]:
    """Run every offline check and produce one aggregate summary."""
    results = [
        fleet_health(devices, expected_firmware, as_of),
        backup_freshness(backup_report, policies, as_of),
        portal_database_backup(portal_state),
    ]
    return {
        "as_of": as_of,
        "checks": [r["check"] for r in results],
        "healthy": all(r["healthy"] for r in results),
        "results": results,
    }
