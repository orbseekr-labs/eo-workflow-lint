# eo-workflow-lint Specification v0.1.0

**Status:** FROZEN  
**Specification version:** 0.1.0  
**Freeze date:** 2026-08-19 (JST)  
**Project:** OrbSeekr Labs Project #002  
**License target:** Apache-2.0  
**Implementation target:** Python 3.11+

> A deterministic, offline static analyzer for scientifically unsafe Google Earth Engine Python workflows.

---

## 0. Specification authority

This document is the normative specification for `eo-workflow-lint` v0.1.0.

Implementation MUST conform to this document. An implementer MUST NOT invent additional scientific rules, silently broaden detection, infer undocumented Earth-observation semantics, or change verdict semantics without a specification revision.

If an implementation question cannot be answered from this specification, implementation MUST stop and report a `SPEC BLOCKER` rather than guess.

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative.

---

## 1. Problem statement

Google Earth Engine can successfully execute workflows that are syntactically valid and operationally valid but scientifically unsafe because the workflow conflicts with documented semantics of the underlying Earth-observation product.

Examples include:

- computing normalized differences directly from encoded Landsat Collection 2 Level-2 surface-reflectance digital numbers without applying the documented additive offset;
- applying the Landsat surface-reflectance scale/offset pair to a surface-temperature band, or vice versa;
- using `ee.Image.normalizedDifference()` on correctly scaled Landsat surface reflectance without acknowledging Earth Engine's documented masking of negative input values;
- applying a second `10*log10()` conversion to `COPERNICUS/S1_GRD`, which Earth Engine already exposes in dB;
- calling region reducers without explicitly fixing analysis scale or transform;
- relying on Sentinel-2 `QA60` during the documented period in which that band is unavailable/masked.

These failures can produce plausible output without a Python syntax error or an Earth Engine runtime error.

`eo-workflow-lint` exists to detect a deliberately narrow set of such failures before execution.

---

## 2. Product position

### 2.1 What v0.1.0 is

`eo-workflow-lint` v0.1.0 is:

- a command-line linter;
- an offline source-code analyzer;
- deterministic for the same source bytes, tool version, and catalog version;
- limited to Google Earth Engine Python source files;
- based on Python AST plus a bundled static Earth-observation product catalog;
- source-provenance-aware;
- suitable for local development and CI.

### 2.2 What v0.1.0 is not

v0.1.0 MUST NOT:

- execute the analyzed Python file;
- import the analyzed Python file;
- authenticate to Earth Engine;
- make any network request;
- call an LLM;
- call Earth Engine APIs;
- download imagery or metadata;
- validate final scientific conclusions;
- estimate model accuracy;
- infer user intent when the source does not prove it;
- analyze JavaScript;
- directly analyze Jupyter notebook JSON;
- validate arbitrary Rasterio, GDAL, xarray, openEO, STAC, QGIS, or ArcGIS workflows;
- automatically rewrite source code;
- claim that `PASS` means the workflow is scientifically correct.

---

## 3. v0.1.0 supported input

### 3.1 File type

The `check` command MUST accept exactly one local `.py` source file.

The file MUST be decoded as UTF-8.

A source file larger than 5 MiB MUST be rejected as invalid input.

### 3.2 Parsing

The implementation MUST parse source using Python's standard-library `ast` module.

The implementation MUST NOT execute or import the source.

Python syntax errors MUST produce exit code `2`.

Unsupported dynamic constructs are not syntax errors. They reduce analysis coverage instead.

### 3.3 Source content hash

The implementation MUST calculate SHA-256 over the exact input bytes.

The JSON result MUST include the SHA-256 hash.

Absolute paths, hostnames, usernames, timestamps, process IDs, random IDs, and environment-specific values MUST NOT appear in deterministic JSON output.

---

## 4. Verdict model

The only top-level verdicts in v0.1.0 are:

1. `PASS`
2. `CONDITIONAL`
3. `FAIL`

### 4.1 PASS

`PASS` means:

> No finding at `CONDITIONAL` or `FAIL` severity was detected by the supported v0.1.0 rules in the portion of the source that the analyzer could resolve.

`PASS` MUST NOT be described as a guarantee of scientific correctness, data quality, legal validity, operational success, or reproducibility.

### 4.2 CONDITIONAL

`CONDITIONAL` means:

> The workflow may be valid, but a documented Earth Engine or product semantic creates a material interpretation or analysis-condition risk that requires explicit review.

### 4.3 FAIL

`FAIL` means:

> The analyzer proved a supported conflict between the workflow operation and documented product/platform semantics.

### 4.4 Verdict precedence

Top-level verdict precedence MUST be:

`FAIL > CONDITIONAL > PASS`

If at least one unsuppressed `FAIL` exists, verdict MUST be `FAIL`.

Else, if at least one unsuppressed `CONDITIONAL` exists, verdict MUST be `CONDITIONAL`.

Else verdict MUST be `PASS`.

### 4.5 No UNKNOWN verdict

v0.1.0 MUST NOT expose an `UNKNOWN` top-level verdict.

Unresolved code MUST be reported through analysis coverage counters instead of being converted into a scientific verdict.

---

## 5. Finding model

Every finding MUST contain:

- stable reason code;
- severity;
- short symbolic name;
- human-readable message;
- 1-based source line;
- 0-based source column;
- one or more source IDs;
- a compact evidence object describing the statically proven trigger.

A finding MUST NOT be emitted unless the exact rule preconditions below are satisfied.

Duplicate findings with the same `(code, line, column, evidence)` MUST be de-duplicated.

