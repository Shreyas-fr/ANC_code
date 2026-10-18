#!/usr/bin/env python3
"""Interactive or environment-driven SSH key copy utility for Raspberry Pi."""
import getpass
import os
import sys
import pexpect

def main():
    target = os.environ.get("SIH_PI_TARGET") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not target:
        target = input("Enter target Pi user@host (e.g. shreyas@shreyas.local): ").strip()
        if not target:
            print("Error: Target host is required.", file=sys.stderr)
            sys.exit(1)

    key_path = os.environ.get("SIH_KEY_PATH", sys.argv[2] if len(sys.argv) > 2 else "./rpi_key.pub")
    password = os.environ.get("SIH_PI_PASSWORD") or getpass.getpass(f"Enter password for {target}: ")

    cmd = f"ssh-copy-id -o StrictHostKeyChecking=no -i {key_path} {target}"
    child = pexpect.spawn(cmd, encoding="utf-8")
    child.logfile = sys.stdout

    index = child.expect(["password:", pexpect.EOF, pexpect.TIMEOUT])
    if index == 0:
        child.sendline(password)
        child.expect(pexpect.EOF)
        print("Done!")
    elif index == 1:
        print("Key already present or EOF reached.")
    else:
        print("Connection timed out.")

if __name__ == "__main__":
    main()
