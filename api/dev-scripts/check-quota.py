"""Check Gemini API free-tier quota by making a minimal test call.

Usage:
    docker compose exec api python3 /app/check_gemini_quota.py [model_name]

Examples:
    docker compose exec api python3 /app/check_gemini_quota.py
    docker compose exec api python3 /app/check_gemini_quota.py gemini-2.0-flash

Exits 0 if Gemini is available, 1 if rate-limited, 2 on other error.
"""

import json
import os
import sys

from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not set")
    sys.exit(2)

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-2.0-flash"

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model=MODEL,
        contents="Reply with a single word: OK",
        config={"temperature": 0, "max_output_tokens": 10},
    )
    print(f"✓ Gemini quota available (model={MODEL}) — responded: {response.text.strip()}")
    sys.exit(0)

except Exception as e:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        print(f"✗ Gemini quota EXHAUSTED:")
        # Pretty-print the key info from the error
        try:
            err_data = json.loads(msg[msg.index("{"):msg.rindex("}")+1])
            for violation in err_data.get("error", {}).get("details", []):
                if violation.get("@type", "").endswith("QuotaFailure"):
                    for v in violation.get("violations", []):
                        print(f"  - {v.get('quotaMetric', '?')}: limit={v.get('limit', '?')}")
                if violation.get("@type", "").endswith("RetryInfo"):
                    print(f"  Retry delay: {violation.get('retryDelay', '?')}")
        except Exception:
            print(f"  {msg[:300]}")
        sys.exit(1)
    else:
        print(f"? Unexpected error: {msg[:200]}")
        sys.exit(2)