Distinct findings MAY share the same reason code.

---

## 6. Bundled source catalog

### 6.1 Catalog identity

The initial v0.1.0 static catalog version MUST be:

`2026-08-19.1`

Catalog facts MUST be bundled with the package and MUST NOT be refreshed at runtime.

### 6.2 Source registry

The implementation MUST expose these source IDs through `eo-workflow-lint sources`.

#### SRC-USGS-LANDSAT-C2-SCALE

Title: USGS — How do I use a scale factor with Landsat Level-2 science products?  
URL: `https://www.usgs.gov/faqs/how-do-i-use-a-scale-factor-landsat-level-2-science-products`

Normative facts used by v0.1.0:

- Collection 2 Surface Reflectance scale factor: `0.0000275`
- Collection 2 Surface Reflectance additive offset: `-0.2`
- Collection 2 Surface Temperature scale factor: `0.00341802`
- Collection 2 Surface Temperature additive offset: `149.0`

#### SRC-GEE-LANDSAT-C1-C2

Title: Google Earth Engine — Landsat Collection 1 to Collection 2 migration  
URL: `https://developers.google.com/earth-engine/landsat_c1_to_c2`

Normative facts used by v0.1.0:

- Collection 2 Level-2 reflectance uses the new scale and additive offset;
- Collection 2 thermal bands use a distinct scale and additive offset;
- Google provides an explicit example that scales SR and ST separately.

#### SRC-GEE-NORMALIZED-DIFFERENCE

Title: Google Earth Engine — ee.Image.normalizedDifference  
URL: `https://developers.google.com/earth-engine/apidocs/ee-image-normalizeddifference`

Normative fact used by v0.1.0:

- if either input band has a negative pixel value, the output pixel from `normalizedDifference()` is masked;
- Google recommends `ee.Image.expression()` when negative values must not be masked.

#### SRC-GEE-S1-GRD

Title: Google Earth Engine Data Catalog — COPERNICUS/S1_GRD  
URL: `https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD`

Normative facts used by v0.1.0:

- `COPERNICUS/S1_GRD` is provided in decibels after log scaling;
- raw power values are exposed separately through `COPERNICUS/S1_GRD_FLOAT`.

#### SRC-GEE-REDUCE-REGION

Title: Google Earth Engine — ee.Image.reduceRegion  
URL: `https://developers.google.com/earth-engine/apidocs/ee-image-reduceregion`

Normative fact used by v0.1.0:

- Google states it is good practice to explicitly define analysis `scale` (or `crsTransform`) and `crs` to avoid unexpected results from undesired defaults.

#### SRC-GEE-REDUCE-REGIONS

Title: Google Earth Engine — ee.Image.reduceRegions  
URL: `https://developers.google.com/earth-engine/apidocs/ee-image-reduceregions`

Normative fact used by v0.1.0:

- the API supports explicit `scale`, `crs`, and `crsTransform` for region analysis.

#### SRC-GEE-S2-HARMONIZED

Title: Google Earth Engine Data Catalog — Harmonized Sentinel-2 MSI Level-1C  
URL: `https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_HARMONIZED`

Normative facts used by v0.1.0:

- `QA60` historically contained rasterized cloud polygons;
- those polygons stopped being produced in 2022;
- legacy-consistent QA60 bands are constructed again from `MSK_CLASSI` beginning in February 2024.

#### SRC-GEE-S2-SR-HARMONIZED

Title: Google Earth Engine Data Catalog — Harmonized Sentinel-2 MSI Level-2A  
URL: `https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED`

Normative facts used by v0.1.0:

- the QA60 discontinuity applies to the Level-2A harmonized collection;
- v0.1.0 uses the conservative interior interval beginning `2022-01-26` and ending before `2024-02-28`; the boundary dates themselves are intentionally not linted in v0.1.0 to avoid false positives from documentation-boundary ambiguity.

---

## 7. Supported dataset recognition

Dataset recognition MUST require a statically known string literal or a statically resolved constant string.

### 7.1 Landsat Collection 2 Level-2

The following dataset ID forms MUST be recognized as `LANDSAT_C2_L2`:

- `LANDSAT/LT04/C02/T1_L2`
- `LANDSAT/LT04/C02/T2_L2`
- `LANDSAT/LT05/C02/T1_L2`
- `LANDSAT/LT05/C02/T2_L2`
- `LANDSAT/LE07/C02/T1_L2`
- `LANDSAT/LE07/C02/T2_L2`
- `LANDSAT/LC08/C02/T1_L2`
- `LANDSAT/LC08/C02/T2_L2`
- `LANDSAT/LC09/C02/T1_L2`
- `LANDSAT/LC09/C02/T2_L2`

A concrete image asset whose ID begins with one of the collection IDs above plus `/` MUST also be recognized.

Band families:

- surface reflectance: names matching `SR_B[1-7]`;
- surface temperature: `ST_B6` for LT04/LT05/LE07 and `ST_B10` for LC08/LC09;
- QA bands are not part of either numeric scaling family.

v0.1.0 MUST NOT assume that applying SR scaling to an entire Landsat image is correct.

### 7.2 Sentinel-1

`COPERNICUS/S1_GRD` MUST be recognized as domain `DB`.

`COPERNICUS/S1_GRD_FLOAT` MUST be recognized as domain `LINEAR_POWER`.

Backscatter bands recognized by v0.1.0 are:

- `VV`
- `VH`
- `HH`
- `HV`

### 7.3 Sentinel-2 QA60-capable families

The following collection IDs MUST be recognized for QA60 temporal analysis:

