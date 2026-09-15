"""Explicit model installation. Runtime never downloads or changes detectors."""
from pathlib import Path
import hashlib
import urllib.request

MODEL_URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-seg.pt'


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


if __name__ == '__main__':
    main()
