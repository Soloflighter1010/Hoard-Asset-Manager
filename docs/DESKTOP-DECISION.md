# Desktop packaging evidence and decision

For #324, keep the existing pywebview shell and release pipelines while the
Tauri/Nuitka experiment is evaluated. Published download sizes and antivirus
results alone do not establish startup, memory use, reliability or maintenance
cost. There is one shipping shell on this branch; the experimental workflow is
on its separate experiment branch. Windows signing remains in place. macOS
Developer ID signing and notarization are deferred at the maintainer's request.

## Evidence available on 9 November 2026

The usual [5.2.0-beta.4 release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/tag/v5.2.0-beta.4)
was published on 5 November, followed by [tauri-nuitka-beta.2](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/tag/tauri-nuitka-beta.2)
that day. The experiment describes the same Hoard version with a different shell
and Python packaging. Exact asset URLs, SHA-256 digests, bytes and published scan
counts are in [the evidence snapshot](measurements/desktop-2026-11-09.json).
Unmeasured fields are `null`, never zero.

| Platform | Usual download, bytes | Experimental download, bytes |
| --- | ---: | ---: |
| Windows installer | 58,468,680 | 52,140,928 |
| macOS Apple silicon | 77,223,873 (.pkg) | 79,912,114 (.dmg) |
| macOS Intel | 79,213,154 (.pkg) | 84,172,333 (.dmg) |
| Linux | 40,837,352 (Flatpak) | 110,872,102 (.deb); 176,523,768 (AppImage) |

The experimental Windows download is 10.82% smaller. Package formats, bundled
runtimes and compression differ, especially on Linux; these are transfer sizes,
not installed footprint measurements. The published VirusTotal summaries report
zero malicious and zero suspicious detections for each desktop artifact, with
59–67 engines. They are historical release snapshots, not fresh scans or a reason
to assume equivalent behavior on a user's machine.

#313's report says project dragging worked in the regular beta while assets did
not. `shared.js` now supplies a pointer-based fallback for product and project
dragging, including cancellation, drop feedback and suppression of the following
click. Browser regression tests disable native drag-start and exercise the
fallback. This still requires confirmation in actual WebView2 and WebKit windows.

## Remaining comparison protocol

Use separate disposable OS accounts or snapshots for the two builds: both use
the same app-data directory, and only one instance may run. Keep the same OS,
architecture, hardware, display scale and WebView/runtime version. Record the
release tag and asset digest, plus whether prerequisite runtimes were already
installed. Do not compare one build's first-time migration with the other's
already-migrated home.

For Windows, Linux and each available Mac architecture:

1. Measure installed app bytes and separately the extra runtime download/install
   bytes. For Flatpak, record shared runtime size and the incremental app size.
2. Record five cold launches from fresh OS sessions and five warm launches after
   quitting fully. Time from launch to the first interactive library tile; also
   record when the local server becomes ready. Report samples and median.
3. Repeat with the same synthetic 50,000-product library, generated from the
   fixture in `scripts/benchmark_storage.py`. Include notes, tags and marks, use
   local placeholder pictures, and record data-generation/migration separately.
4. At first interactive tile and after 30 seconds idle, record memory for the
   entire process tree, including the backend and WebView workers. Record peak
   memory during loading. Name the OS counter (RSS, working set or physical
   footprint); do not silently compare unlike counters.
5. Exercise product-to-product, product-to-set, project-to-project and
   project-to-folder drops, multiple selection and Escape cancellation. Check
   native folder/file pickers, close/reopen, updater handoff and offline startup.
6. Record the published or newly authorized antivirus report by artifact digest,
   engine counts and scan date. Keep tester observations beside measured values.

The Linux development environment used for this change has exercised Chromium
browser tests and Python/C# code; it has not supplied these native cross-OS
measurements or tester reports. #324 therefore remains open for those results
and the final packaging choice. A smaller installer alone does not justify
switching all users to a second shell implementation.
