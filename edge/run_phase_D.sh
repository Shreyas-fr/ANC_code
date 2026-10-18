#!/bin/bash
lsof -ti :5005,5007 | xargs kill -9 2>/dev/null

echo "Starting Mac recorders..."
./pc_venv/bin/python udp_record.py --port 5007 --out ~/anc_tests/D_in.wav --duration 65 > mac_D_in.log 2>&1 &
REC_IN_PID=$!
./pc_venv/bin/python udp_record.py --port 5005 --out ~/anc_tests/D_out.wav --duration 65 > mac_D_out.log 2>&1 &
REC_OUT_PID=$!

echo "Starting Pi Phase D..."
ssh -o StrictHostKeyChecking=no shreyas@"${SIH_PI_IP:?Error: SIH_PI_IP required}" 'bash /tmp/run_phase_D_pi.sh' > pi_D.log 2>&1

echo "Waiting for Mac recorders..."
wait $REC_IN_PID
wait $REC_OUT_PID
echo "Phase D complete."
