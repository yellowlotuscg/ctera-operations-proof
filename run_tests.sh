#!/bin/sh
# Run the CTERA offline checks test suite and save a dated receipt.
set -e
cd "$(dirname "$0")"
mkdir -p receipts
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RECEIPT="receipts/test_run_${STAMP}.txt"
{
  echo "CTERA operations proof test receipt"
  echo "Date (UTC): $STAMP"
  echo "Python: $(python3 --version 2>&1)"
  echo "Host: $(uname -s -m 2>/dev/null || true)"
  echo "Command: python3 -m unittest discover -s tests -t . -v"
  echo "------------------------------------------------------------------"
  python3 -m unittest discover -s tests -t . -v
} 2>&1 | tee "$RECEIPT"
echo "Receipt saved to: $RECEIPT"
