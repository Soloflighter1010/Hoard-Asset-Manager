# Managed asset update groundwork

Issue #357 remains incomplete: this change does not schedule or enable automatic
project updates.

When Hoard imports new files from a Unity package through project preload, it now
records each file's GUID, path, source product key and SHA-256 hashes of both the
asset and its metadata in `ProjectSettings/Hoard/managed-assets.json`. Hashes are
calculated from the package's staged content before files are moved into place,
so a later edit cannot accidentally become the imported baseline.

Existing project files are never adopted just because they share a GUID or path.
Files without metadata still occupy their paths and are left unchanged. Folders
and packages outside Assets are not tracked for managed replacement. Invalid
records and paths through symbolic links are excluded; both asset and metadata
must match the recorded hashes before an asset qualifies as unchanged.

The next steps are transactional replacement with interruption recovery, download
coordination, per-project opt-in choices and scheduling that defers while Unity
is open. Until those are implemented and tested, no automated replacement uses
this record. Old imports without a baseline require a deliberate migration flow;
they cannot be assumed unchanged.