- `COPERNICUS/S2`
- `COPERNICUS/S2_HARMONIZED`
- `COPERNICUS/S2_SR`
- `COPERNICUS/S2_SR_HARMONIZED`

The v0.1.0 QA60 gap interval MUST be represented as:

`[2022-01-26T00:00:00Z, 2024-02-28T00:00:00Z)`

The end boundary is exclusive in the linter's interval model. v0.1.0 intentionally excludes the two documentation boundary dates from hard/conditional temporal findings because the catalog prose and band-table wording are not perfectly aligned at those boundaries. This conservative interior interval reduces false positives.

---

## 8. Static-analysis model

### 8.1 Conservative proof rule

The analyzer MUST prefer no finding over a finding based on uncertain lineage.

If product identity, band identity, transform state, numeric domain, or temporal interval becomes ambiguous, a rule that requires that fact MUST NOT fire.

The analyzer MUST increment an appropriate unresolved coverage counter instead.

### 8.2 Abstract image state

At minimum, abstract image state MUST be capable of carrying:

- recognized dataset/product family;
- known selected bands, if any;
- semantic band family, if provable;
- Landsat SR scale state: `RAW`, `CORRECTLY_SCALED`, or `UNKNOWN`;
- Landsat ST scale state: `RAW`, `CORRECTLY_SCALED`, or `UNKNOWN`;
- Sentinel-1 numeric domain: `DB`, `LINEAR_POWER`, or `UNKNOWN`;
- known temporal interval, if any;
- provenance/source IDs relevant to the state.

### 8.3 Name and constant resolution

The analyzer MUST resolve simple single-name assignments such as:

```python
DATASET = "COPERNICUS/S1_GRD"
collection = ee.ImageCollection(DATASET)
```

The analyzer MUST resolve numeric constants assigned to a simple name when unambiguous in the current scope.

Reassignment with conflicting values MUST invalidate the constant binding for subsequent use unless ordinary lexical statement order proves a single current value.

### 8.4 Simple aliases

The analyzer MUST propagate state through direct assignments:

```python
a = ee.ImageCollection("COPERNICUS/S1_GRD")
b = a.filterDate("2020-01-01", "2020-02-01")
```

### 8.5 Supported pass-through operations

The following operations SHOULD preserve recognized dataset lineage when their use does not alter the relevant semantic domain:

- `filterDate`
- `filter`
- `filterBounds`
- `select`
- `clip`
- `updateMask`
- `mask`
- `rename` (lineage preserved; visible-band mapping MAY become unknown)
- `copyProperties`

An implementation MAY support additional pass-through methods only if doing so cannot create false positive scientific findings.

### 8.6 Unknown-producing operations

Unrecognized arithmetic or nonlinear operations MUST conservatively set the affected numeric-domain/scale state to `UNKNOWN` when preserving the old state could create a false positive.

Example: after an arbitrary `pow()`, `exp()`, or unknown function call, the implementation MUST NOT continue to claim that a value is still Sentinel-1 dB unless the operation is explicitly modeled.

### 8.7 `select()` semantics

Literal band selectors MUST be tracked.

Supported selectors include:

- a literal string;
- a literal list or tuple of strings;
- a statically resolved constant string/list/tuple.

Regex semantics do not need to be fully interpreted in v0.1.0. The exact pattern `SR_B.` MAY be recognized as the Landsat SR family for the scaling idiom described below.

### 8.8 `filterDate()` semantics

v0.1.0 MUST recognize temporal intervals only when both start and end are statically known ISO-like date/datetime strings.

At minimum the parser MUST accept:

- `YYYY-MM-DD`
- `YYYY-MM-DDTHH:MM:SS`
- `YYYY-MM-DDTHH:MM:SSZ`

Earth Engine end-date semantics MUST be modeled as exclusive.

A single-argument `filterDate()` is outside required v0.1.0 temporal reasoning and MUST increment unresolved temporal scope if QA60 reasoning later depends on it.

### 8.9 `.map()` semantics

v0.1.0 MUST support the common pattern:

```python
def f(image):
    ...
    return image

collection.map(f)
```

Requirements:

- `f` MUST be defined in the same file;
- `f` MUST have exactly one required positional data argument for the mapped image;
- the mapped parameter MUST inherit the element image state and temporal interval from the collection;
- analysis MUST be static only;
- recursive map functions are not required;
- dynamic function lookup is not required.

A single-expression lambda SHOULD be supported:

```python
collection.map(lambda image: image.select("VV"))
```

### 8.10 Control flow

v0.1.0 does not require path-sensitive symbolic execution.

When multiple control-flow branches yield incompatible abstract states, the merged state MUST become `UNKNOWN` for the conflicting property.

This rule exists to reduce false positives.

---

## 9. Recognized Landsat scaling idioms

### 9.1 Correct SR scaling

The analyzer MUST recognize the following semantic transformation as correct Collection 2 SR scaling when it is applied only to a statically proven SR band selection:

`multiply(0.0000275).add(-0.2)`

The numerically equivalent literal `2.75e-05` MUST be accepted.

Constants statically bound to these exact numeric values MUST be accepted.

### 9.2 Correct ST scaling

The analyzer MUST recognize the following semantic transformation as correct Collection 2 ST scaling when applied only to a statically proven `ST_B10` selection:

`multiply(0.00341802).add(149.0)`

`149` and `149.0` MUST be treated as equivalent.

### 9.3 Transform order

The order MUST be multiply then add.

`add(...).multiply(...)` MUST NOT be treated as the documented scaling transformation.

### 9.4 Overwrite idiom

