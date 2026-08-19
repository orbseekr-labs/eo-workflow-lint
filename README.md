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

- Version: **0.1.0**
- Specification: [`SPECIFICATION.md`](SPECIFICATION.md) (frozen for the 0.1.x series)
- Catalog version: `2026-08-19.1`
- Python: 3.11+
- Runtime dependencies: none (standard library only)
- License: Apache-2.0

## What PASS means

> `eo-workflow-lint` detects only a narrow set of documented Earth-observation workflow
> anti-patterns. **PASS** means that no supported v0.1.0 rule produced a finding in the
> statically resolved portion of the source. PASS does **not** prove that the workflow,
> analysis, model, or conclusion is scientifically correct.

Every report includes analysis-coverage counters so you can see how much of the source the
analyzer was actually able to resolve. Unresolved code is reported as coverage, never converted
into a scientific verdict — there is no `UNKNOWN` verdict.

## Install

```bash
pip install eo-workflow-lint
```

From a local checkout:

```bash
pip install .
```

## Usage

```bash
eo-workflow-lint check workflow.py
eo-workflow-lint check workflow.py --format json
eo-workflow-lint check workflow.py --fail-on conditional

eo-workflow-lint rules              # list the v0.1.0 reason codes
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
| `EWL203` | CONDITIONAL | `NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK` | Correctly scaled Landsat SR passed to `normalizedDifference()`, which masks pixels when either input is negative |
| `EWL301` | FAIL | `SENTINEL1_GRD_REDUNDANT_DB_CONVERSION` | A second explicit `10*log10()` conversion on `COPERNICUS/S1_GRD`, which is already in dB |
| `EWL401` | CONDITIONAL | `ANALYSIS_SCALE_UNSPECIFIED` | `reduceRegion()` / `reduceRegions()` with neither `scale` nor `crsTransform` explicitly supplied |
| `EWL501` | FAIL | `SENTINEL2_QA60_UNAVAILABLE` | `QA60` use whose entire known interval falls inside the documented QA60 gap |
| `EWL502` | CONDITIONAL | `SENTINEL2_QA60_GAP_OVERLAP` | `QA60` use across an interval that overlaps, but is not contained by, the QA60 gap |

Run `eo-workflow-lint explain <CODE>` for each rule's exact triggers, non-triggers, and sources.

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

## CI usage

```yaml
- name: Lint Earth Engine workflows
  run: |
    pip install eo-workflow-lint
    for f in $(git ls-files '*.py'); do
      eo-workflow-lint check "$f" --fail-on conditional
    done
```

The JSON report is stable for a given `(source bytes, tool version, catalog version, options)`
tuple, so it can be committed, diffed, or cached:

```bash
eo-workflow-lint check workflow.py --format json > report.json
```

## JSON output

```json
{
  "schema_version": "0.1",
  "tool_version": "0.1.0",
  "catalog_version": "2026-08-19.1",
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
`2026-08-19.1` and is never refreshed at runtime; `eo-workflow-lint sources` prints the full
registry with titles, URLs, and the specific facts v0.1.0 relies on:

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

`eo-workflow-lint` v0.1.0 is deliberately narrow. It does **not**:

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

The following are explicitly **not** v0.1.0 rules: Sentinel-2 Processing Baseline 04.00 DN
shift, mixed Sentinel-2 native resolutions, TOA-versus-surface-reflectance mixing, Sentinel-1
ascending/descending or polarization mixing, and Landsat Collection 1 QA bitmasks ported to
Collection 2. See `SPECIFICATION.md` §11 for why each was excluded.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

The specification is frozen for the 0.1.x series: an implementation must not change verdict
semantics, reason-code meanings, thresholds, catalog constants, or the JSON report contract
within 0.1.x.

---

An [OrbSeekr Labs](https://github.com/orbseekr-labs) project.
