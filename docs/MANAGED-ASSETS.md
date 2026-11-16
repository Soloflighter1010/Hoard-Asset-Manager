# Managed project updates

Each listed project can opt into **Packages only**, **Assets only**, or **Assets
and packages**. **Off** is the default. The choice is saved in Hoard's own project
state, not in shared project files. Disabling it prevents queued project updates
from applying changes.

While Hoard runs, the shared scheduler checks opted-in projects hourly. It yields
to existing work and defers while Unity has a project open. For store assets it
queues a check, downloads changed products, and only then queues project changes.
Failed or interrupted checks/downloads prevent the project step. All work appears
in Tasks. Package updates refresh repositories, resolve upgrades, reject conflicts,
and use the existing transactional apply and read-back verification.

## Imported assets

New preloads record GUID, path, source product key and SHA-256 hashes of both the
asset and its metadata in `ProjectSettings/Hoard/managed-assets.json`. Hashes are
calculated from staged package content before files are moved into place.

Updates replace only files from that source with matching paths and unchanged
content/metadata. Existing project files are never adopted just because their
GUID or path matches. Local edits and moved/untracked files are left unchanged.
A file without metadata still occupies its path and is never overwritten.

A journal and original copies support rollback after a failed replacement and
recovery after interruption. Recovery refuses to overwrite later local edits.
Incoming metadata must retain its GUID. Unity is checked before staging and again
before replacement. Transactions are per package, not across the whole project.
Completed package changes can remain if a later product needs manual review;
Tasks records each completed step and the error.

## Changes requiring manual review

- Old imports are adopted only when their asset and metadata bytes exactly match
  the selected package. Different or modified files need manual review.
- A package introducing new assets is not partially applied: import it manually
  to review the additions first. Removed package assets are retained.
- Renamed or missing package files need their replacement selected manually.
- VPM packages imported directly from product archives/folders are not managed
  asset replacements; repository-installed VPM packages use the package updater.
- Local edits, unsupported files and missing downloads are reported as unchanged
  or as failures. Hoard does not claim it updated those entries.

Automatic updates are opt-in. Keep independent project backups for historical
recovery; the replacement journal is only for interrupted work, not long-term
version history.
