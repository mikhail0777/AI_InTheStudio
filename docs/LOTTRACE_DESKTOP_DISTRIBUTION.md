# LotTrace desktop distribution

> Model packaging gate: `backend/model_bundle_manifest.json` is authoritative.
> The commercial build must fail while any required asset is missing, corrupt,
> or lacks verified redistribution approval. The current research make/model
> checkpoint is never packaged and normal installed operation must not download
> models. Resolve model rights or replace the affected assets before release.

LotTrace now has a Windows desktop application shell. It is no longer necessary
for an operator to open a browser or separately start frontend and backend
terminals. The desktop process starts a private loopback API, opens one native
application window, stores data under the Windows application-data directory,
and stops the API when the application exits.

## Existing accounts and installations

LotTrace accounts are local installation accounts, not cloud accounts. A
configured installation shows returning users the normal email/password sign-in
screen. A fresh desktop installation offers two choices:

- create the first administrator for a genuinely new installation; or
- import an existing LotTrace data folder containing `aerofind.db`.

Import copies the selected database, recordings, evidence, and configuration to
a new timestamped folder under the desktop application's data directory. It
does not overwrite or delete either installation. LotTrace then restarts using
the imported copy and presents the returning-user sign-in screen. Close the
previous LotTrace process before importing so its database is not being written
while the copy is made.

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

Squirrel is intentionally a per-user installation. Application binaries can be
upgraded or uninstalled without deleting the separate Electron user-data folder.
Dealership data removal must remain a distinct, explicit operator action.

For Authenticode signing, set `WINDOWS_CERTIFICATE_FILE` and
`WINDOWS_CERTIFICATE_PASSWORD` only in the secured release environment. An optional
`WINDOWS_TIMESTAMP_SERVER` may override the default. Forge rejects a partial
certificate configuration and signing errors are fatal. After `desktop:make`, run:

```powershell
python scripts/verify_windows_release.py frontend/out/make/squirrel.windows/x64/LotTrace-Setup.exe
```

Never commit the certificate or password. A production certificate was not
available for the current audit, so no signed artifact was created.

The 2026-10-26 packaging verification produced an unsigned 505.4 MB Windows
installer and successfully started its bundled frontend and private backend.
Generated installers remain ignored by Git and must be rebuilt from the pinned
source and dependencies for a release.

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
3. Run the installer and upgrade/rollback tests on a clean Windows VM.
4. Configure a Windows code-signing certificate in Electron Forge.
5. Add backup/restore and upgrade/migration acceptance tests.
6. Complete live camera ingestion and the held-out dealership-video benchmark.

Until these are complete, `desktop:dev` is a working desktop prototype and the
installer configuration is a build foundation, not a production-certified
download.
