# Hispa-Syng v1.0 regression tests

This directory contains a regression suite for the Spanish and English editions. Analytical tests use temporary synthetic geometries and data rather than the operational observation database. The release-hygiene check requires the complete MITECO/GSHHS resource files to be present, but these synthetic tests do not run a full operational analysis on those resources.

The suite checks, among other points:

- density is calculated as `N / Area_mar_km2` in individuals per marine km²;
- zero/invalid marine areas are rejected;
- direct, MITECO-fallback, nearest and unassigned point-to-grid cases behave as expected;
- canonical MITECO regional membership is fixed before analytical cell assignment and remains invariant across 1/5/10-km analytical resolutions; points lacking a direct subdivision intersection use the official 10-km reference grid within its fixed regional tolerance;
- cells without positive effective marine area cannot receive analytical observations, while a MITECO-confirmed coastal GSHHS false zero can retain a positive fallback area and direct assignment;
- the persistent GSHHS marine-area cache supports `miss`, `hit` and `partial_hit` states and invalidates a changed cell geometry;
- conservation popup species summaries do not create `Area_mar_km2_x/_y` collisions;
- conservation priority rejects isolated/high-LCBD records and one-year abundance bursts, while validating persistent-occurrence, multi-year diversity, and exceptional-diversity pathways;
- exported/presentation density fields are rounded to at most two decimals while non-density analytical fields are not;
- the regression suite remains free of the `GeoSeries.notna()` warning pattern and does not request the unsupported `semibold` font weight;
- `_common.js` is declared as package data in both Python packages;
- all Python source files compile syntactically without generating `.pyc` files.
- `sampling_event_id` is deterministic, independent of species and row order, groups normalized observer/date/1-m-position records consistently, and does not merge rows with missing observer identity;
- common analytical status codes preserve the distinction between a calculable numeric zero and `insufficient_data` / `not_estimable`.
- temporal annual and period rates use unique `n_sampling_events` rather than row counts as the primary denominator, while record-based rates remain sensitivity fields;
- the primary temporal GLM applies the event offset and Pearson overdispersion correction with `phi >= 1`, and rare/short series are marked `descriptive_only`;
- symmetric temporal-change components are invariant to equivalent unit scaling, preserve change direction separately, and return zero for 0-to-0 comparisons;
- the canonical cell temporal signal uses official MITECO `grid_id`, stays within 0–1 and behaves safely with fewer than two comparison periods;
- spline predictions are generated only for inferentially supported species and are standardized to observation events.
- the integrated technical report preserves the distinction between record volume and proxy-event observation intensity and explicitly states that proxy events are not true sampling effort.

From the project root, after the normal Hispa-Syng environment has been created, run:

```text
RUN_REGRESSION_TESTS.bat
```

or directly:

```text
.venv\Scripts\python.exe tests\run_regression_tests.py
```

The tests are quality-control tools only; they do not modify the analytical pipeline or any user dataset.

## Community-analysis regressions

The suite also checks event-based cell support, Hellinger row-scale invariance, dual Jaccard/Hellinger LCBD with BH-FDR, regional IndVal BH-FDR, Lingoes correction of a known non-Euclidean Bray-Curtis matrix, reproducible Mantel-Spearman inference, and the absence of an inferential p-value for the non-independent pairwise distance-decay regression. `tests/_community_integration_smoke.py` runs as part of the suite for both editions.
## Functional-diversity regressions

The suite checks functional-space geometry, common dimensionality, preservation of zero-distance FEve links, convex-hull-centroid FDiv, Anderson-corrected FDis, and safe non-estimability of FRic when regional species support is too small. `tests/_functional_integration_smoke.py` runs the complete functional block in either edition, verifies explicit trait coverage/exclusion diagnostics, confirms that incidence-based and abundance-weighted results remain distinct, and checks the critical invariant that a species present only in `Datos_data/traits.xlsx` cannot alter functional results.

## Official-MITECO multiscale regressions

The suite checks the multiscale invariants defined for the official multiscale analysis: direct assignment to official 1/5/10-km MITECO grids, `n_sampling_events` as the minimum-support unit, incidence/Jaccard LCBD with BH-FDR separated from the LCBD>=P90 magnitude criterion, Mantel-Spearman distance-decay, and persistence defined on the finest available official support independently of the user-selected resolution. It also verifies that a fine hotspot displaced from the centre of a coarser cell is retained by real polygon relations, that a missing/non-estimable scale can never be redefined as “all scales”, and that multiscale support is derived exclusively from official MITECO geometries. `tests/_multiscale_integration_smoke.py` runs as part of the suite for both editions.

The conservation regression also verifies the separation between unchanged strategic priority areas and evidence-anchored operational conservation areas: disconnected 1-km evidence clusters remain separate, empty bridge cells are not introduced, parent containment is enforced, and the pre-existing conservation popup payloads remain intact.

## Reproducible security and validation records

The complete suite runs 32 subprocesses. To retain each command, exit code, duration, log, loaded dependency version and Python-source SHA-256, use an output directory outside the project:

```text
.venv\Scripts\python.exe tests\run_regression_tests.py --report-dir ..\Hispa-Syng_validation
```

Security tests cover owner/access separation, malformed containers, private generation, rejection of direct protected CLI output into Resultados, encryption before publication, automatic interrupted-run recovery, idempotent protection, disk/write failures, locked files, and abrupt rotation termination before and after commit. The coordinator test uses synthetic child-process output fixtures; it is not an operational scientific run. Existing encrypted copies remain readable with their original keys after rotation.

On Windows, the lifecycle test additionally performs a native current-user DPAPI roundtrip. It does not certify another Windows user's inability to decrypt: that check requires a second account. The packaged validation records were produced on Linux; native DPAPI, Windows ACL enforcement and cross-account isolation remain unverified there. Their recorded status must not be interpreted as PASS. The bilingual parity criterion is exact equality of the serialized synthetic snapshots after the rounding defined in the snapshot test, not complete equivalence on the operational database.

En español: la validación incluida usa datos sintéticos y registra 32 procesos. El cifrado y la recuperación se verifican con fallos simulados; las pruebas nativas de Windows y entre cuentas quedan pendientes. Los hashes identifican el contenido comprobado y no son una firma del propietario.

The SIN_RESOURCES variant validates the core package only. Set HISPA_REQUIRE_RESOURCES=1 to require all external resource paths. A partial Resources directory always fails validation. Metadata export tests preserve original identifiers, comments, observers and URLs in both editions. Recovery tests cover concurrent operations, abrupt process exit and publication cleanup.

Public-product policy is shared identically by both editions and the coordinator. Tests render the actual aggregate templates, reject observation metadata and point geometries, check SHA-256 registration after copy/link rewriting, encrypt unregistered HTML/JS/image files, and verify complete per-file classification audits. Download-document bytes in web-builder tests are synthetic fixtures. Copy-distribution tests require owner authentication and successful recovery before creating any destination or recovery credential.

Public geometry tests exercise official protected-area Point/MultiPoint records and mixed polygon collections in open and protected modes. Observation points and individual metadata remain rejected. Display-only removal of non-polygon fragments preserves polygon area and input geometry.

## Security menu navigation

Run `python tests/_security_menu.py` to check 44 scenarios across ES and EN. The check covers open/protected menus, state transitions, access-management routing and cancellation before any copy destination or credential is created. This is a separate UI check; the regression runner still performs 32 subprocess checks. Native Windows dialogs and DPAPI are outside this menu test.
