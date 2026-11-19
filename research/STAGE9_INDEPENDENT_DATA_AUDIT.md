# SIH 26052 — Stage 9 Independent Data Audit

**Audit date:** 2026-11-13  
**Decision:** **NO-GO for confirmatory independent validation; preflight only.**  
**Scope:** Authorized local project manifests, local non-gold audio, and existing project documentation. No gold paths or contents were inspected. No inference, training, model/checkpoint change, Kaggle access, Pi access, upload, staging, or commit occurred.

## Decision summary

The workspace has metadata for a potentially useful held-out synthetic evaluation recipe, but it does not contain the referenced source audio. The likely candidate is the manifest-declared LibriSpeech test speaker split combined with the declared noise-test and RIR-test splits. Those manifests declare disjoint file hashes and recording IDs from their sibling train and validation manifests. This is useful split evidence, but it does not prove independence from the exact corpora mounted in prior Kaggle runs or every prior evaluation: the training inputs are not fully present locally, and the 590-clip canonical manifest has no source recording IDs (all clean/noise/RIR IDs are N/A). The canonical set has been repeatedly used and is not a fresh holdout.

All referenced raw paths under data/raw/librispeech, data/raw/noise, and data/raw/rir_slr26/rir_slr28 are absent. The legacy data/manifests paths are absent too. No candidate can currently supply the same input recordings and clean references needed for an independent objective comparison. No candidate meets the Stage 9 confirmatory gate today.

Conditional candidate manifests:

- Clean speech: data/clean_manifests/clean_test.csv — 3,197 LibriSpeech utterances, declared 16 kHz, 30 source recording/speaker IDs, 11.25 hours by manifest duration.
- Noise: data/clean_manifests/noise_test.csv — 242 recordings across MUSAN, ESC-50, DEMAND and UrbanSound8K, declared 16 kHz, 81 source recording IDs, 9.40 hours by manifest duration.
- Room responses: data/clean_manifests/rir_test.csv — 6,300 simulated SLR26/SLR28 responses, declared 16 kHz, 21 room/source IDs, 2.04 hours by manifest duration.

These could form a synthetic clean-reference set only after the audio is restored and provenance is reconciled against exact prior training/evaluation inputs. Noise condition labels exist; per-mixture input SNR labels do not exist until a fixed mixing plan creates mixtures. Channel counts are not recorded. The manifests describe clean/noise/RIR components, not captured noisy speech. The clean test paths point to LibriSpeech train-clean-100 and use source recording IDs disjoint from sibling train/val manifests, but the corpus family is also present in the project source inventory. Prior training sources and remote mounted inputs are not fully available to exclude exposure.

## Candidate findings

### Manifest-declared held-out synthetic recipe — conditional, not cleared

The data/clean_manifests split manifests have zero pairwise overlap by exact file_hash, file_path, and source_recording_id among clean train/validation/test, noise train/validation/test, and RIR train/validation/test. This supports local split construction. It does not establish independence from the canonical set or prior Kaggle training because canonical source IDs are unavailable and actual mounted training snapshots are not local. Every referenced clean/noise/RIR test audio path was absent at audit time. Sample rates and duration statistics below are manifest claims, not measurements from loaded audio; channel count is unavailable. No per-mixture SNR annotation exists because no paired mixtures exist in this candidate.

### data/eval_samples — unsuitable

There are 31 files: ten clean/noisy/enhanced triplets and one streaming test file. The 30 triplet files are mono 16 kHz, 48,000 samples (3 seconds), PCM-16; the streaming file is mono 16 kHz, 47,872 samples (2.992 seconds), PCM-16. No speaker/recording IDs, noise labels, SNR annotations, or collection provenance were found in the inspected local records. No WAV byte-hash matched the canonical clean/noisy WAV files, but this does not prove source-recording independence. For IDs 2 and 6, files named clean and noisy are byte-identical, making their status as realistic noisy/clean pairs uncertain. This folder is too small and provenance-opaque for confirmation.

### Canonical 590 clips — not independent

The frozen canonical manifest has 590 three-second mono 16 kHz clips (29.5 minutes total), with clean references and target-SNR strata. Its origins are EXISTING_PROXY (148) and IoBT_GUNFIRE (442), but all clean/noise/RIR source IDs are N/A. It has been repeatedly used for model selection and comparison, so it is development evidence, not a fresh holdout. It was not rerun or modified for this audit.

### Other local manifests — unsuitable as delivered

The legacy data/manifests inventory declares LibriSpeech clean audio and ESC-50/AudioSet/UrbanSound/nonstationary noise, but none of 48,000 referenced paths exist locally; older manifests have no recording hashes. The clean train/val/test speaker IDs are disjoint, but cannot establish exposure against prior model training and provide no waveforms. Defence-gunfire train/val/test manifests include source-group/session/device/firearm metadata, but audio paths are absent, sample rate is UNKNOWN, duration values are not numeric in the expected field, and these are noise-only recordings rather than clean-reference speech/noise pairs.

## Overlap and leakage assessment

- **Canonical overlap:** No exact WAV-byte hash match was found between data/eval_samples and canonical clean/noisy WAVs. This is not source-level independence proof. Canonical source IDs are all N/A, so recording linkage is unavailable.
- **Declared split overlap:** Clean/noise/RIR train/val/test manifests show zero exact file-hash, path, or source-recording-ID intersections across their local partitions. This is a manifest-level control, not proof that prior model runs used only those train rows.
- **Prior model exposure:** Exact remote Kaggle dataset snapshots and source audio are unavailable locally. The repository audit states training data were mounted as external Kaggle datasets and complete source audio is not locally evidenced. Exposure to prior model training therefore cannot be ruled out for the candidate corpora.
- **Previously used evaluation data:** Canonical is known to be reused. The eval_samples source identities and prior-use history are undocumented. No byte duplicates to canonical were found, but no stronger conclusion is justified.
- **Gold isolation:** This audit intentionally did not enumerate, read, hash, or compare gold-set files or manifests. It makes no claim that candidate data have been proven disjoint from gold. Gold remains unused and inaccessible.

## What is missing to reach GO

1. Restore authorized source audio for candidate manifests, preserving listed hashes/IDs, or acquire newly collected non-gold data outside all training and prior evaluation corpora.
2. Provide immutable snapshots/manifests for every prior training input and previously used evaluation source, allowing exact-file and source-recording/speaker overlap checks without opening gold.
3. Recover provenance/source IDs for the canonical proxy clips so recording-level overlap can be checked.
4. Preferably collect independent speech with consent/provenance, speaker/session/device IDs, clean references in a controlled condition, and paired noisy recordings or reproducible captured noise conditions. Record sample rate/channels, noise class, input SNR, and licensing/consent.
5. Pre-register the pairing/mixing recipe and split before generating model predictions. Do not use gold or the repeatedly used canonical set for selection/tuning.

The frozen protocol is in research/STAGE9_VALIDATION_PROTOCOL.md. Do not generate predictions until a dataset passes the source-level overlap gate and receives explicit approval. No evaluation or deployment work was started.