The analyzer MUST recognize the common Google migration pattern in which correctly scaled bands are written back into the original image:

```python
optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
thermal = image.select("ST_B10").multiply(0.00341802).add(149.0)
image = image.addBands(optical, None, True)
image = image.addBands(thermal, None, True)
```

Equivalent keyword form MUST be recognized:

```python
image.addBands(optical, overwrite=True)
```

If overwrite is not statically proven true, the original band's scale state MUST NOT be replaced.

### 9.5 Unsupported custom scaling

Arbitrary user-defined helper functions that happen to perform equivalent scaling are not required to be recognized unless their body is analyzable under the same local rules.

Failure to recognize equivalent custom scaling MUST reduce coverage rather than generate a false `FAIL`.

---

# 10. Rules

## 10.1 EWL201 — LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE

**Severity:** `FAIL`  
**Primary sources:** `SRC-USGS-LANDSAT-C2-SCALE`, `SRC-GEE-LANDSAT-C1-C2`

### Intent

Detect normalized-difference computation over encoded Landsat Collection 2 Level-2 SR digital numbers before the documented additive offset has been applied.

### Required trigger

Emit EWL201 only if all are proven:

1. the receiver image is `LANDSAT_C2_L2`;
2. the two normalized-difference inputs are Landsat SR bands;
3. the relevant SR state is `RAW`;
4. the operation is `ee.Image.normalizedDifference()` or method-equivalent `image.normalizedDifference()`;
5. the two input bands are statically known either from the explicit argument or from an immediately known two-band receiver selection.

### Non-triggers

MUST NOT emit EWL201 when:

- SR scaling is proven correct and overwritten/applied before the operation;
- product identity is unknown;
- band identity is unknown;
- the user uses `expression()` instead of `normalizedDifference()`;
- the data are Landsat TOA rather than Collection 2 Level-2 SR;
- the operation is on non-SR bands.

### Message template

`Landsat Collection 2 Level-2 surface-reflectance bands are encoded with scale 0.0000275 and additive offset -0.2. normalizedDifference() is being applied before the documented SR scaling is proven.`

### Evidence fields

- `dataset_id`
- `bands`
- `sr_scale_state`

---

## 10.2 EWL202 — LANDSAT_C2_BAND_SCALE_MISMATCH

**Severity:** `FAIL`  
**Primary sources:** `SRC-USGS-LANDSAT-C2-SCALE`, `SRC-GEE-LANDSAT-C1-C2`

### Intent

Detect application of the documented Landsat Collection 2 SR transform to a proven ST band, or the documented ST transform to proven SR bands.

### Trigger A

Emit if:

- receiver/product is `LANDSAT_C2_L2`;
- selected family is a recognized Landsat Collection 2 ST band (`ST_B6` or `ST_B10` as platform-appropriate);
- applied chain is exactly SR scaling: `multiply(0.0000275).add(-0.2)`.

### Trigger B

Emit if:

- receiver/product is `LANDSAT_C2_L2`;
- selected family is SR;
- applied chain is exactly ST scaling: `multiply(0.00341802).add(149.0)`.

### Non-triggers

MUST NOT emit for arbitrary other numeric arithmetic.

The rule is deliberately a cross-family mismatch detector, not a generic "unexpected scale" detector.

### Message template

`A documented Landsat Collection 2 scale/offset pair is being applied to the wrong band family.`

### Evidence fields

- `dataset_id`
- `band_family`
- `applied_scale`
- `applied_offset`
- `expected_family_for_transform`

---

## 10.3 EWL203 — NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK

**Severity:** `CONDITIONAL`  
**Primary sources:** `SRC-GEE-NORMALIZED-DIFFERENCE`, `SRC-USGS-LANDSAT-C2-SCALE`

### Intent

Warn when correctly scaled Landsat Collection 2 SR values are passed to `normalizedDifference()`, because the Earth Engine API masks output pixels when either input value is negative.

### Required trigger

Emit only if all are proven:

1. product is `LANDSAT_C2_L2`;
2. the two inputs are SR bands;
3. SR scaling state is `CORRECTLY_SCALED`;
4. operation is `normalizedDifference()`;
5. the relevant band identities are statically known.

### Non-triggers

MUST NOT emit:

- on RAW Landsat SR; EWL201 covers that case;
- on `expression()` normalized-difference formulas;
- if scale state is unknown;
- for non-Landsat products in v0.1.0.

### Message template

`ee.Image.normalizedDifference() masks a pixel when either input band is negative. Correctly scaled Landsat surface reflectance can contain negative physical values; review whether silent masking is acceptable or use expression() when negatives must be retained.`

### Evidence fields

- `dataset_id`
- `bands`
- `sr_scale_state`

---

## 10.4 EWL301 — SENTINEL1_GRD_REDUNDANT_DB_CONVERSION

**Severity:** `FAIL`  
**Primary source:** `SRC-GEE-S1-GRD`

### Intent

Detect an additional explicit `10*log10()` conversion applied to Earth Engine `COPERNICUS/S1_GRD`, whose backscatter values are already exposed in dB.

### Required trigger

Emit only when:

1. lineage is proven to originate from `COPERNICUS/S1_GRD`;
2. numeric domain at the conversion input is proven `DB`;
3. the analyzer recognizes one of the v0.1.0 explicit dB conversion forms.

### Required recognized dB conversion forms

At minimum:

```python
image.log10().multiply(10)
```

and

```python
10 * image.log10()
```

Numeric literal `10.0` MUST be equivalent to `10`.

### Domain safety

A standalone `.log10()` MUST NOT trigger EWL301.

