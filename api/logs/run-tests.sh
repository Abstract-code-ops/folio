#!/usr/bin/env bash
# Run pytest and capture a concise error summary.
# Usage: bash /app/logs/run-tests.sh [optional pytest args]
#
# Full output goes to:  /app/logs/pytest-output-<timestamp>.log
# Error summary goes to: /app/logs/pytest-errors.log (overwritten each run)

set -euo pipefail

cd /app
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_LOG="/app/logs/pytest-output-${TIMESTAMP}.log"
ERROR_LOG="/app/logs/pytest-errors.log"

echo "🧪 Running pytest ..."
echo "   Full output: ${OUTPUT_LOG}"
echo "   Errors only: ${ERROR_LOG}"

# Run pytest, capture everything
set +e
pytest "$@" --tb=short -v 2>&1 | tee "${OUTPUT_LOG}"
EXIT_CODE=$?
set -e

# Extract just the FAILURES / ERRORS section into the error log
{
  echo "=== pytest run ${TIMESTAMP} ==="
  echo "Exit code: ${EXIT_CODE}"
  echo ""
  # Print lines between "= FAILURES =" and the next "===" or end
  awk '
    /^=+ FAILURES =+$/     { in_fail=1; print; next }
    /^=+ ERRORS =+$/       { in_err=1; print; next }
    /^=+ short test summary/ { in_summary=1 }
    /^=+ [0-9]+ passed/   { if(in_fail||in_err) print ""; in_fail=0; in_err=0; in_summary=0 }
    in_fail || in_err || in_summary { print }
  ' "${OUTPUT_LOG}"
  echo ""
  echo "Exit code: ${EXIT_CODE}"
} > "${ERROR_LOG}"

echo ""
echo "✅ Done (exit ${EXIT_CODE})"
echo "   Error summary → ${ERROR_LOG}"
exit ${EXIT_CODE}
