# LotTrace clean Windows VM release checklist

Run this checklist on supported clean Windows x64 virtual machines with network
access disabled for the offline-inference phase. Record OS build, VM resources,
artifact SHA-256, operator, timestamps, and pass/fail evidence for every row.

- Verify Authenticode on the installer and packaged executables before launch.
- Install per-user through Squirrel without Python, Node.js, Git, or developer tools.
- Confirm no inbound firewall rule is created and the backend listens only on a
  dynamic `127.0.0.1` port.
- Complete initial administrator setup, sign out, and sign back in.
- Import an existing LotTrace data folder and verify the original remains intact.
- Restart the app and Windows; confirm queued work, camera configuration and data.
- Run the redistributable model checksum gate, disconnect networking, and process
  the approved representative inference fixture.
- Exercise simulated camera normal, disconnect, stall, corrupt-frame, overload,
  concurrent-stream and clean-shutdown cases.
- Create an encrypted backup, alter test data, stage restore, restart, validate the
  restored state and verify the rollback database remains usable.
- Upgrade from the prior signed release, verify the pre-upgrade backup, schema
  version, user data, evidence and audit history; then test rollback without opening
  newer data in an incompatible older binary.
- Exercise malformed configuration, wrong camera credentials, low disk space,
  insufficient permissions, interrupted evidence segment and long-running work.
- Record peak CPU, RAM, GPU/VRAM when applicable, disk growth, queue depth and
  processing latency for the representative workload.
- Uninstall through Windows Apps. Verify binaries are removed and dealership data
  remains unless a separate, explicit data-removal action is chosen.

This checklist cannot be signed off from a developer workstation.
