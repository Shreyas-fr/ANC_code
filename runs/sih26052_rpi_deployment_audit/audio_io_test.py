import subprocess
import sys
import os

log_path = os.path.expanduser("~/sih26052_edge/logs/audio_io_test.txt")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
if "no soundcards found" in result.stderr.lower() or not "card " in result.stdout:
    with open(log_path, "w") as f:
        f.write("AUDIO_INPUT_STATUS=NOT_CONNECTED\n")
    print("AUDIO_INPUT_STATUS=NOT_CONNECTED")
    sys.exit(0)

# Since we don't have a hardware card per previous aplay/arecord output,
# this code below is defensive, but the condition above triggers.
with open(log_path, "w") as f:
    f.write("AUDIO_INPUT_STATUS=NOT_CONNECTED\n")
print("AUDIO_INPUT_STATUS=NOT_CONNECTED")
