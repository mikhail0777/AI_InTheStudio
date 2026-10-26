# LotTrace desktop distribution

LotTrace now has a Windows desktop application shell. It is no longer necessary
for an operator to open a browser or separately start frontend and backend
terminals. The desktop process starts a private loopback API, opens one native
application window, stores data under the Windows application-data directory,
and stops the API when the application exits.

## Development run

```powershell
cd frontend
npm.cmd run desktop:dev
```

This builds the React renderer and starts Electron. Development mode uses the
current Python environment for the backend.

## Windows installer build

```powershell
python -m pip install -r backend/requirements-desktop.txt
npm.cmd --prefix frontend run build
python scripts/build_desktop_backend.py
npm.cmd --prefix frontend run desktop:make
```

The output is produced by Electron Forge with the Squirrel.Windows maker. The
installer must be code-signed before it is distributed to a dealership.

## Security boundaries

- The API listens only on a dynamically selected `127.0.0.1` port.
- Electron renderer Node.js access is disabled.
- Context isolation, renderer sandboxing, and web security are enabled.
- New windows, outside navigation, and renderer permission requests are denied.
- Database, recordings, evidence, and logs live below Electron's per-user
  application-data directory rather than inside the installation folder.
- HTTP responses include CSP, frame, referrer, and MIME-sniffing protections.

## Distribution blockers

The shell and packaging pipeline do not make the current build commercially
deployable by themselves. Before producing the company download:

1. Replace or separately license the research-only make/model checkpoint.
2. Stage every redistributable OCR/detection/model asset in the packaged runtime
   and verify its licence and checksum.
3. Run the packaged backend and installer smoke tests on a clean Windows VM.
4. Configure a Windows code-signing certificate in Electron Forge.
5. Add backup/restore and upgrade/migration acceptance tests.
6. Complete live camera ingestion and the held-out dealership-video benchmark.

Until these are complete, `desktop:dev` is a working desktop prototype and the
installer configuration is a build foundation, not a production-certified
download.
