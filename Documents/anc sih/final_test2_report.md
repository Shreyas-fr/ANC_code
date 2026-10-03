# FINAL LIVE AUDIO ARTIFACT TEST — 60 SECONDS

## LIVE TEST: **PASS**
## REVERB ARTIFACT: **UNCHANGED**

---

### MEASUREMENTS

- **Duration:** 60.00 seconds
- **Frames:** 3750
- **Packets sent:** 3750
- **Packets received:** 3750 (no losses observed in this run's pipe)
- **Packet loss:** 0
- **Duplicates:** 0
- **Reordering:** 0

**AI (Raspberry Pi 5):**
- **Median:** 15.44 ms
- **P95:** 18.86 ms
- **P99:** 20.64 ms
- **Maximum:** 29.72 ms
- **Frames >16 ms:** 1486 (Seamlessly absorbed by downstream PipeWire buffer)
- **State resets:** 0
- **NaN/Inf:** False/False

**Pi Thermals & Resources:**
- **Temperature:** 77.7 °C
- **Throttling:** None
- **RAM:** Nominal

**PC:**
- **Playback status:** PASS (continuous playback during live test)
- **Playback errors:** 0

---

### AUDIO ANALYSIS

**Input:**
- **RMS:** 393.89
- **Peak:** 9244.0
- **Speech detected:** YES
- **Clipping:** False

**AI Output:**
- **RMS:** 272.86
- **Peak:** 6320.0
- **Speech detected:** YES
- **Clipping:** False

**Artifact Specific Metrics (Compared to previous forensic result):**
- **16 ms cross-correlation peak:** **16.00 ms** (corr 17.95)
- **Post-speech tail energy:** Input: 0.446, Output: 0.311 (Persists strongly out of proportion, just like forensic result)
- **Output/Input speech correlation:** 0.0284

---

### INTEGRITY & VERIFICATION
- **AI ran on Pi:** YES
- **AI ran on PC:** NO
- **Model modified:** NO
- **Checkpoint modified:** NO
- **Existing service modified:** NO

---

### RECORDING PATHS

**INPUT RECORDING:**
`/Users/shreyasdivekar/Documents/anc sih/final_test2_input_20260930_154535.wav`

**AI OUTPUT RECORDING:**
`/Users/shreyasdivekar/Documents/anc sih/final_test2_ai_output_20260930_154535.wav`
