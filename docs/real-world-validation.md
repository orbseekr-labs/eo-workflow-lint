# Real-world validation

This page records how `eo-workflow-lint` behaves on real, public Google Earth Engine
Python code. The v0.2.0 release notes summarised the benchmark in one line. This page
publishes all of it, with every repository, pinned commit, file, line, expected
result and observed result, so anyone can check the claims and re-run them.

- **Validation date:** 2026-09-28 (original benchmark: 2026-09-22)
- **Tool versions compared:** v0.1.2 (tag `v0.1.2`), v0.2.0 (tag `v0.2.0`), v0.2.1
  (this revision)
- **Machine-readable manifest:** [`validation/manifest.json`](../validation/manifest.json)
- **Rendered results of this run:** [`validation/results/2026-09-28.md`](../validation/results/2026-09-28.md)
- **Runner:** [`validation/run_benchmark.py`](../validation/run_benchmark.py) (developer
  tool, needs network, not part of the offline test suite)

No third-party source code is stored in this repository. The manifest records only
repository names, full commit SHAs, file paths, line numbers and SHA-256 digests of the
files.

## What this benchmark does and does not show

The benchmark asks two questions:

1. On real code that a human reviewer confirmed contains a pattern a rule is meant to
   report, does the tool report it at the right call? (**candidates**)
2. On real code written by experts, or on a large set of official samples, does the tool
   report anything it should not? (**controls and sweeps**)

It is **not** an accuracy estimate. The repositories were found by targeted search for
Landsat Collection 2 Level-2 scaling followed by `normalizedDifference()`, not sampled
at random. The sample is small. We therefore report counts, never a percentage.

## Methodology

1. **Candidate selection (2026-09-22).** Public GitHub repositories were searched for
   Earth Engine Python code that loads a Landsat Collection 2 Level-2 collection, applies
   the documented surface-reflectance scale and offset (`0.0000275`, `-0.2`), and then calls
   `normalizedDifference()` or an equivalent index. A repository was counted only when a
   human read the whole lineage (dataset → scaling → index → downstream use) and confirmed
   it. Text matches alone were not counted. That produced 8 EWL203 candidates and 1 expert
   control across 9 repositories (12 files).
2. **Pinning.** Each repository is pinned to a full commit SHA. On 2026-09-28 every
   original SHA was still the HEAD of its default branch, so the 2026-09-22 files and the
   files re-verified here are byte-identical. The SHA-256 of each listed file is in the
   manifest, and the runner refuses to report if a digest differs.
3. **Human review (2026-09-28).** For every target we recorded the file and line of the
   call the rule should report, and the reason. We also recorded whether the specification's
   static model can prove the lineage at all (`static_scope: in` / `out`). For `out`, we
   recorded the specific gap. The reviewer notes are in the manifest.
4. **Execution.** Every listed file, plus every `.py` file in each pinned repository
   ("sweep"), was linted with `check --format json` by each tool version. The linter
   was run as a subprocess and never imports or executes the analysed code.
5. **Classification.** A target counts as *detected* only if the expected reason code is
   reported at the expected line. Every other finding from any version was read by a
   human and labelled `true_positive` or `false_positive`. A finding without a label would
   be reported as `unadjudicated`. There are none.

### Provenance of the original benchmark

The v0.2.0 release notes list only counts. The commit that introduced v0.2.0
(`2d34e51`) names four of the repositories (gee-urban-clim, Deforestation-Detection,
geeet, stpred) and the Open-ET control. The complete list below, including the short SHAs
and the file each candidate was judged on, comes from the maintainers' benchmark working
record of 2026-09-22. It was re-checked against GitHub on 2026-09-28: every repository,
full SHA and file exists as recorded, and re-running v0.1.2 and v0.2.0 reproduces the
recorded results exactly (0/8 and 4/8, with EWL203 at the same lines).

## Repositories

