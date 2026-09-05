# CTERA Operations Proof (offline reference project)

A bounded, offline, public reference project demonstrating CTERA
operations health and backup verification logic. Everything here runs
against explicitly synthetic fixture data that mirrors documented CTERA
SDK field paths. No CTERA Portal, Edge Filer, or cloud service is
contacted, no SDK is installed, and no credentials, accounts, or private
system references appear anywhere in this repository.

Intended use: public MVP / case study / reference example for publication.

## What is demonstrated

Three pure, deterministic checks in `ctera_ops/checks.py`:

1. `fleet_health` - device connectivity posture and firmware parity for
   a fleet of edge filers (offline detection, silent-device detection,
   firmware baseline comparison, stale firmware reports).
2. `backup_freshness` - per backup-folder completion age against a
   folder-group freshness policy (overdue backups, missing completion
   records, groups with no data at all, future timestamps).
3. `portal_database_backup` - portal main database backup to S3:
   enabled flag, valid interval, and current bucket connectivity.

Run it:

```sh
./run_tests.sh            # unittest suite; writes a dated receipt
python3 demo.py           # aggregate summary over the fixtures
```

Run `python3 -m unittest discover -s tests -v` for the current suite. CI runs the tests and synthetic demo.

## Implemented vs vendor-connected (exact gap)

| Layer | Status in this proof | Notes |
|---|---|---|
| Offline check logic (this repo) | Implemented and tested | stdlib only, deterministic checks |
| Synthetic fixtures | Implemented and labeled | `fixtures/*.json` each carry a `schema_note` stating they are synthetic, not CTERA API responses |
| Live CTERA Portal wiring (fleet state, backup completion, DB backup state) | Integration boundary, not exercised | A deployment would fetch this via the documented CTERA Python SDK against a reachable portal. Out of scope for an offline reference proof; no credentials are requested or used |
| Connection-status value vocabulary | Assumption, documented | `deviceConnectionStatus` is a documented retrievable field, but exact runtime enum values should be confirmed against a live portal; checks treat only `connected`/`ok` as healthy |
| Backup completion timestamps from a live portal | Assumption, documented | `lastCompletedBackupUtc` is a declared synthetic extension; a live portal surfaces this data through portal reports or UI rather than the documented SDK include fields used here |

## Mapping from checks to documented CTERA SDK surface

The fixture field paths mirror documented CTERA SDK for Python include
fields where documented. A real adapter must validate field availability, timestamps and value mappings; this is not a drop-in live integration:

- `admin.devices.filers(include=['name', 'portal', 'deviceType', 'owner',
  'deviceConnectionStatus', 'deviceReportedStatus.status.device.runningFirmware'])`
  - connection state, report time, firmware.
- `admin.cloudfs.backups.all()` - backup folder inventory (folder, group,
  owner); completion timestamps would come from a portal report or per
  device state (see gap table).
- `admin.servers.backup.enabled` / `backup.connected()` and
  `Backup.enable(bucket, interval)` - portal main database backup to S3.

## Layout

```
ctera-operations-proof/
  ctera_ops/checks.py        offline check logic (stdlib only)
  fixtures/devices.json      synthetic fleet state
  fixtures/backup_report.json  synthetic backup completion report
  fixtures/portal_backup.json  synthetic portal DB backup state
  tests/test_checks.py       unittest suite (23 tests)
  demo.py                    aggregate summary runner
  run_tests.sh               runs tests, saves receipt
  receipts/                  dated test receipts
  SOURCES.md                 official documentation citations
```

## Scope and safety

- No installs, no cloud calls, no publishing, no account changes.
- Deterministic: fixtures carry their own `as_of` observation time.
- Honest labels: every fixture declares itself synthetic; nothing is
  presented as a captured vendor response.