If an unsupported arithmetic/nonlinear transformation occurs between the S1_GRD value and the dB-conversion pattern, domain MUST become `UNKNOWN` and EWL301 MUST NOT fire.

`COPERNICUS/S1_GRD_FLOAT` MUST NOT trigger EWL301.

### Message template

`COPERNICUS/S1_GRD is already log-scaled in dB. A second explicit 10*log10() conversion is being applied. Use the dB values directly, or use COPERNICUS/S1_GRD_FLOAT when linear power is required.`

### Evidence fields

- `dataset_id`
- `numeric_domain`
- `conversion_pattern`

---

## 10.5 EWL401 — ANALYSIS_SCALE_UNSPECIFIED

**Severity:** `CONDITIONAL`  
**Primary sources:** `SRC-GEE-REDUCE-REGION`, `SRC-GEE-REDUCE-REGIONS`

### Intent

Warn when Earth Engine region reduction relies on implicit analysis scale/transform.

### Supported calls

- `Image.reduceRegion()`
- `Image.reduceRegions()`

### Trigger

Emit when neither `scale` nor `crsTransform` is statically supplied with a non-`None` value.

### Keyword rules

These suppress the finding:

- `scale=<non-None expression>`
- `crsTransform=<non-None expression>`

The expression does not need to resolve numerically. The rule checks explicitness, not whether the chosen value is scientifically optimal.

### Positional rules

For `reduceRegion(reducer, geometry, scale, crs, crsTransform, ...)`:

- third positional argument is `scale`;
- fifth positional argument is `crsTransform`.

For `reduceRegions(collection, reducer, scale, crs, crsTransform, ...)`:

- third positional argument is `scale`;
- fifth positional argument is `crsTransform`.

A positional literal `None` does not suppress the finding.

### Non-goal

EWL401 MUST NOT judge whether a supplied scale is appropriate.

### Message template

`Region reduction does not explicitly define scale or crsTransform. Earth Engine recommends explicitly defining analysis scale/transform to avoid unexpected results from defaults.`

### Evidence fields

- `operation`
- `scale_explicit`
- `crs_transform_explicit`

---

## 10.6 EWL501 — SENTINEL2_QA60_UNAVAILABLE

**Severity:** `FAIL`  
**Primary sources:** `SRC-GEE-S2-HARMONIZED`, `SRC-GEE-S2-SR-HARMONIZED`

### Intent

Detect a workflow that statically selects Sentinel-2 `QA60` when its entire known analysis interval is inside the documented QA60 gap.

### Trigger

Emit only when all are proven:

1. lineage is one of the supported Sentinel-2 collections;
2. band `QA60` is selected or directly referenced;
3. a closed-open requested interval `[start, end)` is statically known;
4. `[start, end)` is entirely contained within `[2022-01-26, 2024-02-28)`.

### Message template

`The workflow relies on Sentinel-2 QA60 for a period entirely inside the documented QA60 availability gap (the conservative 2022-01-26 to 2024-02-28 interval in the v0.1 catalog).`

### Evidence fields

- `dataset_id`
- `requested_start`
- `requested_end`
- `qa60_gap_start`
- `qa60_gap_end`

---

## 10.7 EWL502 — SENTINEL2_QA60_GAP_OVERLAP

**Severity:** `CONDITIONAL`  
**Primary sources:** `SRC-GEE-S2-HARMONIZED`, `SRC-GEE-S2-SR-HARMONIZED`

### Intent

Warn when a statically known Sentinel-2 analysis interval overlaps the QA60 gap but is not entirely contained within it.

### Trigger

Emit when:

1. supported Sentinel-2 lineage is proven;
2. `QA60` use is proven;
3. `[start, end)` is statically known;
4. the interval intersects `[2022-01-26, 2024-02-28)`;
5. EWL501 does not apply.

### Unknown dates

If QA60 is used but temporal scope cannot be proven, v0.1.0 MUST NOT emit EWL502 solely because the collection as a whole spans the gap.

Instead, increment `unresolved_temporal_scope_count`.

### Message template

`The workflow relies on Sentinel-2 QA60 across a time range that overlaps the documented QA60 availability gap. Review temporal cloud-mask consistency.`

### Evidence fields

- `dataset_id`
- `requested_start`
- `requested_end`
- `qa60_gap_start`
- `qa60_gap_end`

---

## 11. Explicitly excluded candidate rules

The following are intentionally NOT v0.1.0 rules:

### 11.1 Sentinel-2 Processing Baseline 04.00 DN shift

Reason: the risk is real, but AST-only analysis cannot reliably prove whether custom compensation/harmonization has already been applied without materially broader data-flow semantics.

Status: v0.2 backlog.

### 11.2 Mixed Sentinel-2 native resolutions

Reason: mixing 10 m, 20 m, and 60 m bands can be intentional; automatic resampling is not itself a contradiction.

Status: excluded from v0.1.0.

### 11.3 TOA versus surface reflectance mixing

Reason: mixing can be intentional in calibration, diagnostics, or specialized workflows; user intent cannot be inferred safely.

Status: excluded from v0.1.0.

### 11.4 Sentinel-1 ascending/descending or polarization mixing

Reason: heterogeneous collection mixing can be wrong or intentional depending on the analysis.

Status: excluded from v0.1.0.

### 11.5 Landsat Collection 1 QA bitmask ported to Collection 2

Reason: bit patterns are documented to differ, but code alone cannot always prove the author's intended class combination.

Status: v0.2 candidate after intent-free detection semantics are found.

---

## 12. Suppression

v0.1.0 MUST provide a narrow source-level suppression mechanism.

