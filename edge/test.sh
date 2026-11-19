#!/bin/bash
THROT="0xd0000"
THROT_DEC=$(( THROT ))
if [ $(( THROT_DEC & 1 )) -ne 0 ]; then
    echo "THROTTLE_BIT0"
else
    echo "NO_BIT0"
fi
