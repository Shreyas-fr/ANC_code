#!/usr/bin/env python3
"""
Downloads standard clean speech and noise audio from the Microsoft MS-SNSD benchmark,
and synthesizes dual-microphone 30mm spatial array evaluation clips at controlled SNR levels.
"""

import os
import sys
import urllib.request
import wave
import numpy as np

CLEAN_SPEECH_URLS = [
    ("clnsp0.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/clean_test/clnsp0.wav"),
    ("clnsp1.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/clean_test/clnsp1.wav"),
    ("clnsp10.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/clean_test/clnsp10.wav"),
    ("clnsp100.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/clean_test/clnsp100.wav"),
]

NOISE_URLS = [
    ("Babble_1.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/noise_test/Babble_1.wav"),
    ("Traffic_1.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/noise_train/Traffic_1.wav"),
    ("Bus_1.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/noise_train/Bus_1.wav"),
    ("Car_1.wav", "https://raw.githubusercontent.com/microsoft/MS-SNSD/master/noise_train/Car_1.wav"),
]

def download_file(url, target_path):
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
        print(f"Already downloaded: {target_path}")
        return
    print(f"Downloading {url} -> {target_path}...")
    urllib.request.urlretrieve(url, target_path)
    print(f"Saved ({os.path.getsize(target_path)} bytes)")

def read_wav(path):
    with wave.open(path, 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
        if sampwidth == 2:
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            samples = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported sample width: {sampwidth}")
        if n_channels > 1:
            samples = samples.reshape(-1, n_channels)[:, 0] # Use primary channel if stereo
        return samples, framerate

def write_wav_stereo(path, mic1, mic2, framerate=16000):
    m1 = np.clip(mic1, -1.0, 1.0)
    m2 = np.clip(mic2, -1.0, 1.0)
    stereo = np.column_stack((m1, m2))
    int16_samples = (stereo * 32767.0).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(int16_samples.tobytes())

def write_wav_mono(path, mono, framerate=16000):
    m = np.clip(mono, -1.0, 1.0)
    int16_samples = (m * 32767.0).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(int16_samples.tobytes())

def apply_acoustic_delay(signal, delay_samples):
    """Exact fractional delay in frequency domain."""
    n = len(signal)
    fft_vals = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n)
    phase_shift = np.exp(-2j * np.pi * freqs * delay_samples)
    return np.fft.irfft(fft_vals * phase_shift, n=n).astype(np.float32)

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clean_dir = os.path.join(base_dir, "data", "eval", "clean")
    noise_dir = os.path.join(base_dir, "data", "eval", "noise")
    bench_dir = os.path.join(base_dir, "data", "eval", "benchmarks")

    os.makedirs(clean_dir, exist_ok=True)
    os.makedirs(noise_dir, exist_ok=True)
    os.makedirs(bench_dir, exist_ok=True)

    print("Step 1: Downloading Clean Speech Samples from MS-SNSD...")
    clean_files = []
    for name, url in CLEAN_SPEECH_URLS:
        dest = os.path.join(clean_dir, name)
        download_file(url, dest)
        clean_files.append(dest)

    print("\nStep 2: Downloading Tactical Noise Samples from MS-SNSD...")
    noise_files = []
    for name, url in NOISE_URLS:
        dest = os.path.join(noise_dir, name)
        download_file(url, dest)
        noise_files.append(dest)

    print("\nStep 3: Synthesizing Dual-Microphone (30mm Array) Benchmark Clips...")
    # Parameters for SIH 26052 Dual-Mic 30mm array:
    # d = 0.03 m, c = 343 m/s, fs = 16000 Hz
    # Broadside target speech: theta = 0 deg => delay = 0.0 samples
    # Endfire directional noise: theta = 90 deg => delta_t = 0.03 / 343 = 8.746e-5 s => 1.399 samples
    delay_samples_endfire = (0.03 / 343.0) * 16000.0

    snr_levels = [-5.0, 0.0, 5.0, 10.0]

    benchmark_manifest = []

    for c_idx, clean_path in enumerate(clean_files):
        c_name = os.path.splitext(os.path.basename(clean_path))[0]
        speech, fs = read_wav(clean_path)

        for n_idx, noise_path in enumerate(noise_files):
            n_name = os.path.splitext(os.path.basename(noise_path))[0]
            noise_raw, n_fs = read_wav(noise_path)

            # Match lengths
            length = min(len(speech), len(noise_raw), 16000 * 8) # Cap at 8 seconds
            if length < 16000:
                continue

            s_clip = speech[:length]
            n_clip = noise_raw[:length]

            # RMS calculation
            s_rms = np.sqrt(np.mean(s_clip ** 2)) + 1e-8
            n_rms = np.sqrt(np.mean(n_clip ** 2)) + 1e-8

            for snr_db in snr_levels:
                # Scale noise to achieve exact desired input SNR
                target_n_rms = s_rms / (10.0 ** (snr_db / 20.0))
                scaled_noise = n_clip * (target_n_rms / n_rms)

                # Acoustic spatial propagation:
                # Target speech at broadside (0 deg): arrives in-phase at mic1 and mic2
                mic1_speech = s_clip
                mic2_speech = s_clip

                # Directional noise at endfire (90 deg):
                # Mic 1 receives raw noise, Mic 2 receives delayed noise
                mic1_noise = scaled_noise
                mic2_noise = apply_acoustic_delay(scaled_noise, delay_samples_endfire)

                mic1_mix = mic1_speech + mic1_noise
                mic2_mix = mic2_speech + mic2_noise

                # Peak normalize to avoid initial clipping
                max_peak = max(np.max(np.abs(mic1_mix)), np.max(np.abs(mic2_mix)), 1e-6)
                if max_peak > 0.95:
                    scale = 0.90 / max_peak
                    mic1_mix *= scale
                    mic2_mix *= scale
                    mic1_speech = mic1_speech * scale

                clip_id = f"{c_name}_{n_name}_snr{int(snr_db):+03d}db"
                mix_out_path = os.path.join(bench_dir, f"{clip_id}_stereo.wav")
                clean_ref_path = os.path.join(bench_dir, f"{clip_id}_clean_ref.wav")

                write_wav_stereo(mix_out_path, mic1_mix, mic2_mix, framerate=fs)
                write_wav_mono(clean_ref_path, mic1_speech, framerate=fs)

                benchmark_manifest.append({
                    "id": clip_id,
                    "stereo_file": mix_out_path,
                    "clean_ref": clean_ref_path,
                    "target_snr": snr_db,
                    "speech_source": c_name,
                    "noise_source": n_name,
                    "duration_s": length / fs,
                })

    print(f"\nGenerated {len(benchmark_manifest)} standardized 30mm spatial benchmark clips in {bench_dir}.")

if __name__ == "__main__":
    main()
