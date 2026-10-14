# CTERA Operations Proof

Offline Python checks for CTERA fleet health and backup freshness. They
run on the JSON fixtures in this repository. The fixtures are invented
records shaped like CTERA portal data, and each file says so in
`schema_note`. The checks are plain Python, with no SDK dependency.
Running them does not contact a CTERA Portal, an Edge Filer, or any
other network service, and the repository holds no credentials.

This is a public reference: a small, tested example, with the boundary
to a live portal written down in `SOURCES.md`.

## Get the code

```sh
git clone https://github.com/yellowlotuscg/ctera-operations-proof.git
cd ctera-operations-proof
```

## Run

`./run_tests.sh` can be started from any working directory. It moves to
the repository root, runs the unittest suite, and saves a timestamped
log under `receipts/`.

From the repository root:

```sh
./run_tests.sh
python3 demo.py
python3 -m unittest discover -s tests -v
```

`python3 demo.py` loads the three fixtures and prints one JSON summary.
The summary clock is `as_of` from `fixtures/devices.json`. The backup
fixture stores the same timestamp. The folder-group policies are
hardcoded in `demo.py`: Finance, Hr, Legal, and Lab at 24 hours, Archive
at 48 hours.

GitHub Actions (`.github/workflows/tests.yml`) uses Python 3.12 and runs:

```sh
python -m unittest discover -s tests -v
python demo.py
```

The suite is 24 tests: 23 in `tests/test_checks.py` and 1 in
`tests/test_counter_integrity.py`. The saved log
`receipts/test_run_20260905T153150Z.txt` is from an earlier run. It
records 23 tests on Python 3.9.6.

## The three checks

All three are in `ctera_ops/checks.py` and use the Python standard
library. `run_all` calls them in this order: `fleet_health`,
`backup_freshness`, `portal_database_backup`. A result is healthy when
its critical count is zero. Warning findings are still included.

### `fleet_health`

Inputs are the device list, `expected_firmware` (device model to
required version), and `as_of`. `as_of` has to be an ISO-8601 timestamp
with `Z` or a numeric offset. Any other value raises `ValueError`.

Connection status is compared in lowercase:

- `connected` or `ok` counts as up. If
  `deviceReportedStatus.lastReportedTimeUtc` is more than 15 minutes
  before `as_of`, that is a critical finding: the portal still says
  connected, and the device has gone quiet. A report time later than
  `as_of` is accepted. A connected device with no parseable report time
  gets no quiet-device finding.
- Any other status value is critical.
- A missing `deviceConnectionStatus` is a warning.

Firmware is evaluated for every device:

- No baseline for that `deviceType`: warning.
- Missing `deviceReportedStatus.status.device.runningFirmware`: warning.
- Firmware present and different from the baseline: warning.
- Firmware matches, and `deviceReportedStatus.reportedAtUtc` is missing
  or more than 24 hours before `as_of`: warning. A firmware report time
  later than `as_of` is accepted.

On the included fleet fixture the check is unhealthy. `edge-nyc-02` is
connected with a report 40 minutes old, `edge-lon-03` is
`disconnected`, and `edge-fra-04` has a firmware warning.

### `backup_freshness`

Inputs are the backup report, a map of folder group to maximum age in
hours, and `as_of`. `as_of` follows the same timestamp rule as fleet
health.

For each entry the check reads `folder`, `group`, and
`lastCompletedBackupUtc`:

- No policy for that group: warning. Age is left unevaluated.
- Missing or unparseable `lastCompletedBackupUtc`: critical.
- Completion time later than `as_of`: warning.
- Age greater than the group policy: critical.
- Age within the policy: ok.

After the entries, each policy group that has no row in the report is a
critical finding. The included report has no Archive folder, so that
group is one of those findings. The included report also flags `bf-hr`
as overdue, `bf-legal` as missing a completion time, and `bf-lab` as a
future timestamp. `bf-finance` is within 24 hours.

### `portal_database_backup`

This check reads `enabled`, `intervalMinutes`, and `connected` from
`fixtures/portal_backup.json`. It stops at the first failing condition:

- `enabled` missing or false: critical.
- `intervalMinutes` missing, or not an int greater than zero: critical.
- `connected` missing or false: warning. The result stays healthy,
  because the critical count is still zero.
- Enabled, a positive interval, and connected: ok.

The included portal fixture takes the last path. `targetBucket` and
`lastRunUtc` are in the file and are not read.

On these fixtures, `python3 demo.py` reports `"healthy": false`. Fleet
health and backup freshness both have critical findings. Portal
database backup is healthy.

## Live portal boundary

| Piece | In this repository | Against a live portal |
|---|---|---|
| Check logic | `ctera_ops/checks.py`, covered by the unittest suite | The same functions, fed by data fetched elsewhere |
| Fixtures | `fixtures/*.json`, each labeled synthetic in `schema_note` | A query against a portal you can reach |
| SDK calls | Described below, and not executed | CTERA SDK for Python. This repository does not ask for or store credentials |
| `deviceConnectionStatus` | `connected` and `ok` count as up | The field is documented as retrievable. The guide does not list the runtime values, so a deployment still has to confirm them |
| Backup completion time | `lastCompletedBackupUtc` on each fixture entry | A portal report or the portal UI. It is not one of the documented `Backups.all()` include fields |

## Field paths

The global administration guide linked from `SOURCES.md` documents these
calls:

- `admin.devices.filers(...)`. The default include is `name`, `portal`,
  and `deviceType`. The guide's examples also request `owner`,
  `deviceConnectionStatus`, and
  `deviceReportedStatus.status.device.runningFirmware`.
- `admin.cloudfs.backups.all()`. The guide's default include is `name`,
  `group`, and `owner`. Fixture entries use `folder` as the folder
  label. The freshness check reads `folder` and `group`. `owner` is
  stored on the entry and is unused by the check.
- `user.servers.backup.enable(bucket, interval)` and
  `user.servers.backup.connected()`, for the portal main database
  backup to S3. The interval argument is minutes.

The fixtures also carry fields those calls do not document, because the
checks need a clock and a completion time:
`deviceReportedStatus.lastReportedTimeUtc`,
`deviceReportedStatus.reportedAtUtc`, and `lastCompletedBackupUtc`.

Two comments in `ctera_ops/checks.py` disagree with each other, and one
disagrees with the guide. The function comment says
`user.servers.backup.connected()`, which matches the guide. The module
comment says `admin.servers.backup.connected()`, and it lists
`deviceReportedStatus.status.agent.details.osName` on `filers`. The
guide shows that `osName` path on `admin.devices.agents`. These checks
never call the SDK. `osName` is unused.

## Layout

```
ctera-operations-proof/
  ctera_ops/__init__.py
  ctera_ops/checks.py
  fixtures/devices.json
  fixtures/backup_report.json
  fixtures/portal_backup.json
  tests/test_checks.py
  tests/test_counter_integrity.py
  demo.py
  run_tests.sh
  receipts/
  SOURCES.md
  .github/workflows/tests.yml
  LICENSE
```

## License

MIT. Copyright (c) 2026 Matthew Coggins. See `LICENSE`.
