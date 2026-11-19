# SIH 26052 — Stage 9 Frozen Independent Validation Protocol

**Status:** Prepared only; no inference or scoring performed. **Dataset gate: NO-GO** until independent source data are available and provenance-cleared.

## 1. Frozen candidate set

Compare exactly these four configurations on identical recordings:

1. Primary ensemble: DFN3 Step-500 / FullSubNet epoch 58 / GTCRN DNS3 = 0.15 / 0.70 / 0.15.
2. Secondary ensemble: same models = 0.20 / 0.60 / 0.20.
3. Standalone FullSubNet epoch 58.
4. Protected deployed reference: DFN3 Step-500.

No weight search, checkpoint selection, model setting changes, retraining, fine-tuning, or model selection on the independent evaluation set. Use the existing verified model artifacts and implementations unchanged. Preserve per-recording state resets and the approved evaluator methodology.

## 2. Data gate before inference

Before any predictions, require a suitable non-gold dataset with immutable provenance, authorized access, usable clean references, sample rates/channels and recording IDs. Freeze a recording-level manifest, hashes, speaker/session/device IDs, source corpus, collection method, split, noise condition, and input SNR before inference. Reconcile exact file hashes and source identities against prior training inputs, the canonical 590-clip set, and all prior evaluation data. A different folder or filename is not evidence of independence. Do not inspect gold to perform this check; use only pre-existing non-gold exclusion/provenance records. If identity cannot be ruled out, classify the data as unsuitable.

The local LibriSpeech/noise/RIR test manifests are only conditional candidates: their referenced audio is absent, and remote training exposure cannot presently be excluded. The demo files lack provenance. Neither passes this gate.

## 3. Inputs and waveform policy

- Use identical, frozen input recordings for all four comparators; maintain exact clip/recording IDs and clean-reference pairing.
- Preserve native float model outputs throughout objective scoring. Do not clip, peak-normalize, RMS-match, shift, invert polarity, or tune ensemble normalization on the independent evaluation data.
- Keep the two previously flagged alignment-correlation IDs 162 and 436 flagged if the same canonical material is ever used for a non-confirmatory reproduction; do not silently align them. A fresh independent dataset must define any alignment policy before inference.
- Playback/export is a separate path from metric scoring. For audition, create a copy and apply one predeclared safe-output policy (e.g., fixed limiter or PCM saturation with logged settings); never feed that playback copy to metrics. Preserve original float predictions.

## 4. Metrics and statistical analysis

Use the established definitions and evaluator for output SNR, SI-SDR, STOI, and wideband PESQ. Report each metric per recording and as mean with uncertainty. Report joint-pass count and percentage using the project thresholds: output SNR >15 dB, STOI >0.85, and PESQ-WB >2.5. Also report individual-threshold counts.

Report input-SNR subgroup results using the established seven bins and the same bin boundaries as the existing canonical analysis. State sample counts in every bin; do not merge or redefine sparse bins after observing outcomes.

Use paired comparisons on the exact same recordings for each ensemble and FullSubNet versus deployed Step-500. Provide paired bootstrap 95% confidence intervals for all four metrics, with 2,000 resamples and seed 26052. Resample recordings as paired units; do not treat segments from a single recording as independent. Report all candidate comparisons and the full-set denominator. No independent-set metric can be used to change the frozen weights.

## 5. Listening assessment

Only if appropriate independent recordings and suitable listeners are available, conduct a blinded, randomized listening study. Present matched input and outputs for all frozen candidates, with identity/order concealed and playback level handled consistently. Collect separate ratings for speech intelligibility, naturalness, speech distortion/artifacts, and residual noise; include an option for ties/unsure and a no-speech/noise-only flag. Predefine listener eligibility, playback equipment, level, rating scale, sample selection, and analysis before the session. Do not recruit or send project audio to external services without authorization. Listening results supplement, not replace, objective scores.

## 6. Reproducibility package after future approval

Store new results in a new immutable run directory. Record source manifest hash, source-file hashes, model/checkpoint hashes, code revision, environment versions, exact commands, evaluator version, per-recording float prediction hashes, metrics, subgroup summaries, bootstrap seed/results, warnings, runtime, and failures. Verify protected artifacts before and after. Do not overwrite canonical results, checkpoints, manifests, or existing predictions.

## 7. Stop conditions

Stop before inference if provenance, authorization, clean references, input alignment, model compatibility, or non-gold status is uncertain. Stop if the frozen models cannot consume the inputs under the established methodology without changing the evaluator or model settings. Do not access gold, Kaggle, or Raspberry Pi; do not upload project data; do not deploy or promote any result. Following any successful future evaluation, provide results for review before additional experiments or deployment.
