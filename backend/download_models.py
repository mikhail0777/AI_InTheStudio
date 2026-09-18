"""Explicit model installation. Runtime never downloads or changes detectors."""
from pathlib import Path
import hashlib
import urllib.request

MODEL_URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-seg.pt'
SIGLIP_MODEL_ID = 'google/siglip-base-patch16-224'
SIGLIP_REVISION = '7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed'
SIGLIP_SHA256 = '2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8'
OWLV2_MODEL_ID = 'google/owlv2-base-patch16-ensemble'
OWLV2_REVISION = '410d70ced26e95c344915c2f10f4ecf967f2cde4'
OWLV2_SHA256 = 'e1e130b9e404cf91a75ad45644c1da9d7fa5284085eecc864266a6923efb99e7'


def main():
    destination = Path(__file__).resolve().parent / 'models' / 'yolo11s-seg.pt'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix('.download')
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=60) as source, temporary.open('wb') as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    print(f'Model: {destination}')
    print(f'SHA256: {hashlib.sha256(destination.read_bytes()).hexdigest()}')
    from huggingface_hub import snapshot_download
    snapshot = Path(snapshot_download(
        repo_id=SIGLIP_MODEL_ID, revision=SIGLIP_REVISION,
        allow_patterns=['config.json', 'model.safetensors', 'preprocessor_config.json',
                        'spiece.model', 'tokenizer.json', 'tokenizer_config.json',
                        'special_tokens_map.json'],
    ))
    siglip_weights = snapshot / 'model.safetensors'
    actual_hash = hashlib.sha256(siglip_weights.read_bytes()).hexdigest()
    if actual_hash != SIGLIP_SHA256:
        raise RuntimeError(f'Unexpected SigLIP weight hash: {actual_hash}')
    print(f'Model: {SIGLIP_MODEL_ID}@{SIGLIP_REVISION}')
    print(f'Cache: {snapshot}')
    print(f'SHA256: {actual_hash}')
    owl_destination = Path(__file__).resolve().parent / 'models' / 'owlv2'
    owl_snapshot = Path(snapshot_download(
        repo_id=OWLV2_MODEL_ID, revision=OWLV2_REVISION,
        local_dir=owl_destination,
        allow_patterns=['config.json', 'model.safetensors', 'preprocessor_config.json',
                        'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt',
                        'special_tokens_map.json'],
    ))
    owl_weights = owl_snapshot / 'model.safetensors'
    owl_hash = hashlib.sha256(owl_weights.read_bytes()).hexdigest()
    if owl_hash != OWLV2_SHA256:
        raise RuntimeError(f'Unexpected OWLv2 weight hash: {owl_hash}')
    print(f'Model: {OWLV2_MODEL_ID}@{OWLV2_REVISION}')
    print(f'Cache: {owl_snapshot}')
    print(f'SHA256: {owl_hash}')
    from fast_alpr import ALPR
    plate_reader = ALPR(
        detector_model='yolo-v9-t-384-license-plate-end2end',
        ocr_model='cct-xs-v2-global-model', ocr_device='cpu',
    )
    print(f'Model: {plate_reader.detector.detector.model._model_path}')
    print(f'Model: {plate_reader.ocr.ocr_model.model._model_path}')


if __name__ == '__main__':
    main()
