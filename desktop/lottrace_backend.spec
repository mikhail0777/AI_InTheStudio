# PyInstaller one-folder build for the private desktop API process.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"

datas = []
binaries = []
hiddenimports = []
for package in ("fast_alpr", "onnxruntime", "ultralytics", "transformers"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

yolo = BACKEND / "models" / "yolo11s-seg.pt"
if yolo.is_file():
    datas.append((str(yolo), "models"))

analysis = Analysis(
    [str(BACKEND / "desktop_entry.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="lottrace-backend",
    console=False,
    disable_windowed_traceback=False,
)
bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="lottrace-backend",
)
