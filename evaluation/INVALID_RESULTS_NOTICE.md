# Invalid superseded evaluation artifacts

Do not use these files as evidence:

- `uc3m_alpr_full_frame_all.json`
- `uc3m_alpr_production_test_dedup.json`

They were generated before discovery that UC3M-LP's embedded `imagePath` values are systematically offset by one annotation. The corrected evaluator pairs same-stem JPG/JSON sidecars, matching the dataset's documented directory convention. Valid replacements are `uc3m_alpr_production_all.json` and `uc3m_alpr_production_test.json`.

The invalid artifacts are retained only because this controlled rebuild prohibits deleting existing work without explicit approval.
