"""Guarantee exactly one live audio-processing process on the Pi."""
from __future__ import annotations

import os
import subprocess
import sys

LOCK_PATH = "/tmp/sih26052_live.lock"
COMPETITORS = (
    "anc_stream.py",
    "pi_ai_network_sender.py",
    "dfn3_stream.py",
    "dfn3_live_sender.py",
    "vs102_ai_stream.py",
    "deep-filter",
)

_lock_fh = None


def pgrep_competitors(exclude_pid: int | None = None) -> list[tuple[int, str]]:
    found = []
    me = exclude_pid if exclude_pid is not None else os.getpid()
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    except Exception:
        return found
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == me:
            continue
        args = parts[1]
        for name in COMPETITORS:
            if name in args:
                found.append((pid, args))
                break
    return found


def acquire_lock(replace: bool = False) -> None:
    global _lock_fh
    competitors = pgrep_competitors()
    # Ignore this file name appearing in the lock-holder's own command after exec
    others = [(pid, args) for pid, args in competitors if str(os.getpid()) not in args]
    if others:
        print("Other live audio processes are running:")
        for pid, args in others:
            print(f"  pid={pid}  {args}")
        if not replace:
            print("Refusing to start. Stop them, disable sih26052-edge.service, or pass --replace.")
            sys.exit(2)
        for pid, args in others:
            print(f"Sending SIGTERM to pid {pid}")
            try:
                os.kill(pid, 15)
            except OSError as e:
                print(f"  kill failed: {e}")

    import fcntl
    _lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"Could not acquire {LOCK_PATH}. Another live sender holds the flock.")
        sys.exit(2)
    _lock_fh.write(str(os.getpid()) + "\n")
    _lock_fh.flush()
    print(f"Single-instance lock acquired: {LOCK_PATH} pid={os.getpid()}")
