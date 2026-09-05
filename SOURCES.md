# Sources: CTERA operations proof

Primary documentation consulted (official vendor channels), retrieved
2026-09-05. All URLs were fetched and read during research for this proof.

## Official CTERA SDK for Python (published on PyPI, linked from kb.ctera.com)

1. CTERA knowledge base, "The CTERA SDK" (SDK overview, portal and edge
   filer examples, REST-enablement note)
   https://kb.ctera.com/docs/the-ctera-sdk

2. CTERA SDK for Python, "Global Administration" user guide. Documents the
   portal objects and include fields used by this proof:
   - `Devices.filers(include=[...])`, with examples including
     `['owner', 'deviceConnectionStatus']` and nested
     `['deviceReportedStatus.status.device.runningFirmware']` and
     `['deviceReportedStatus.status.agent.details.osName']`
   - `Devices.agents`, `Devices.by_name`, `Devices.get_comment`
   - `Backups.all()` for portal backup folders
   - "Main Database Backup to S3": `Backup.enable(bucket, interval)`,
     `Backup.disable()`, `servers.backup.connected()`
   - `Reports.generate(name)` / `Reports.storage()` report retrieval
   https://ctera-python-sdk.readthedocs.io/en/latest/UserGuides/Portal/Administration.html

3. CTERA SDK for Python, Portal user guide index (Quickstart, Global
   Administration, Services Portal, File Browser)
   https://ctera-python-sdk.readthedocs.io/en/latest/UserGuides/Portal/Index.html

## Notes on what the docs do NOT pin down

- Exact runtime values of `deviceConnectionStatus` are not enumerated on
  the pages above; this proof documents that vocabulary as an assumption
  to confirm against a live portal in a real deployment (integration
  boundary for this offline reference project).
- Completion timestamps for portal backup folder backups are not exposed
  through the documented include paths listed above; the fixture field
  `lastCompletedBackupUtc` is labeled synthetic and would be sourced from
  portal reports or UI state in a live integration.
