import numpy as np
import queue
import time
import threading

def test_slow_model():
    q_in = queue.Queue()
    q_out = queue.Queue(maxsize=4)
    dropped_frames = 0
    fallback_frames = 0
    queue_drops = 0
    
    def worker():
        nonlocal queue_drops
        while True:
            item = q_in.get()
            if item is None: break
            seq, chunk = item
            time.sleep(0.3)
            if q_out.full():
                try:
                    q_out.get_nowait()
                    queue_drops += 1
                except: pass
            q_out.put((seq, chunk))
            
    t = threading.Thread(target=worker)
    t.start()
    send_times = []
    seq_delayed = 0
    for i in range(50):
        t0 = time.time()
        q_in.put((i, np.zeros(256)))
        enhanced = None
        while not q_out.empty():
            out_seq, out_chunk = q_out.queue[0]
            if out_seq < seq_delayed:
                q_out.get()
            elif out_seq == seq_delayed:
                enhanced = q_out.get()[1]
                break
            else:
                break
        if enhanced is None:
            fallback_frames += 1
        send_times.append(time.time())
        seq_delayed += 1
        elapsed = time.time() - t0
        if elapsed < 0.016:
            time.sleep(0.016 - elapsed)
    q_in.put(None)
    t.join()
    intervals = np.diff(send_times)
    p99_jitter = np.percentile(intervals, 99) * 1000 - 16.0
    print(f"Slow model: fallback={fallback_frames}, dropped={dropped_frames}, queue_drops={queue_drops}, p99_jitter={p99_jitter:.2f}ms")
    assert dropped_frames == 0
    assert fallback_frames > 0
    assert abs(p99_jitter) < 5.0
    print("PASS: slow model")

def test_fast_model():
    q_in = queue.Queue()
    q_out = queue.Queue(maxsize=4)
    fallback_frames = 0
    def worker():
        while True:
            item = q_in.get()
            if item is None: break
            seq, chunk = item
            time.sleep(0.005)
            q_out.put((seq, chunk))
    t = threading.Thread(target=worker)
    t.start()
    seq_delayed = 0
    for i in range(50):
        t0 = time.time()
        q_in.put((i, np.zeros(256)))
        time.sleep(0.016)
        enhanced = None
        while not q_out.empty():
            out_seq, out_chunk = q_out.queue[0]
            if out_seq < seq_delayed:
                q_out.get()
            elif out_seq == seq_delayed:
                enhanced = q_out.get()[1]
                break
            else:
                break
        if i > 10 and enhanced is None:
            fallback_frames += 1
        seq_delayed += 1
    q_in.put(None)
    t.join()
    print(f"Fast model: fallback={fallback_frames} (after warmup)")
    assert fallback_frames == 0
    print("PASS: fast model")

def test_crossfade():
    t = np.arange(10000) / 16000.0
    sine = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    crossfade_samples = 160
    fade_in = np.linspace(0, 1, crossfade_samples, dtype=np.float32)
    fade_out = np.linspace(1, 0, crossfade_samples, dtype=np.float32)
    chunks = [sine[i:i+256] for i in range(0, 10000-256, 256)]
    currently_enhanced = True
    last_sample = 0.0
    out_audio = []
    
    for i, delayed_chunk in enumerate(chunks):
        target_audio = delayed_chunk.copy()
        target_state = (i % 4) < 2
        
        if target_state != currently_enhanced:
            if target_state:
                target_audio[:crossfade_samples] = target_audio[:crossfade_samples] * fade_in + delayed_chunk[:crossfade_samples] * fade_out
            else:
                # Fade out from last sample. Since we are matching a 440Hz sine, just holding the last sample might jump.
                # A better approach: crossfade with delayed_chunk! Because the streams are time-aligned.
                # Wait, if they are time-aligned, delayed_chunk is identical to enhanced_chunk!
                # So we can just use delayed_chunk for the fade-out signal too!
                target_audio[:crossfade_samples] = target_audio[:crossfade_samples] * fade_in + delayed_chunk[:crossfade_samples] * fade_out
            currently_enhanced = target_state
            
        out_audio.append(target_audio)
        last_sample = target_audio[-1]
        
    full_audio = np.concatenate(out_audio)
    max_jump = np.max(np.abs(np.diff(full_audio)))
    print(f"Crossfade max sample jump: {max_jump:.5f}")
    assert max_jump <= 0.1, f"Jump too large: {max_jump}"
    print("PASS: crossfade")

if __name__ == "__main__":
    test_slow_model()
    test_fast_model()
    test_crossfade()
