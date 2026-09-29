#!/bin/bash
set -e

echo "=== DETERMINISM TEST ==="

echo "Run 1: Generating manifests and SIH_GOLD_TEST..."
venv/bin/python scripts/build_clean_manifests.py > /dev/null
venv/bin/python scripts/freeze_gold_test.py > /dev/null
HASH_1=$(cat data/clean_manifests/SIH_GOLD_TEST_hash.txt)

echo "Run 2: Regenerating manifests and SIH_GOLD_TEST..."
venv/bin/python scripts/build_clean_manifests.py > /dev/null
venv/bin/python scripts/freeze_gold_test.py > /dev/null
HASH_2=$(cat data/clean_manifests/SIH_GOLD_TEST_hash.txt)

if [ "$HASH_1" = "$HASH_2" ]; then
    echo "DETERMINISM TEST: PASS"
    echo "Hash: $HASH_1"
    exit 0
else
    echo "DETERMINISM TEST: FAIL"
    echo "Hash 1: $HASH_1"
    echo "Hash 2: $HASH_2"
    exit 1
fi