### 12.1 Syntax

The supported directive is:

```python
# ewl: ignore-next-line=EWL203
ndvi = image.normalizedDifference(["SR_B5", "SR_B4"])
```

Multiple codes MAY be comma-separated:

```python
# ewl: ignore-next-line=EWL203,EWL401
```

### 12.2 Semantics

The directive applies only to findings whose primary finding line is the immediately following physical line.

Blank lines break the directive association.

A malformed directive MUST NOT suppress findings.

Unknown reason codes in a suppression directive SHOULD produce a non-fatal text warning but MUST NOT change scientific verdict.

Suppressed findings MUST NOT affect top-level verdict or exit threshold.

The JSON analysis object MUST include `suppressed_finding_count`.

v0.1.0 does not require file-wide disable directives.

---

## 13. Analysis coverage

The analyzer MUST report at least:

- `recognized_dataset_count`
- `supported_operation_check_count`
- `unresolved_lineage_count`
- `unresolved_temporal_scope_count`
- `suppressed_finding_count`

Coverage counters are informational and MUST NOT change verdict by themselves.

A `PASS` result with unresolved coverage MUST still clearly state in text output that PASS is limited to supported/proven analysis.

---

## 14. Deterministic ordering

Findings MUST be sorted by this tuple:

1. severity rank: `FAIL=0`, `CONDITIONAL=1`;
2. line ascending;
3. column ascending;
4. reason code ascending;
5. symbolic name ascending.

Source IDs inside a finding MUST be sorted lexicographically.

Dictionary/object key order in serialized JSON SHOULD follow the schema order defined below.

JSON output MUST use UTF-8 and stable separators/indentation chosen once by the implementation.

JSON MUST NOT contain timestamps generated at runtime.

---

## 15. JSON output schema

The conceptual v0.1.0 JSON shape is:

```json
{
  "schema_version": "0.1",
  "tool_version": "0.1.0",
  "catalog_version": "2026-08-19.1",
  "input": {
    "sha256": "<64 lowercase hex chars>",
    "byte_length": 1234
  },
  "verdict": "FAIL",
  "findings": [
    {
      "code": "EWL301",
      "severity": "FAIL",
      "name": "SENTINEL1_GRD_REDUNDANT_DB_CONVERSION",
      "line": 12,
      "column": 11,
      "message": "...",
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

The JSON MUST NOT include the absolute or relative filesystem path of the input.

The JSON MUST NOT include source code snippets in v0.1.0.

---

## 16. Text output

Text output SHOULD be concise and optimized for developer use.

A failing example SHOULD resemble:

```text
FAIL

EWL301 SENTINEL1_GRD_REDUNDANT_DB_CONVERSION
line 12: COPERNICUS/S1_GRD is already log-scaled in dB. A second explicit 10*log10() conversion is being applied.
source: SRC-GEE-S1-GRD

