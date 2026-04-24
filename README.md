# Top-View Grounded Height Verification

Top-View Grounded Height Verification studies how vision-language models answer
overall package height from electronic package drawings. It separates low-level
evidence extraction, top-view-grounded height evidence construction, and direct
answer screening so the pipeline can support both engineering work and thesis
writing.

## At a Glance

- 15 package types
- 2 numeric value variants per package
- 30 package drawing images
- 3 Stage 1 evidence acquisition tasks
- 1 Stage 2/3 height verification pipeline
- 3 screening outcomes: `supported`, `contradicted`, and `insufficient_evidence`

## Start Here

- If you want the documentation structure, start at [spec/README.md](spec/README.md).
- If you want the thesis-facing problem statement, start at [spec/paper-intent/paper-statement.md](spec/paper-intent/paper-statement.md).
- If you want current implementation behavior, start with [src/top_view_grounded_height_verification](src/top_view_grounded_height_verification) and [tests](tests).
- If you want generated experiment summaries, start at [experiment_results/README.md](experiment_results/README.md).

## Pipeline Stages

- `direct_extraction`: model-provided package-level dimension answers, including `overall_package_height`
- `dimension_extraction`: OCR dimension values, slot layout, slot assignment, and dimension-line orientation
- `top_view_detection`: top-view slot localization
- `height_evidence`: top-view-grounded construction of supporting, ruled-out, and unresolved dimensions
- `height_screening`: screening of the direct `overall_package_height` answer

## Providers

The Stage 1 runners support `openai`, `gemini`, `anthropic`, and local
`ollama`. Copy `.env.example` to `.env` and fill in the API keys needed for the
selected hosted providers.

For Ollama, start the local API with `ollama serve`, pull a vision-capable
model, then pass `--providers ollama --ollama-model <model>` or set
`OLLAMA_MODEL` in `.env`. The default Ollama base URL is
`http://localhost:11434/api` and can be overridden with `OLLAMA_BASE_URL` or
`--ollama-base-url`.

The project uses `uv` for dependency locking and command execution.

## Repository Map

- `data/`: package drawing images, task cases, prompts, and ground truth
- `src/`: pipeline implementation
- `tests/`: implementation behavior checks
- `spec/`: implementation specs and thesis-facing method notes
- `runs/`: raw Stage 1 runs
- `outputs/`: evidence bundles, verification results, and report artifacts
- `experiment_results/`: manually curated paper-facing summaries

## Dataset Source

The dataset is derived from STEP files obtained from the KiCad 9.x Library
Repositories, specifically the `kicad-packages3D` repository at
https://gitlab.com/kicad/libraries/kicad-packages3D. The selected package models
were imported into Autodesk Fusion to produce the three-view drawings and
dimension annotations used by this benchmark, so the dataset follows the
Creative Commons licensing terms applied to the KiCad library source material.

## License

Except where otherwise noted, this repository is licensed under Creative Commons
Attribution-ShareAlike 4.0 International with the KiCad libraries exception:
`CC-BY-SA-4.0 WITH KiCad-libraries-exception`.

See [LICENSE](LICENSE). Third-party material remains subject to its original
license unless explicitly covered by this repository's license notice.
