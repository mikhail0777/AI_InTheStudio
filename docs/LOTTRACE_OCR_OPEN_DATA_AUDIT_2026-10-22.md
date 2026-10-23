# LotTrace OCR open-data and model audit

Date: 2026-10-22

## Outcome

An online search did not find a downloadable, commercially reusable Canadian
or North-American dealership-video dataset that combines full plate
transcriptions, repeated frames/track identity, and a clear commercial-use
licence. Public availability was not treated as permission.

The useful work completed from available sources is:

- downloaded and checksum-verified an Apache-2.0 ONNX recognizer candidate;
- measured it at 180/300 exact (60.00%) on the OpenALPR development split and
  rejected it as a replacement for CCT-S;
- added deterministic synthetic North-American-style OCR training data using
  only explicitly allow-listed DejaVu Sans fonts and a required font licence;
- trained a PARSeq verifier on 2,273 existing real crops plus 5,000 synthetic
  crops;
- measured that verifier at 249/300 exact (83.00%) and 94.96% character
  accuracy on real development images, up from 228/300 (76.00%) for the prior
  PARSeq checkpoint;
- retained CCT-S as the primary crop reader because it remains stronger at
  263/300 exact (87.67%).

Synthetic samples are training augmentation only. They are never included in
an accuracy denominator or presented as real-world evidence.

## Source decisions

| Source | Declared terms | Contents | Decision |
|---|---|---|---|
| [CCPD](https://github.com/detectRecog/CCPD) | MIT; repository explicitly says the dataset is MIT | More than 300,000 Chinese vehicle/plate images with filename-encoded text | Commercially permissive auxiliary source, but not acquired because the roughly 48 GB Chinese-domain corpus is poorly matched to North-American OCR |
| [Indian ANPR OCR corpus](https://huggingface.co/datasets/thundarstrom/indian-anpr-ocr-corpus) | CC BY 4.0 | Card claims 18,537 labelled crops | Rejected: the downloadable repository contained only README and `.gitattributes`, with no images or labels |
| [Open LPR models](https://huggingface.co/faisalthaheem/open-lpr-models) | Apache-2.0 repository; card discloses incomplete upstream recognizer provenance | CPU ONNX PP-OCR recognizer and dictionary | Downloaded, hashed, benchmarked, and rejected at 60.00% exact |
| [Awiros ANPR OCR](https://huggingface.co/Awiros/anpr-ocr) | Apache-2.0 | Indian-specialized PaddleOCR checkpoint; publisher reports 98.42% on its private/held-out Indian distribution | Not promoted: target-domain mismatch, unavailable public validation truth, and no compatible Paddle runtime in the current Python 3.14 environment |
| [0xnu European licence-plate data](https://huggingface.co/datasets/0xnu/european-licence-plate) | Page metadata says Apache-2.0 while the card also says “All Rights Reserved” | 1,975 full vehicle images, no plate transcription field | Rejected for OCR training: contradictory rights language and no text labels |
| [UFPR-ALPR](https://github.com/raysonlaroca/ufpr-alpr-dataset) | Academic research/non-commercial only | 4,500 fully annotated images | Rejected for commercial training |
| [AMLPR](https://www.pinakinathc.me/amlpr/) | Site says non-commercial; annotations alone are CC BY 4.0 | 1,501 crowded-road images and 4,986 plates | Rejected for commercial image training |
| [UCSD/Calit2](https://belongielab.org/car_data) | Access by request; no clear commercial licence on the data page | Approximately 10 hours of video and tracked, transcribed plate sequences | Not acquired; excellent technical fit but commercial reuse is not established |
| [ICPR 2026 LRLPR](https://icpr26lrlpr.github.io/license-agreement.pdf) | Academic, non-commercial only | 20,000 five-frame low/high-resolution plate tracks | Rejected for commercial training |

## Reproducibility and provenance

- Open LPR source revision:
  `faa9540c5cf51dec5e63c6748830d168a844d55b`
- Open LPR OCR ONNX SHA-256:
  `71443c7381a5f851cbec81d1e6557e8b56956078aa503056978852b0cdfc3d60`
- Open LPR dictionary SHA-256:
  `c9007c1e471102735d65ed5e6bf2c197f4c3b926f7005c61143ac9c37c25adce`
- Clean synthetic PARSeq checkpoint SHA-256:
  `01f6b47fd4c2c314298f66b4a0653727ccc3929797b97afda9f4f1115dc06b3f`
- Synthetic seed: `20261022`
- Synthetic font pattern: `DejaVuSans*.ttf`
- The training command requires the local `LICENSE_DEJAVU` file and records its
  resolved path in `training_report.json`.

All downloaded images/models, checkpoints, and detailed predictions remain in
Git-ignored dataset directories. No data was committed or uploaded.

## Remaining evidence gap

Open data can improve character features, but it cannot certify LotTrace on a
dealership entrance. Final event-level proof still requires consented or
customer-owned dealership footage with exact plate strings, vehicle tracks,
gate crossings, timestamps, and multiple frames per vehicle. A synthetic video
can test software behavior, but it cannot establish real event accuracy.

