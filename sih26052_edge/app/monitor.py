import time
import psutil
import csv
import os
import numpy as np

class PerformanceMonitor:
    def __init__(self, log_path, deadline_ms=16.0):
        self.log_path = log_path
        self.deadline_ms = deadline_ms
        self.frame_times = []
        self.deadline_misses = 0
        self.nan_inf_count = 0
        self.state_resets = 0
        self.dropped_frames = 0
        self.underruns = 0
        self.overruns = 0
        
        self.start_time = time.time()
        self.last_log_time = time.time()
        
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "frames_processed", "p50_ms", "p95_ms", "p99_ms", "max_ms",
                "deadline_misses", "cpu_percent", "ram_mb", "temp_c", "throttled",
                "nan_inf_count", "state_resets", "dropped_frames", "underruns", "overruns"
            ])

    def record_frame(self, duration_ms):
        self.frame_times.append(duration_ms)
        if duration_ms > self.deadline_ms:
            self.deadline_misses += 1

    def record_anomaly(self, nan_inf=False, state_reset=False, dropped=False, underrun=False, overrun=False):
        if nan_inf: self.nan_inf_count += 1
        if state_reset: self.state_resets += 1
        if dropped: self.dropped_frames += 1
        if underrun: self.underruns += 1
        if overrun: self.overruns += 1

    def _get_temp(self):
        try:
            res = os.popen("vcgencmd measure_temp").readline()
            return float(res.replace("temp=", "").replace("'C\n", ""))
        except:
            return 0.0

    def _get_throttle(self):
        try:
            return os.popen("vcgencmd get_throttled").readline().strip()
        except:
            return "unknown"

    def flush_log(self, force=False):
        current_time = time.time()
        if not force and current_time - self.last_log_time < 5.0:
            return
            
        if len(self.frame_times) == 0:
            return

        p50 = np.percentile(self.frame_times, 50)
        p95 = np.percentile(self.frame_times, 95)
        p99 = np.percentile(self.frame_times, 99)
        max_t = np.max(self.frame_times)
        
        cpu = psutil.cpu_percent()
        ram = psutil.Process().memory_info().rss / (1024 * 1024)
        temp = self._get_temp()
        throttle = self._get_throttle()

        with open(self.log_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                current_time, len(self.frame_times), p50, p95, p99, max_t,
                self.deadline_misses, cpu, ram, temp, throttle,
                self.nan_inf_count, self.state_resets, self.dropped_frames, self.underruns, self.overruns
            ])
            
        self.frame_times = []
        self.last_log_time = current_time
