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

manifest = BACKEND / "model_bundle_manifest.json"
datas.append((str(manifest), "."))
# Model binaries are added only after the manifest records approved commercial
# redistribution. Research checkpoints and developer caches never enter COLLECT.
model_manifest = __import__("json").loads(manifest.read_text(encoding="utf-8"))
for asset in model_manifest["assets"]:
    if asset.get("package") and asset.get("redistribution_status") in ("approved", "permitted"):
        source = BACKEND / asset["expected_installed_path"]
        if source.is_file(): datas.append((str(source), str(Path(asset["expected_installed_path"]).parent)))

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
