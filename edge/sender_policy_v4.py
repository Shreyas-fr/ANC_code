import collections
import numpy as np

class SenderPolicyV4:
    def __init__(self, D_samples=9024, jitter_ms=300):
        self.D = D_samples
        self.J_frames = int(round(jitter_ms / 16.0))
        self.J_samples = self.J_frames * 256
        self.total_delay = self.D + self.J_samples
        
        self.chain_resets = 0
        self.late_frames = 0
        self.fallback_frames = 0
        
        self.raw_history = []
        
        crossfade_samples = 160
        self.fade_in = np.linspace(0, 1, crossfade_samples, dtype=np.float32)
        self.fade_out = np.linspace(1, 0, crossfade_samples, dtype=np.float32)
        self.currently_enhanced = True
        self.last_val = 0.0
        
    def enqueue(self, seq, chunk, t_ms, backlog_ms):
        self.raw_history.extend(chunk)
        if backlog_ms > 2000.0:
            self.chain_resets += 1
            return True # signal to reset chain
        return False
        
    def get_output(self, seq, out_q):
        seq_target = seq - self.J_frames
        enhanced = None
        
        if seq_target >= 0:
            while out_q:
                out_seq, out_chunk = out_q[0]
                if out_seq < seq_target:
                    out_q.popleft()
                    self.late_frames += 1
                elif out_seq == seq_target:
                    enhanced = out_q.popleft()[1]
                    break
                else:
                    break
                    
        # EXACT sample-level delayed raw fallback
        # we need 256 samples that arrived (D + J) samples ago
        # The current seq is processing the chunk that just arrived.
        # But wait, seq * 256 is the start of the current chunk in raw_history?
        # Actually, if we just use raw_history:
        # The first sample of the current chunk is at seq * 256.
        # We want the sample that arrived (D + J) ago: seq * 256 - (D + J).
        start_idx = seq * 256 - self.total_delay
        if start_idx >= 0 and start_idx + 256 <= len(self.raw_history):
            delayed_chunk = np.array(self.raw_history[start_idx : start_idx + 256])
        else:
            delayed_chunk = np.zeros(256, dtype=np.float32)
            if start_idx + 256 > 0 and start_idx + 256 <= len(self.raw_history):
                valid_len = start_idx + 256
                delayed_chunk[-valid_len:] = self.raw_history[:valid_len]
            
        target_state = False
        target_audio = delayed_chunk.copy()
        
        if enhanced is not None:
            target_audio = enhanced
            target_state = True
        elif seq_target >= 0:
            self.fallback_frames += 1
            
        if target_state != self.currently_enhanced:
            if target_state:
                # Switching F -> E
                old_source = delayed_chunk
            else:
                # Switching E -> F
                shift = self.last_val - delayed_chunk[0]
                old_source = delayed_chunk + shift
                
            target_audio[:160] = target_audio[:160] * self.fade_in + old_source[:160] * self.fade_out
            self.currently_enhanced = target_state
            
        out = np.clip(target_audio, -0.99, 0.99).astype(np.float32)
        self.last_val = out[-1]
        return out
