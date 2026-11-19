# Vendored FullSubNet source

- Upstream: [Audio-WestlakeU/FullSubNet](https://github.com/Audio-WestlakeU/FullSubNet)
- Pinned commit: `e97448375cd1e883276ad583317b1828318910dc`
- License: MIT; full license text is in `LICENSE`.
- This directory contains only the source modules needed to instantiate and run the official DNS-INTERSPEECH-2020 FullSubNet checkpoint. `fullsubnet/model.py`, `audio_zen/model/base_model.py`, `audio_zen/model/module/sequence_model.py`, `audio_zen/acoustics/mask.py`, and `audio_zen/constant.py` are copied from that commit.
- `audio_zen/acoustics/feature.py` contains only the upstream `drop_band` helper, reproduced for import compatibility. The helper is training-only; the adapter uses inference batch size 1, so the model never enters the upstream branch that invokes it.
- The complete upstream checkout is kept separately at `third_party/FullSubNet/` for reference. Do not edit that checkout as part of project changes.
