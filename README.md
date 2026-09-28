# eo-workflow-lint

A deterministic, offline static analyzer for scientifically unsafe Earth observation workflows.

`eo-workflow-lint` reads Google Earth Engine **Python** source files and reports a narrow,
documented set of workflow patterns that Earth Engine will happily execute but that conflict
with the published semantics of the underlying Earth-observation product — unscaled Landsat
Collection 2 surface reflectance, a second dB conversion on already-log-scaled Sentinel-1 GRD,
region reductions with an implicit analysis scale, and Sentinel-2 `QA60` use inside the
documented availability gap.

It is a linter, not an assistant. It never runs your code, never contacts a network, and never
needs Earth Engine credentials.

- Version: **0.2.1**
- Specification: [`SPECIFICATION.md`](SPECIFICATION.md) v0.2.1 (frozen for the 0.2.x series)
- JSON report `schema_version`: `0.2`
- Catalog version: `2026-09-22.1`
- Reason codes: 7 (unchanged since v0.1.0)
- Real-world validation: [`docs/real-world-validation.md`](docs/real-world-validation.md)
- Python: 3.11+
- Runtime dependencies: none (standard library only)
- License: Apache-2.0

## What PASS means

> `eo-workflow-lint` detects only a narrow set of documented Earth-observation workflow
> anti-patterns. **PASS** means that no supported rule produced a finding in the
> statically resolved portion of the source. PASS does **not** prove that the workflow,
> analysis, model, or conclusion is scientifically correct.

Every report includes analysis-coverage counters so you can see how much of the source the
analyzer was actually able to resolve. Unresolved code is reported as coverage, never converted
into a scientific verdict — there is no `UNKNOWN` verdict.

## Install

Python 3.11 or newer. `eo-workflow-lint` has no runtime dependencies.

