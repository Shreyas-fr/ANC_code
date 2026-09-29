import pexpect
import sys

child = pexpect.spawn('ssh-copy-id -o StrictHostKeyChecking=no -i ./rpi_key.pub shreyas@shreyas.local', encoding='utf-8')
child.logfile = sys.stdout

index = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT])
if index == 0:
    child.sendline('Shreyas@0405')
    child.expect(pexpect.EOF)
    print("Done!")
elif index == 1:
    print("EOF")
else:
    print("TIMEOUT")
