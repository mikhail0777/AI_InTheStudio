# PyInstaller one-folder build for the private desktop API process.
from pathlib import Path

ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"

datas = []
binaries = []
hiddenimports = [
    "fast_alpr",
    "fast_alpr.default_detector",
    "fast_alpr.default_ocr",
]

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
    # These belong to the retired general-purpose visual-search workflow. The
    # LotTrace desktop runtime uses YOLO/ONNX inference and should not ship the
    # entire Hugging Face training/conversion stack.
    excludes=["transformers", "datasets", "nltk", "tkinter"],
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