1 finding: 1 FAIL, 0 CONDITIONAL
coverage: 1 recognized dataset, 0 unresolved lineage, 0 unresolved temporal scopes
```

Text output MAY include the CLI-provided path for user convenience; deterministic JSON MUST NOT.

---

## 17. CLI

Required commands:

```bash
eo-workflow-lint check FILE
eo-workflow-lint rules
eo-workflow-lint explain CODE
eo-workflow-lint sources
eo-workflow-lint --version
```

### 17.1 check options

Required:

```bash
--format text|json
--fail-on fail|conditional
```

Defaults:

- `--format text`
- `--fail-on fail`

### 17.2 fail threshold

With `--fail-on fail`:

- exit 1 if any unsuppressed FAIL exists;
- CONDITIONAL alone exits 0.

With `--fail-on conditional`:

- exit 1 if any unsuppressed FAIL or CONDITIONAL exists.

### 17.3 exit codes

- `0` = result below configured failure threshold;
- `1` = configured finding threshold reached;
- `2` = invalid CLI usage or invalid input;
- `3` = internal analyzer failure.

No other exit code is part of the v0.1.0 contract.

---

## 18. Error handling

### 18.1 Invalid input, exit 2

Examples:

- missing file;
- non-file path;
- unsupported extension;
- file > 5 MiB;
- invalid UTF-8;
- Python syntax error.

### 18.2 Internal failure, exit 3

Unexpected analyzer exceptions MUST become exit 3.

In JSON mode, internal failures MAY emit a machine-readable error object, but MUST NOT emit a normal scientific verdict pretending analysis succeeded.

Tracebacks SHOULD be hidden by default and MAY be exposed through a developer/debug option that is outside the stable v0.1.0 CLI contract.

---

## 19. Security and privacy requirements

The runtime MUST:

- perform no network access;
- perform no telemetry;
- execute no subprocess based on analyzed source;
- use no `eval()` or `exec()` on analyzed content;
- import no analyzed module;
- load no plugins from the analyzed project;
- write no analyzed source to temporary files unless required by the runtime, and no such write is expected for v0.1.0;
- read only the requested input and bundled package resources during ordinary `check` execution.

CI MUST include a test or scan proving that normal `check` execution works with network unavailable.

---

## 20. Dependency policy

The v0.1.0 runtime SHOULD use only the Python standard library.

A runtime dependency MUST NOT be introduced unless the standard library cannot implement a frozen requirement safely and simply.

Development dependencies MAY include:

- `pytest`
- `ruff`

No LLM or Earth Engine SDK dependency is permitted at runtime for v0.1.0.

---

## 21. Test requirements

No release is allowed unless all normative rule behavior below is covered by automated tests.

### 21.1 General tests

MUST test:

- UTF-8 parsing;
- syntax-error exit 2;
- oversized-file exit 2;
- deterministic JSON byte-for-byte across repeated runs;
- same JSON when the same source bytes are checked from different filesystem directories;
- stable finding ordering;
- suppression;
- malformed suppression does not hide a finding;
- no source execution;
- no network requirement;
- exit threshold behavior.

### 21.2 EWL201 tests

Positive tests MUST include:

- direct Landsat C2 L2 image + raw `normalizedDifference(["SR_B5", "SR_B4"])`;
- ImageCollection mapped function using raw SR bands;
- constant-bound dataset ID;
- exact two-band `select()` followed by no-argument `normalizedDifference()` if implemented.

Negative tests MUST include:

- correctly scaled/overwritten SR before normalizedDifference;
- Landsat TOA dataset;
- unknown dataset;
- non-SR bands;
- `expression()` formula.

### 21.3 EWL202 tests

Positive:

- `ST_B6` or `ST_B10` with SR scale/offset;
- `SR_B5` with ST scale/offset;
- `SR_B.` selection with ST scale/offset;
- constants bound to wrong documented pair.

Negative:

- correct SR scaling;
- correct ST scaling;
- arbitrary multiplication not equal to the other documented transform;
- unknown band selection.

### 21.4 EWL203 tests

Positive:

- correctly scaled Landsat SR overwritten then normalizedDifference;
- correctly scaled two-band SR selection then normalizedDifference.

Negative:

- raw Landsat SR (EWL201 only);
- `expression()`;
- scale state unknown;
- non-Landsat product.

### 21.5 EWL301 tests

Positive:

- `s1.log10().multiply(10)` from S1_GRD;
- `10 * s1.log10()` from S1_GRD;
- mapped named function;
- constant dataset ID.

Negative:

- `COPERNICUS/S1_GRD_FLOAT`;
- standalone `.log10()`;
- arbitrary transformed domain that becomes UNKNOWN;
- non-Sentinel dataset.

### 21.6 EWL401 tests

Positive:

- `reduceRegion()` without scale/transform;
- `reduceRegions()` without scale/transform;
- explicit `scale=None`;
- positional `scale=None` and no transform.

Negative:

- keyword `scale=30`;
- keyword `scale=my_scale`;
- keyword `crsTransform=transform`;
- positional non-None scale;
- positional non-None crsTransform.

### 21.7 EWL501/EWL502 tests

EWL501 positive:

- QA60 with interval fully inside gap;
- same through mapped cloud-mask function.

EWL502 positive:

- interval starts before gap and ends inside gap;
- interval starts inside gap and ends after gap;
- interval spans entire gap.

Negative:

- interval entirely before gap;
- interval entirely after gap;
- non-QA60 band;
- non-Sentinel-2 dataset;
- unknown temporal scope: no EWL501/502, increment unresolved temporal count.

### 21.8 Cross-rule tests

MUST prove:

- raw Landsat SR normalizedDifference => EWL201, not EWL203;
- correctly scaled Landsat SR normalizedDifference => EWL203, not EWL201;
- wrong Landsat cross-family scale => EWL202 regardless of later use;
- QA60 fully in gap => EWL501 only, not EWL502;
- multiple distinct findings have deterministic order.

---

## 22. Minimum release quality gate

A v0.1.0 release candidate MUST satisfy all of the following:

1. all tests pass on Python 3.11, 3.12, and 3.13;
2. `ruff` is green;
3. clean-install CLI smoke test passes;
4. deterministic JSON test passes;
5. network-disabled `check` test passes;
6. package contains the frozen catalog and source registry;
7. `rules`, `explain`, and `sources` reflect exactly this specification;
8. no additional scientific reason code exists outside this specification;
9. README states PASS limitation prominently;
10. privacy/security scan finds no telemetry, credential access, or network dependency in normal runtime.

---

## 23. README-required limitation language

The README MUST communicate, in substance:

> `eo-workflow-lint` detects only a narrow set of documented Earth-observation workflow anti-patterns. PASS means that no supported rule fired in the statically resolved portion of the source. PASS does not prove that the workflow, analysis, model, or conclusion is scientifically correct.

The exact wording MAY differ, but the meaning MUST not be weakened.

---

## 24. Stable reason-code registry

| Code | Severity | Name |
|---|---|---|
| EWL201 | FAIL | LANDSAT_C2_SR_UNSCALED_NORMALIZED_DIFFERENCE |
| EWL202 | FAIL | LANDSAT_C2_BAND_SCALE_MISMATCH |
| EWL203 | CONDITIONAL | NORMALIZED_DIFFERENCE_NEGATIVE_MASK_RISK |
| EWL301 | FAIL | SENTINEL1_GRD_REDUNDANT_DB_CONVERSION |
| EWL401 | CONDITIONAL | ANALYSIS_SCALE_UNSPECIFIED |
| EWL501 | FAIL | SENTINEL2_QA60_UNAVAILABLE |
| EWL502 | CONDITIONAL | SENTINEL2_QA60_GAP_OVERLAP |

Reason codes MUST NOT be repurposed after release.

Removed or deprecated future reason codes MUST remain reserved once publicly released.

---

## 25. Implementation boundaries

The implementation team MAY choose internal module names and class structure.

The implementation team MUST NOT change:

- supported scope;
- verdict semantics;
- reason-code meaning;
- severity;
- source facts;
- QA60 boundary constants;
- CLI stable commands/options;
- exit codes;
- JSON semantic fields;
- false-positive guardrails;
- runtime offline/no-execution requirements.

without a specification revision.

---

## 26. Recommended repository shape (non-normative)

```text
eo-workflow-lint/
├── src/eo_workflow_lint/
│   ├── cli.py
│   ├── analyzer.py
│   ├── lineage.py
│   ├── models.py
│   ├── suppressions.py
│   ├── catalog.py
│   └── rules/
│       ├── landsat.py
│       ├── sentinel1.py
│       ├── sentinel2.py
│       └── scale.py
├── catalog/
│   └── gee-products.json
├── tests/
├── SPECIFICATION.md
├── README.md
├── LICENSE
└── pyproject.toml
```

---

## 27. v0.2 backlog (non-normative)

Candidates only; none are authorized for v0.1.0 implementation:

- Sentinel-2 Processing Baseline 04.00/harmonization reasoning;
- intent-free Landsat C1->C2 QA migration detection;
- safe mixed-resolution/resampling diagnostics;
- more explicit Sentinel-1 linear/dB domain transitions;
- notebook extraction layer;
- JavaScript frontend;
- STAC/openEO adapters;
- SAR preprocessing semantics beyond S1_GRD domain;
- machine-readable rule manifest for external AI agents.

---

## 28. Freeze declaration

This specification is **FROZEN for v0.1.0 implementation**.

The implementation task is to implement this specification, not redesign it.

If code reveals an ambiguity that materially affects scientific behavior, false-positive risk, deterministic output, or public CLI semantics, implementation MUST stop at that point and report a `SPEC BLOCKER` with:

1. the exact ambiguous clause;
2. the smallest reproducing code example;
3. at least two plausible interpretations;
4. a recommended interpretation;
5. no production code implementing the disputed behavior until the specification is revised.

---

# Appendix A — Reference examples

## A.1 EWL201 FAIL

```python
import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
```

Expected: `EWL201 FAIL`.

## A.2 Correct scaling followed by EWL203 CONDITIONAL

```python
import ee

