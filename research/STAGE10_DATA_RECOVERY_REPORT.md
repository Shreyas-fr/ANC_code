# SIH 26052 — Stage 10 Data Recovery and Acquisition Audit

**Date:** 2026-11-13  
**Disposition:** Audit and planning only. No download, cache extraction, restoration, mixing, inference, scoring, training, upload, Kaggle/Pi access, gold access, staging, or commit occurred. Existing manifests and protected artifacts were not modified.  
**Confirmatory-validation decision:** **NO-GO** for LibriSpeech clean-test, noise-test, and RIR-test candidates at this time.

## Executive result

The clean speech and room-response audio referenced by the manifests are not present in their declared project paths or in the documented local source tree. The noise manifests likewise point to missing raw audio paths. A local Hugging Face cache contains full Arrow-format ESC-50 and UrbanSound8K dataset snapshots, which may contain the corresponding audio payloads, but no individual file has been restored, mapped to the manifest, or SHA-256 verified. Their local cache metadata reports an empty license, homepage, and citation, and a generated 0.0.0 cache version rather than an immutable upstream revision. Extraction would require a compatible Arrow reader that is not installed in the available project environments; no dependency was installed.

Even if the cache audio were extractable, noise alone does not provide clean-reference speech pairs. The remaining MUSAN, DEMAND, and RIR components are missing. More importantly, prior training inputs cannot be conclusively reconciled: project records say training data were attached through external Kaggle datasets, while the full mounted snapshots are not present locally. A local training-source inventory has LibriSpeech dev-clean items with 3 of the 30 speaker IDs from candidate clean_test.csv. It does not prove the exact utterances were used, but speaker-level exposure cannot be excluded. The canonical set itself has no source IDs, so exact recording overlap cannot be checked against it. Per the Stage 10 rule, any unresolved exposure makes a candidate unsuitable for confirmatory validation.

No source is cleared for confirmatory use. No licensing or authorization status is inferred from a local cache.

## Phase A — Recoverability findings

### LibriSpeech clean test

- Manifest: data/clean_manifests/clean_test.csv; 3,197 rows; declared 16 kHz; total 40,511.04 seconds (11.2531 h), median 14.01 s; 30 source_recording_id values.
- Declared paths use data/raw/librispeech/LibriSpeech/train-clean-100/...
- The declared root data/raw/librispeech is absent. 0/3,197 referenced paths exist; 0 manifest SHA-256 values could be checked.
- No LibriSpeech dataset cache was found under the inspected Hugging Face dataset/hub cache roots.
- The umbrella source inventory data/clean_manifests/DFN3_V2_SIH_DEFENCE_AUGMENTED_manifest.csv contains 5,323 LibriSpeech dev-clean rows and shares 3 speaker IDs with clean_test.csv. Since the inventory is not an executed-run file list, this is a potential speaker overlap, not proof of exact training exposure.

**Decision: NO-GO.** Audio is absent, licensing/authorization is not evidenced in the local manifest, and same-speaker exposure plus incomplete training snapshots prevent clearance.

### Noise test

- Manifest: data/clean_manifests/noise_test.csv; 242 rows; declared 16 kHz; total 91,436.76 seconds (25.3991 h), median 152.16 s; 81 source_recording_id values. Source counts: MUSAN 147, ESC-50 64, DEMAND 16, UrbanSound8K 15. Noise classes: nonstationary 202, impulsive 24, stationary 16.
- Declared raw paths under data/raw/noise are absent. 0/242 manifest paths exist; 0 manifest SHA-256 values could be checked.
- Local cache leads: Hugging Face Arrow cache for ashraq/esc50 has 2,000 examples and 882,246,992 bytes of dataset data; danavery/urbansound8K has 8,732 examples and 7,089,581,985 bytes. These are cached dataset containers, not restored manifest files. No row mapping or per-file digest comparison was possible in the installed environment. The cache’s dataset_info.json reports version 0.0.0 and blank license/homepage/citation fields. Its hash-like directory component is a builder fingerprint, not verified source provenance.
- No local MUSAN or DEMAND cache was found. No individual recording was extracted or copied.
- The sibling split manifests show zero file-hash/path/source-recording-ID overlap between train, validation, and test. Prior model training exposure to the full mounted corpora is unresolved; local training records describe a large processed-audio input and prior Kaggle mounts.

