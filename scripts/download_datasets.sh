#!/bin/bash
set -e

# Antigravity V1 Dataset Downloader
# This script downloads the raw archives into data/raw/
# IMPORTANT: This will download >50GB of data. Run on a server with sufficient space.

RAW_DIR="data/raw"
mkdir -p "$RAW_DIR/librispeech"
mkdir -p "$RAW_DIR/musan"
mkdir -p "$RAW_DIR/rir_slr26"
mkdir -p "$RAW_DIR/rir_slr28"
mkdir -p "$RAW_DIR/demand"

echo "======================================"
echo "1. Downloading LibriSpeech"
echo "======================================"
cd "$RAW_DIR/librispeech"
curl -L -O -C - https://www.openslr.org/resources/12/train-clean-100.tar.gz
curl -L -O -C - https://www.openslr.org/resources/12/dev-clean.tar.gz
# Uncomment for 360h dataset
# curl -L -O -C - https://www.openslr.org/resources/12/train-clean-360.tar.gz
tar -xzf train-clean-100.tar.gz
tar -xzf dev-clean.tar.gz
cd ../../..

echo "======================================"
echo "2. Downloading MUSAN"
echo "======================================"
cd "$RAW_DIR/musan"
curl -L -O -C - https://openslr.org/resources/17/musan.tar.gz
tar -xzf musan.tar.gz
cd ../../..

echo "======================================"
echo "3. Downloading SLR26 (Simulated RIRs 16kHz)"
echo "======================================"
cd "$RAW_DIR/rir_slr26"
curl -L -O -C - https://www.openslr.org/resources/26/sim_rir_16k.zip
unzip -qo sim_rir_16k.zip
cd ../../..

echo "======================================"
echo "4. Downloading SLR28 (Real/Sim RIRs and Isotropic noise)"
echo "======================================"
cd "$RAW_DIR/rir_slr28"
curl -L -O -C - https://www.openslr.org/resources/28/rirs_noises.zip
unzip -qo rirs_noises.zip
cd ../../..

echo "======================================"
echo "5. Downloading DEMAND (16kHz versions)"
echo "======================================"
# DEMAND from Zenodo
cd "$RAW_DIR/demand"
FILES=("DKITCHEN_16k.zip" "DLIVING_16k.zip" "DWASHING_16k.zip" "NFIELD_16k.zip" "NPARK_16k.zip" "NRIVER_16k.zip" "OHALLWAY_16k.zip" "OMEETING_16k.zip" "OOFFICE_16k.zip" "PCAFETER_16k.zip" "PRESTO_16k.zip" "PSTATION_16k.zip" "SPSQUARE_16k.zip" "STRAFFIC_16k.zip" "TBUS_16k.zip" "TCAR_16k.zip" "TMETRO_16k.zip")

for FILE in "${FILES[@]}"; do
    curl -f -L -O -C - --retry 3 --retry-delay 5 "https://zenodo.org/records/1227121/files/$FILE"
    unzip -qo "$FILE"
    sleep 2
done
cd ../../..

echo "All raw downloads complete!"