| Case | Repository | Commit | Role | Files judged |
|---|---|---|---|---|
| gee-urban-clim | [nlebovits/gee-urban-clim](https://github.com/nlebovits/gee-urban-clim) | `c845a45ca517d1a4ea5ee186cff9751e5a03f6f8` | candidate (original) | `src/heat/utils.py` |
| deforestation-detection | [Ojas-Rohatgi/Deforestation-Detection](https://github.com/Ojas-Rohatgi/Deforestation-Detection) | `f7f474fb869267c6414c29ab92a9a6b2671ddb7c` | candidate (original) | `backend.py` |
| geeet | [kaust-halo/geeet](https://github.com/kaust-halo/geeet) | `ae40313bd890adcac4c03b69eb7939fb154a2434` | candidate (original) | `geeet/eepredefined/landsat.py` |
| stpred | [FaranIdo/stpred](https://github.com/FaranIdo/stpred) | `c31b7b8ea2f0e1e93a5fe8da00ca2510a6b07ff9` | candidate (original) | `dataset/download_ee_data.py` |
| snapp | [Yingjie4Science/SNAPP](https://github.com/Yingjie4Science/SNAPP) | `56edc73cd5bb6888844803d7bdfe11a7fb901f96` | candidate (original) | `src/inputs/ndvi/ndvi_gee.py` |
| urban-heat-stress | [AS-youKnow/urban-heat-stress](https://github.com/AS-youKnow/urban-heat-stress) | `72ef427ca4ff2614cf21597548761857c9a87b70` | candidate (original) | `module1_data_ingestion.py` |
| rusle | [nriveras/RUSLE](https://github.com/nriveras/RUSLE) | `3338daf5efd0717c3db4fcb299e8d21decafc179` | candidate (original) | `00_scripts/rusle_utils.py`, `app/services/rusle_calculator.py`, `app/services/gee_service.py` |
| inferes | [Critical-Infrastructure-Systems-Lab/InfeRes](https://github.com/Critical-Infrastructure-Systems-Lab/InfeRes) | `5e148bb14af243ee6499579c7b7a87725ad9c41c` | candidate (original) | `src/ndwi_processing.py`, `src/satellite_composite.py` |
| openet-core-landsat | [Open-ET/openet-core](https://github.com/Open-ET/openet-core) | `ab923aa7daf56cb9bbb1fe01c4295a3a1fc380d7` | expert control (original) | `openet/core/landsat.py` |
| crop-analysis | [SylviaChebetEMTH/Crop-Analysis](https://github.com/SylviaChebetEMTH/Crop-Analysis) | `bb0924a79c061263fbee3b53e0e0c90e92c9886f` | candidate (added 2026-09-28) | `backend/NDVI.py`, `backend/app.py` |
| openet-geesebal-ndvi | [Open-ET/openet-geesebal](https://github.com/Open-ET/openet-geesebal) | `809bc36d136998d8e9a14086063c2490acc43276` | candidate (added 2026-09-28) | `openet/geesebal/openet_landsat.py`, `openet/geesebal/openet_image.py` |
| openet-ssebop | [Open-ET/openet-ssebop](https://github.com/Open-ET/openet-ssebop) | `f6a97a2731111b0d3bd8cf1b85a2dccc23ae4c1d` | expert control (added) | whole repository |
| openet-ptjpl | [Open-ET/openet-ptjpl](https://github.com/Open-ET/openet-ptjpl) | `f62fe24446c16d79e8a9710767de7c06d795a7af` | expert control (added) | whole repository |
| openet-sims | [Open-ET/openet-sims](https://github.com/Open-ET/openet-sims) | `20914c03c62c202bd068e4e887f0ad269e641920` | expert control (added) | whole repository |
| earthengine-community-python-samples | [google/earthengine-community](https://github.com/google/earthengine-community) | `dfc91467c24f095eba140c33e7f2a66fd1264fee` | blind sweep (added) | `samples/python/**` (868 files) |

We also swept every `.py` file in all of the above repositories at the pinned commit.
That is 1,115 files in total; the vendored virtualenv in Crop-Analysis was excluded.

## Candidate results

"In scope" means the specification's static model can prove the lineage. "Out of scope"
means it cannot, for the stated reason. The tool then correctly stays silent and the miss
is a known coverage gap, not a wrong answer.

| Case | File:line | Expected | Scope | v0.1.2 | v0.2.0 | v0.2.1 |
|---|---|---|---|---|---|---|
| gee-urban-clim | `src/heat/utils.py:70` | EWL203 | in | missed | **detected** | **detected** |
| gee-urban-clim | `src/heat/utils.py:143` | EWL203 | in | missed | **detected** | **detected** |
| deforestation-detection | `backend.py:54` | EWL203 | in | missed | **detected** | **detected** |
| geeet | `geeet/eepredefined/landsat.py:66` | EWL203 | in | missed | **detected** | **detected** |
| stpred | `dataset/download_ee_data.py:107` | EWL203 | in | missed | **detected** | **detected** |
| snapp | `src/inputs/ndvi/ndvi_gee.py:83` | EWL203 | out: dataset ID is a function parameter reached by plain calls | missed | missed | missed |
| snapp | `src/inputs/ndvi/ndvi_gee.py:87` | EWL203 | out: same | missed | missed | missed |
| urban-heat-stress | `module1_data_ingestion.py:212` | EWL203 | out: dataset ID from an imported config attribute; composite passed through a plain call | missed | missed | missed |
| urban-heat-stress | `module1_data_ingestion.py:215` | EWL203 | out: same | missed | missed | missed |
| rusle | `00_scripts/rusle_utils.py:443` | EWL203 | out: scaled collection flows through a function return and a parameter | missed | missed | missed |
| rusle | `app/services/rusle_calculator.py:332` | EWL203 | out: scaled collection comes from another module | missed | missed | missed |
| inferes | `src/ndwi_processing.py:52` | EWL203 | out: pipeline in another module imports the helpers; `SR_B.*` selector not recognised (§8.7) | missed | missed | missed |
| inferes | `src/ndwi_processing.py:76` | EWL203 | out: same | missed | missed | missed |
| crop-analysis | `backend/NDVI.py:33` | EWL502 | in | **detected** | **detected** | **detected** |
| openet-geesebal-ndvi | `openet/geesebal/openet_landsat.py:20` | EWL203 | out: bands renamed and scaled with per-platform list constants in another module | missed | missed | missed |
| openet-geesebal-ndvi | `openet/geesebal/openet_landsat.py:97` | EWL203 | out: same | missed | missed | missed |

Every detection is a `CONDITIONAL` EWL203 (or EWL502) finding on the intended call. In
every candidate file, the target findings are the only findings.

### Why each candidate is a candidate

Short versions of the reviewer notes in the manifest:

- **gee-urban-clim.** `LANDSAT/LC08/C02/T1_L2` is mapped through the module-level
  `apply_scale_factors` (lines 39–42, which rescales both SR and ST bands in place) and a
  QA cloud mask. `normalizedDifference(["SR_B5","SR_B4"])` then runs on scaled SR, in
  `calculate_lst` (70) and in a lambda (143). Nothing handles negative inputs. The NDVI
  feeds fractional vegetation, emissivity and LST.
- **Deforestation-Detection.** The same module-level helper is used inside
  `fetch_rgb_ndvi`. After a `median()` composite, NDVI is computed on scaled SR (54) and
  used as a classifier input.
- **geeet.** A library `collection()` merges LE07/LC08/LC09 C2 L2, maps `scale_SR`, then
  `add_ndvi`, which calls `normalizedDifference` on scaled SR (66). The later
  `clamp(-1, 1)` does not address masking of negative inputs.
- **stpred.** The collection is chosen per year, then a nested SR scaling helper is
  applied. The NDVI band names are chosen per platform in an `if`/`else`, and
  `normalizedDifference([nir, red])` runs on scaled SR (107).
- **SNAPP.** L5/L7/L8/L9 C2 L2 are scaled, cloud-masked and passed to
  `normalizedDifference` (83 for L5/L7, 87 for L8/L9) for a yearly NDVI p90.
- **urban-heat-stress.** A scaled LC08 C2 L2 median composite is passed to
  `compute_indices`, which computes NDVI (212) and NDBI (215) with
  `normalizedDifference`.
- **RUSLE.** `load_landsat8()` scales LC08 C2 L2. `calculate_c_factor` takes a median
  composite and computes NDVI for the C factor, in both the script (443) and the app (332).
- **InfeRes.** Scaled LC09/LC08/LE07/LT05 C2 L2 go into NDWI via `normalizedDifference`
  (52, 76), which then feeds an Otsu water mask. The following `unmask(-2)` fills masked
  output after the fact. It does not stop negative inputs from being masked.
- **Crop-Analysis (added).** `COPERNICUS/S2_SR_HARMONIZED` is filtered to
  2022-01-01..2022-12-31 and cloud-masked with `select('QA60').eq(0)` (33). QA60 cloud
  polygons were not produced from late January 2022 until February 2024, so for most of
  that year the mask removes nothing. The interval overlaps the documented gap but is not
  contained by it, which is exactly EWL502. `backend/app.py` in the same repository is a
  negative control and correctly produces no findings: its Sentinel-2 indices use band
  arithmetic, every region reduction passes `scale=30`, and it never uses QA60.
- **openet-geeSEBAL (added).** Scaled Landsat SR, with bands renamed to `nir`/`red`/`green`,
  is passed to `normalizedDifference` (20, 97) without clamping, followed by `unmask(0)`.
  Pixels with a negative input therefore silently become 0. EWL203 semantics apply, but the
  renamed-band, list-constant, cross-module shape is outside the static model. We record
  this case as coverage-unresolved rather than hiding it.

### Expert controls

- **Open-ET/openet-core** (`openet/core/landsat.py`, the original control). The code
  applies `max(0)` before `normalizedDifference` (96) and a comment explains why. The
  negative-input choice is explicit, so no EWL203 is expected, and none is reported by any
  version.
- **Open-ET/openet-ssebop, openet-ptjpl, openet-sims** (added, whole repositories). These
  use the same explicit `max(0)` pattern. v0.1.2 and v0.2.0 reported EWL401 on
  `utils.py` helpers that call `reduceRegion(**rr_params)`, where `rr_params` contains
  `'scale'`. Those findings are **false positives** (see below). v0.2.1 reports nothing in
  any of the four Open-ET model repositories or in openet-core.

## Findings outside the targets

| Finding | Where | Versions | Label |
|---|---|---|---|
| EWL401 | `openet/core/utils.py:678, 688` | v0.1.2, v0.2.0 | false positive: `reduceRegion(**rr_params)` with `'scale'` in the dict |
| EWL401 | `openet/ssebop/utils.py:46, 56` | v0.1.2, v0.2.0 | false positive: same shape |
| EWL401 | `openet/ptjpl/utils.py:44, 54` | v0.1.2, v0.2.0 | false positive: same shape |
| EWL401 | `openet/sims/utils.py:44, 54` | v0.1.2, v0.2.0 | false positive: same shape |
| EWL401 | `openet/geesebal/utils.py:80, 90` | v0.1.2, v0.2.0 | false positive: same shape |
| EWL401 | geeet `geeet/eepredefined/reducers.py:28` | v0.1.2, v0.2.0 | false positive: `reduceRegions(..., **reducer_kws)`; the omission cannot be proven |
| EWL401 | earthengine-community `samples/python/apidocs/ee_featurecollection_flatten.py:26` | v0.1.2, v0.2.0 | false positive: `reduceRegions(**{..., 'scale': 5000})` |
| EWL401 | earthengine-community `apidocs/ee_image_clip.py:44`, `guides/features04.py:166`, `guides/reducers00_overview.py:48` | all | true positive: no `scale` or `crsTransform` given |
| EWL201 | earthengine-community `apidocs/ee_image_normalizeddifference.py:22` | all | true positive: NDVI on an unscaled C2 L2 SR image |
| EWL201 | earthengine-community `guides/image_collections085.py:52` | all | true positive: NDVI computed on the raw image before the scaling function runs |
| EWL203 | earthengine-community `guides/arrays06.py:33` | all | true positive: NDVI on correctly scaled SR without an explicit negative-input choice |

One file, `samples/python/guides/quickstart.py`, contains an IPython `%pip` line. It is
not valid Python, so every version exits with code 2 ("invalid input"). That is the
documented CLI contract, not a finding.

The 12 false positives share one root cause: EWL401 ignored `*`/`**` argument
unpacking. v0.2.1 fixes it without changing any rule (see the specification
Revision history, §10.5). Between v0.2.0 and v0.2.1, exactly those 12 findings
disappear and no other finding in the 1,115 files changes.

## Metrics

| Metric | v0.1.2 | v0.2.0 | v0.2.1 |
|---|---|---|---|
| Original EWL203 candidate repositories (human-verified) | 8 | 8 | 8 |
| — detected (finding on the intended call) | 0 | 4 | 4 |
| — missed | 8 | 4 | 4 |
| All candidate cases incl. 2 added 2026-09-28 | 10 | 10 | 10 |
| — detected | 1 | 5 | 5 |
| — missed, lineage outside the static model (coverage-unresolved) | 9 | 5 | 5 |
| — missed although in static scope (would be a bug) | — | 0 | 0 |
| Target call sites (16 total) detected | 1 | 6 | 6 |
| Unrelated false positives (all 1,115 files) | 12 | 12 | **0** |
| Adjudicated true positives outside the targets | 6 | 6 | 6 |
| Unadjudicated findings | 0 | 0 | 0 |

The "in static scope" labels describe the v0.2.x specification. v0.1.2 missed the four
now-detected candidates because v0.1.x could not prove their lineage: module-level
helpers were invisible inside functions, `ST_B.*` overwrites erased the SR scale state, and
`median()`, `merge()` and per-platform band names were not modelled. v0.2.0 addressed
exactly those gaps.

## Limitations

- **Small, targeted sample.** 10 candidate cases and 5 expert repositories do not
  support a detection-rate or precision estimate. We deliberately report no percentage.
- **Not a held-out set.** The 8 original candidates are a development and regression set, not an independent held-out test:
  - The v0.2.0 lineage-coverage work was developed against them. For example, v0.2.0 was the first version to detect `nlebovits/gee-urban-clim` `src/heat/utils.py`.
  - The project also opened questions about the suspected pattern on several candidate repositories before and after that release (e.g. `nlebovits/gee-urban-clim#9`, `AS-youKnow/urban-heat-stress#1`/`#2`, `Yingjie4Science/SNAPP#7`, `FaranIdo/stpred#3`, `Ojas-Rohatgi/Deforestation-Detection#1`, `SylviaChebetEMTH/Crop-Analysis#1`, `kaust-halo/geeet#38`).
  - The "0/8 → 4/8" change therefore shows improved coverage on known cases, not generalisation.
  - The official-sample sweep (868 files), added on 2026-09-28, was not used during development.
- **Review is internal.** Candidate labels were made within the project: an initial
  review (2026-09-22) and an independent re-review of every target line (2026-09-28), both
  AI-assisted and maintainer-directed. The repository authors have not confirmed them.
- **Rule coverage is uneven.** The candidates exercise EWL203 (and one EWL502).
  EWL201, EWL202, EWL301 and EWL501 have no real-world *candidate* in this benchmark.
  EWL201 and EWL401 appear only as true positives in the official-sample sweep.
- **Known coverage gaps** remain by design. The specification rules out interprocedural
  flow (function returns and parameters), cross-module imports, dataset IDs from
  configuration attributes, the `SR_B.*` selector, and renamed-band pipelines. Five
  candidate cases stay undetected for these reasons.
- **Line granularity.** A detection must match the exact reported line of the call. A
  multi-line call is reported at its first line.
- **Moving targets.** Results are only claimed for the pinned commits. Later commits in
  these repositories may differ.

## Re-running

```bash
pip install -e ".[dev]"
python validation/run_benchmark.py \
  --linter current=eo-workflow-lint \
  --linter v0.1.2=/path/to/a/v0.1.2/venv/bin/eo-workflow-lint
```

The runner fetches each pinned commit into `validation/.cache/` (ignored by git) with a
shallow, sparse `git fetch`. It verifies file digests, then writes `results.json` and
`results.md` to `validation/.cache/results/`. `--offline` reuses an existing cache. A
v0.1.2 executable can be installed from the tag in a separate virtual environment, for
example `pip install "git+https://github.com/orbseekr-labs/eo-workflow-lint.git@v0.1.2"`.