img = ee.Image("LANDSAT/LC08/C02/T1_L2/LC08_044034_20210508")
sr = img.select("SR_B.").multiply(0.0000275).add(-0.2)
img = img.addBands(sr, overwrite=True)
ndvi = img.normalizedDifference(["SR_B5", "SR_B4"])
```

Expected: `EWL203 CONDITIONAL`; no EWL201.

## A.3 Avoid EWL203 with expression

```python
nir = img.select("SR_B5")
red = img.select("SR_B4")
ndvi = img.expression(
    "(nir - red) / (nir + red)",
    {"nir": nir, "red": red},
)
```

Expected: no EWL203.

## A.4 EWL202 FAIL

```python
thermal = img.select("ST_B10").multiply(0.0000275).add(-0.2)
```

Expected: `EWL202 FAIL`.

## A.5 EWL301 FAIL

```python
s1 = ee.ImageCollection("COPERNICUS/S1_GRD")

def to_db(image):
    return image.log10().multiply(10)

s1 = s1.map(to_db)
```

Expected: `EWL301 FAIL`.

## A.6 S1 float non-trigger

```python
s1 = ee.ImageCollection("COPERNICUS/S1_GRD_FLOAT")

def to_db(image):
    return image.log10().multiply(10)

s1 = s1.map(to_db)
```

Expected: no EWL301.

## A.7 EWL401 CONDITIONAL

```python
stats = img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=aoi,
)
```

Expected: `EWL401 CONDITIONAL`.

## A.8 Explicit scale non-trigger

```python
stats = img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=aoi,
    scale=30,
)
```

Expected: no EWL401.

## A.9 EWL501 FAIL

```python
s2 = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterDate("2023-01-01", "2024-01-01")
)

def mask_clouds(image):
    qa = image.select("QA60")
    return image.updateMask(qa.eq(0))

clean = s2.map(mask_clouds)
```

Expected: `EWL501 FAIL`.

## A.10 EWL502 CONDITIONAL

```python
s2 = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterDate("2021-01-01", "2025-01-01")
)

def mask_clouds(image):
    qa = image.select("QA60")
    return image.updateMask(qa.eq(0))

clean = s2.map(mask_clouds)
```

Expected: `EWL502 CONDITIONAL`.

---

# Appendix B — Normative implementation checklist

Before marking implementation complete, verify:

- [ ] Input is never executed.
- [ ] Runtime has no network dependency.
- [ ] Runtime has no Earth Engine SDK dependency.
- [ ] Same source bytes produce identical JSON across repeated runs.
- [ ] Filesystem path does not appear in JSON.
- [ ] EWL201 fires only with proven raw Landsat C2 SR normalized-difference usage.
- [ ] EWL202 fires only for cross-family use of the two documented Landsat C2 scale/offset pairs.
- [ ] EWL203 does not double-report the EWL201 raw case.
- [ ] EWL301 never fires on S1_GRD_FLOAT.
- [ ] EWL301 requires an explicit recognized 10*log10 pattern.
- [ ] EWL401 checks explicitness, not correctness, of scale/transform.
- [ ] EWL501 wins over EWL502 when the interval is fully inside the gap.
- [ ] Unknown QA60 temporal scope produces coverage information, not a speculative finding.
- [ ] Suppressed findings do not affect verdict or exit threshold.
- [ ] All findings include source provenance.
- [ ] No scientific rule beyond EWL201/202/203/301/401/501/502 exists in v0.1.0.
- [ ] README contains the PASS limitation.
- [ ] Python 3.11/3.12/3.13 CI is green.
- [ ] Ruff is green.
- [ ] Clean-install smoke test is green.
- [ ] `SPEC BLOCKER` policy is enforced during implementation.