**Install a tagged release directly from GitHub** (tags are listed on the
[Releases](https://github.com/orbseekr-labs/eo-workflow-lint/releases) page; this README
describes v0.2.1):

```bash
pip install "git+https://github.com/orbseekr-labs/eo-workflow-lint.git@v0.2.1"
```

**Or install from a local clone**, which you will want if you intend to run the tests or read the
specification alongside the code:

```bash
git clone https://github.com/orbseekr-labs/eo-workflow-lint.git
cd eo-workflow-lint
pip install .
```

Either method installs the `eo-workflow-lint` command. The package is not published on PyPI.

## Usage

```bash
eo-workflow-lint check workflow.py
eo-workflow-lint check workflow.py --format json
eo-workflow-lint check workflow.py --fail-on conditional

eo-workflow-lint rules              # list the reason codes
eo-workflow-lint explain EWL301     # explain one reason code
eo-workflow-lint sources            # show the bundled catalog source registry
eo-workflow-lint --version
```

Example:

```console
$ eo-workflow-lint check examples/sentinel1_double_db.py
FAIL
file: examples/sentinel1_double_db.py

EWL301 SENTINEL1_GRD_REDUNDANT_DB_CONVERSION
line 7: COPERNICUS/S1_GRD is already log-scaled in dB. A second explicit 10*log10() conversion is being applied. Use the dB values directly, or use COPERNICUS/S1_GRD_FLOAT when linear power is required.
source: SRC-GEE-S1-GRD

1 finding: 1 FAIL, 0 CONDITIONAL
coverage: 1 recognized dataset, 1 supported operation check, 0 unresolved lineage, 0 unresolved temporal scopes, 0 suppressed findings
```

### Options

| Option | Values | Default |
|---|---|---|
| `--format` | `text`, `json` | `text` |
| `--fail-on` | `fail`, `conditional` | `fail` |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Result is below the configured failure threshold |
| `1` | Configured finding threshold reached |
| `2` | Invalid CLI usage or invalid input (missing file, wrong extension, >5 MiB, invalid UTF-8, Python syntax error) |
| `3` | Internal analyzer failure |

## Reason codes

| Code | Severity | Name | Detects |
|---|---|---|---|
| `EWL201` | FAIL | `LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE` | `normalizedDifference()` over encoded Landsat Collection 2 Level-2 SR digital numbers before the documented offset is applied |
| `EWL202` | FAIL | `LANDSAT_C2_BAND_SCALE_MISMATCH` | The documented SR scale/offset pair applied to a proven ST band, or the ST pair applied to proven SR bands |
| `EWL203` | CONDITIONAL | `NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK` | Correctly scaled Landsat SR passed to `normalizedDifference()`, which masks output pixels when either input is negative — a workflow choice that should be explicit (see below) |
| `EWL301` | FAIL | `SENTINEL1_GRD_REDUNDANT_DB_CONVERSION` | A second explicit `10*log10()` conversion on `COPERNICUS/S1_GRD`, which is already in dB |
| `EWL401` | CONDITIONAL | `ANALYSIS_SCALE_UNSPECIFIED` | `reduceRegion()` / `reduceRegions()` with neither `scale` nor `crsTransform` explicitly supplied (a call using `*`/`**` argument unpacking is not flagged, because the omission cannot be proven) |
| `EWL501` | FAIL | `SENTINEL2_QA60_UNAVAILABLE` | `QA60` use whose entire known interval falls inside the documented QA60 gap |
| `EWL502` | CONDITIONAL | `SENTINEL2_QA60_GAP_OVERLAP` | `QA60` use across an interval that overlaps, but is not contained by, the QA60 gap |

Run `eo-workflow-lint explain <CODE>` for each rule's exact triggers, non-triggers, and sources.

### EWL203: an explicit choice, not a prohibition

EWL203 does **not** mean "do not use `normalizedDifference()`". Earth Engine documents that
`ee.Image.normalizedDifference()` masks an output pixel when either input band is negative.
Correctly scaled Landsat Collection 2 surface reflectance can contain negative values, so the
call may silently change which pixels contribute to the analysis. Whether those pixels are
retained or excluded is a scientific/workflow choice; EWL203 asks that it be explicit.

- If excluding them is intentional, keep `normalizedDifference()` and document the choice, or
  suppress EWL203 at that call site.
- If retaining them is appropriate, compute the index with `ee.Image.expression()`, handle a
  zero or near-zero denominator deliberately, and apply that guard with `updateMask()` so the
  masks the inputs already carry are preserved. Do not `unmask()` inputs merely to keep
  negative values.

`check` prints these as short `hint:` lines; `eo-workflow-lint explain EWL203` prints a
guarded example (`examples/clean_workflow.py` is the same pattern in a full workflow, and
`examples/landsat_ndvi_scaled_negative_mask.py` is the minimal trigger).

## Verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | No `CONDITIONAL` or `FAIL` finding in the portion of the source the analyzer resolved |
| `CONDITIONAL` | A documented semantic creates a material interpretation or analysis-condition risk that needs explicit review |
| `FAIL` | The analyzer proved a supported conflict between the workflow and documented product/platform semantics |

Precedence is `FAIL > CONDITIONAL > PASS`.

## Suppression

A single-line directive suppresses specific codes on the immediately following physical line:

```python
# ewl: ignore-next-line=EWL203
ndvi = image.normalizedDifference(["SR_B5", "SR_B4"])

# ewl: ignore-next-line=EWL203,EWL401
stats = image.reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi)
```

A blank line between the directive and the target breaks the association, and a malformed
directive never suppresses anything. Suppressed findings do not affect the verdict or the exit
threshold; they are counted in `suppressed_finding_count`.

## GitHub Action

Add the official action to a workflow to lint every tracked `.py` file on each pull request:

```yaml
name: eo-workflow-lint
on: [pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: orbseekr-labs/eo-workflow-lint@v0.2.1
        with:
          fail-on: conditional
```

Findings appear as pull-request annotations (`FAIL` as errors, `CONDITIONAL` as warnings,
with file, line and reason code) and as a job Step Summary with per-file verdict totals. The
analysis runs entirely on the GitHub runner from the pinned tag's own source tree: no Earth
Engine credentials, no network access, no telemetry, and your source code is never uploaded
anywhere.

| Input | Default | Meaning |
|---|---|---|
| `fail-on` | `fail` | `fail` fails the step only on FAIL findings; `conditional` also fails on CONDITIONAL |
| `paths` | `*.py` | Newline-separated Git pathspecs; only `.py` matches are analyzed |

```yaml
      - uses: orbseekr-labs/eo-workflow-lint@v0.2.1
        with:
          fail-on: conditional
          paths: |
            *.py
            :!notebooks/**
```

A file that cannot be analyzed (for example a Python syntax error) is reported as
"not analyzable", counted separately from findings, and fails the step with exit code 2 —
the same distinction the CLI makes. Outputs: `verdict`, `files-checked`, `findings`,
`fail-count`, `conditional-count`, `not-analyzable`, `exit-code`.

## Other CI systems

```bash
pip install "git+https://github.com/orbseekr-labs/eo-workflow-lint.git@v0.2.1"
git ls-files -z -- '*.py' | xargs -0 -n1 eo-workflow-lint check --fail-on conditional
```

The JSON report is stable for a given `(source bytes, tool version, catalog version, options)`
tuple, so it can be committed, diffed, or cached:

```bash
eo-workflow-lint check workflow.py --format json > report.json
```

## JSON output

```json
{
  "schema_version": "0.2",
  "tool_version": "0.2.1",
  "catalog_version": "2026-09-22.1",
  "input": { "sha256": "…", "byte_length": 1234 },
  "verdict": "FAIL",
  "findings": [
    {
      "code": "EWL301",
      "severity": "FAIL",
      "name": "SENTINEL1_GRD_REDUNDANT_DB_CONVERSION",
      "line": 7,
      "column": 11,
      "message": "…",
      "source_ids": ["SRC-GEE-S1-GRD"],
      "evidence": {
        "dataset_id": "COPERNICUS/S1_GRD",
        "numeric_domain": "DB",
        "conversion_pattern": "log10().multiply(10)"
      }
    }
  ],
  "analysis": {
    "recognized_dataset_count": 1,
    "supported_operation_check_count": 1,
    "unresolved_lineage_count": 0,
    "unresolved_temporal_scope_count": 0,
    "suppressed_finding_count": 0
  }
}
```

The JSON report contains no filesystem path, timestamp, hostname, username, or source snippet,
so identical input bytes produce byte-identical output on any machine.

## Provenance

Every finding carries the source IDs it rests on. The bundled catalog is frozen at version
`2026-09-22.1` and is never refreshed at runtime; `eo-workflow-lint sources` prints the full
registry with titles, URLs, and the specific facts the rules rely on:

`SRC-USGS-LANDSAT-C2-SCALE`, `SRC-GEE-LANDSAT-C1-C2`, `SRC-GEE-NORMALIZED-DIFFERENCE`,
`SRC-GEE-S1-GRD`, `SRC-GEE-REDUCE-REGION`, `SRC-GEE-REDUCE-REGIONS`, `SRC-GEE-S2-HARMONIZED`,
`SRC-GEE-S2-SR-HARMONIZED`.

## Offline and privacy behavior

- No network access at runtime, and no network is required for any command.
- No telemetry, analytics, or crash reporting.
- No credentials, no API key, no Earth Engine authentication.
- The analyzed file is parsed with Python's `ast` module and is never executed, imported, or
  passed to `eval`/`exec`; no subprocess is spawned from it.
- Nothing is written outside stdout/stderr, and your source is never transmitted anywhere.

## Limitations

`eo-workflow-lint` 0.2.x is deliberately narrow. It does **not**:

- execute, import, or authenticate anything;
- analyze JavaScript, or read Jupyter notebook JSON directly;
- validate Rasterio, GDAL, xarray, openEO, STAC, QGIS, or ArcGIS workflows;
- rewrite or repair source code;
- estimate accuracy, validate scientific conclusions, or infer user intent;
- resolve dynamic dataset construction, reflection, configuration-driven IDs, or arbitrary
  user-defined scaling helpers — these reduce analysis coverage rather than produce findings.

Static analysis is conservative by design: when product identity, band identity, numeric domain,
scale state, or temporal scope cannot be proven, the relevant rule does not fire and a coverage
counter is incremented instead. Preferring a missed finding over a false one is a deliberate
product decision.

The following were excluded in v0.1.0 and are still **not** rules: Sentinel-2 Processing
Baseline 04.00 DN shift, mixed Sentinel-2 native resolutions, TOA-versus-surface-reflectance
mixing, Sentinel-1 ascending/descending or polarization mixing, and Landsat Collection 1 QA
bitmasks ported to Collection 2. See `SPECIFICATION.md` §11 for why each was excluded.

## Real-world validation

The rules are checked against pinned public Earth Engine repositories, not only synthetic
fixtures. [`docs/real-world-validation.md`](docs/real-world-validation.md) lists every
repository, commit, file and line, the human-reviewed expectation, and the v0.1.2 and current
results. In summary (2026-09-28): of the 8 human-verified EWL203 candidate repositories from
the original benchmark, v0.1.2 detected 0 and v0.2.1 detects 4 (the other 4 need
interprocedural or cross-module lineage, which is out of scope); expert negative controls
produce no false positives after the v0.2.1 EWL401 fix. There is no accuracy percentage: the
sample is small and was not drawn at random.

The benchmark manifest is [`validation/manifest.json`](validation/manifest.json). It stores
only repository URLs, commit SHAs, paths, lines and file digests — never third-party source.
Re-running it needs network access and is a manual developer command, not part of the test
suite:

```bash
python validation/run_benchmark.py                     # fetch pinned files, run the linter
python validation/run_benchmark.py --linter /path/to/other/eo-workflow-lint  # e.g. v0.1.2
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
python -m build
```

The test suite is offline. The version is defined once, in `src/eo_workflow_lint/__init__.py`.

The specification is frozen for the 0.2.x series: an implementation must not change verdict
semantics, reason-code meanings, thresholds, catalog constants, or the JSON report contract
without an authorised specification revision recorded in its Revision history (and the
frozen digest in `tests/test_spec_integrity.py`).

---

An [OrbSeekr Labs](https://github.com/orbseekr-labs) project.