**Decision: NO-GO.** Only two partial cache leads exist, neither individually verified or authorization-cleared; the other 163 noise recordings are unavailable; noise alone cannot support the required clean-reference metrics; and prior exposure cannot be excluded.

### RIR test

- Manifest: data/clean_manifests/rir_test.csv; 6,300 rows; declared 16 kHz; total 7,350 seconds (2.0417 h), median 1 s; 21 source_recording_id room IDs; source datasets SLR26/SLR28.
- Declared roots data/raw/rir_slr26 and data/raw/rir_slr28 are absent. 0/6,300 paths exist; 0 manifest SHA-256 values could be checked.
- No matching local Hugging Face cache entry or other documented cache was found. Channel count and capture details are not in the manifest.
- The local train/val/test RIR split manifests have zero exact hash/path/source-recording-ID intersections, but prior training use of these source datasets is not ruled out by available run inputs.
- The RIR manifest lacks a locally recorded licensing/authorization field.

**Decision: NO-GO.** No waveform files are recoverable from the inspected local sources, and training exposure and licensing are unresolved.

## Other local sources and evaluation records

- data/eval_samples contains ten short clean/noisy/enhanced triplets and one streaming sample. Source recording, speaker, collection, license, and prior-use records are absent. It is not a substitute for the manifest candidate.
- runs/sih26052_canonical_validation contains the existing 590-clip benchmark and references, but it is repeatedly used and its clean/noise/RIR source IDs are N/A. It is excluded as an independent set.
- Project audit docs/CODEX_REPOSITORY_AUDIT.md and research/SIH26052_RESEARCH_STATUS.md record that training corpora were mounted as Kaggle inputs and the complete source audio is not evidenced locally. Kaggle was not accessed in this audit.
- Protected gold files/manifests were not enumerated, opened, hashed, or compared. No gold independence claim is made.
- Hash check summary: for the candidate raw manifests, 0 clean + 0 noise + 0 RIR audio files were present at declared paths, and 0 individual source hashes were verified. There were no mismatches because no candidate source files were available to compare.

Detailed row counts, paths, availability, and status are in research/STAGE10_RECOVERABLE_DATA_INVENTORY.csv. Unresolved provenance and authorization questions are in research/STAGE10_PROVENANCE_GAPS.csv.

## Phase C — Alternative data plan

If a new set is approved, use the acquisition proposal in research/STAGE10_NEW_DATA_COLLECTION_PLAN.md. It specifies consented, independently captured speech/noise, exact clean references or controlled mix pairs, source-level split separation, calibrated SNR annotations, transient/impulsive conditions, privacy, licensing, and immutable provenance. No participant has been contacted and no collection has begun.

## Final recommendation and stop

**LibriSpeech clean-test: NO-GO. Noise-test: NO-GO. RIR-test: NO-GO.** The ESC-50/UrbanSound8K cache contents are partial recovery leads only, not individually verified authorized files. The principal blockers are missing source recordings, unverified per-file hashes, missing license/authorization evidence, incomplete training-input inventories, unresolved speaker/source overlap, and unavailable canonical source IDs.

To reconsider these candidates, an authorized operator would need to approve extraction or restoration, provide authoritative license/source records and complete prior training/evaluation manifests, and then permit a non-gold overlap audit. Alternatively, approve a new recording study following the collection plan. This report stops before downloading, restoring/extracting, collecting, mixing, generating predictions, or evaluating data.
