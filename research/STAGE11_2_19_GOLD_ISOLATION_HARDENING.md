# Stage 11.2.19 — Gold Isolation Hardening for Dataset Audit Tools

## Finding

Static review of `scripts/audit_sih26_dataset.py` found that `build_existing_hashes_database()` explicitly enumerated and SHA-256 hashed `.wav` files beneath `data/SIH_GOLD_TEST`. The report generator also claimed exact-overlap comparisons against gold even though candidate-file hashes were sampled by deterministic stride. That behavior conflicted with the project’s sealed-gold rule and overstated the audit's coverage.

## Changes

- Removed the gold directory enumeration and hashing path.
- Added fail-closed resolution for the candidate root, metadata file, each metadata-referenced audio path, existing canonical/IoBT hash-reference paths, and output paths.
- Rejects any resolved path with a `SIH_GOLD_TEST` component, any dataset member outside its declared root, and all directory symlinks (including in-root links) rather than silently skipping or traversing them.
- Replaced the recursive glob walk with a symlink-aware `os.walk(..., followlinks=False)` inventory.
- Corrected generated report language: exact hashing is limited to sampled candidate files against local canonical-validation and IoBT sets; SIH gold overlap is not assessed. Reports mark `gold_set_accessed: false` and `gold_overlap_assessed: false`.
- Removed the scanner's unused `scipy.signal` import; the scanner module now imports under the existing project environment without invoking the incompatible SciPy stack.
- The canonical evaluator was not changed.

## Verification and boundaries

`../pc_venv/bin/python -m unittest discover -s tests -v` completed **8/8 passed**. Tests use temporary directories, including a dummy directory named `SIH_GOLD_TEST`; they do not access project gold files. `../pc_venv/bin/python -c 'import scripts.audit_sih26_dataset'` passed. `python3 -m py_compile scripts/audit_sih26_dataset.py tests/test_canonical_gold_guard.py` passed.

The first test invocation exited `1` before executing tests because importing the evaluator hit the existing `pc_venv` SciPy/NumPy incompatibility (`scipy.signal` cannot import `numpy.exceptions.RankWarning`). The path-only test module now stubs the evaluator’s unused `scipy.signal` import; the successful rerun required no dependency install. This does not fix or validate audio evaluation under that environment.

The dataset audit itself was **not run**. No gold, canonical, training, or candidate audio was opened by this work; tests only created and inspected synthetic temporary paths. The changes provide path-level protections in this one audit script, not an OS sandbox for the entire repository. The gold set remains sealed and its overlap status remains unknown.
