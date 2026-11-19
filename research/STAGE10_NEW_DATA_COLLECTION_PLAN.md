# SIH 26052 — New Independent Recording Collection Plan

**Status:** Proposal only. No participant contact, recruitment, recording, purchase, download, or collection has begun. Obtain explicit approval and institutional/privacy review before any collection.

## Purpose and frozen comparison

Create a non-gold, provenance-documented evaluation set to test the frozen Stage 8 candidates and baselines without tuning:

- Primary ensemble: DFN3 Step-500 / FullSubNet epoch 58 / GTCRN DNS3 at 0.15 / 0.70 / 0.15.
- Secondary ensemble: same models at 0.20 / 0.60 / 0.20.
- Standalone FullSubNet epoch 58.
- Protected deployed DFN3 Step-500.

No model training, parameter search, checkpoint selection, or independent-set tuning is part of this plan.

## Recording design

### Speech and clean references

- Recruit consenting adult speakers under an approved protocol; include varied accents and speaking styles without recording unnecessary sensitive information.
- Record read and spontaneous speech in a quiet controlled room. Keep unprocessed, uncompressed master files and metadata.
- Capture mono or multichannel PCM at 48 kHz, 24-bit as the archival master; record the microphone, interface, gain, room, distance, orientation, and calibration. Preserve channel layout. For evaluation, make a deterministic, documented mono 16 kHz derivative using one fixed resampler after the split is frozen.
- A clean reference must correspond exactly to the utterance and time span used for scoring. Prefer controlled additive mixing from the clean master for objective metrics, since it preserves an exact clean target. Keep any real acoustic noisy capture as a separate realism subset; do not claim its clean reference is sample-synchronous unless the recording design makes that true.
- Log pseudonymous speaker ID, session ID, utterance ID, device ID, date bucket, room, and operator. Store the identity key separately with restricted access; the model evaluation manifest should contain pseudonyms only.

### Noise and acoustics

- Record or license independent noise beds with a calibrated chain and documented provenance. Cover stationary and nonstationary noise, including ventilation, road/vehicle, machinery, wind, water, crowd/restaurant, and public-space ambience.
- Include transient and impulsive events relevant to speech enhancement, such as knocks, claps, impacts, alarms, and safely sourced firearm-like effects only when lawful and approved. Record event onset/offset and speech overlap; avoid hazardous recording activity.
- Maintain noise source ID, session/device/location pseudonyms, event labels, duration, channels, sample rate, gain, licensing/consent, and any edit history. Avoid identifiable bystander speech; obtain consent or reject the recording.
- Capture room impulse responses separately only with a documented measurement procedure, equipment, room/device IDs, and rights. Simulated RIRs must be labeled synthetic and identify the source set/seed.

## Pairing and SNR ground truth

- Pre-register a deterministic mixing plan before producing any evaluation inputs. Pair clean utterances with independent noise recordings at fixed input-SNR targets spanning the intended operating range; use a balanced, predeclared grid such as -10, -5, 0, 5, 10, and 15 dB, plus a clean/no-noise condition if useful.
- Define SNR from the active clean speech interval and the scaled noise component with a written formula; retain the original clean/noise stems and scaling gain so every label is reproducible.
- Apply any reverberation or channel filtering identically according to a predeclared condition, and retain the exact clean target convention. Do not change mixtures after model outputs are seen.
- For real noisy recordings without an exact clean counterpart, report listening results or separately justified intrusive metrics; do not create a synthetic clean reference by assumption.

## Independence and split policy

- Assign speakers, noise source recordings, rooms, and recording sessions to train/validation/test at source-recording level before processing. For confirmatory validation, reserve test speakers and test noise sessions that are absent from every project training and tuning input. Ideally collect the confirmatory test corpus after model configurations and analysis are frozen.
- Avoid leakage from identical utterances, source recordings, repeated takes, derived crops, room captures, and transformed copies. Keep a manifest of raw file hashes and source identity links. Store split assignment at speaker/session/source-group level and audit exact hashes plus identity-level overlap.
- Freeze the confirmatory manifest and analysis plan before producing any model predictions. The sealed gold set remains separate and untouched.

## Consent, privacy, rights, and security

- Obtain written informed consent covering recording, speech-enhancement research, evaluation, retention period, access controls, and any intended sharing. Provide withdrawal handling where applicable.
- Complete institutional ethics/privacy review and jurisdiction-specific consent, data-protection, and retention review before collection.
- Use pseudonymous IDs; do not include names, phone numbers, addresses, or free-text personal details in audio filenames or public reports. Encrypt restricted identity mappings and limit access.
- Use project-owned recordings or obtain written licenses that explicitly permit research use, processing, model evaluation, storage, and any planned redistribution. Track license/consent per source and per derivative. Do not assume that public availability means permission to redistribute or upload.
- Keep all audio local and access controlled. Do not send recordings to cloud services or external listeners without separate authorization and appropriate consent.

## Minimum release checklist before any evaluation

1. Written authorization, consent/ethics, privacy, and license records approved.
2. Raw masters and fixed derivatives cataloged with cryptographic hashes.
3. Per-recording provenance, speaker/session/device/source IDs and clean/noise pairing recorded.
4. Channel/sample-rate metadata verified by reading files; input SNR labels recomputed from retained stems.
5. Recording-level split frozen and audited against prior training/evaluation manifests, without accessing gold.
6. Confirmatory set demonstrably disjoint from model-development data and canonical evaluation inputs.
7. Stage 9/Stage 8 metric and listening protocol pre-registered; candidate models and ensemble weights frozen.
8. Explicit approval received before recording, processing/mixing, generating predictions, or evaluating.
