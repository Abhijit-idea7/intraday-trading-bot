"""
test_webhook.py
---------------
Sends a single test webhook to stocksdeveloper.in and prints the response.
Safe to run any time — if market is closed, Zerodha will reject the order
but the webhook response still tells us connectivity is working.

Run locally:
    python test_webhook.py

Run via GitHub Actions:
    Actions tab → "Test Webhook" → Run workflow
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

STOCKSDEVELOPER_URL     = "https://tv.stocksdeveloper.in/"
STOCKSDEVELOPER_API_KEY = os.getenv("STOCKSDEVELOPER_API_KEY", "bbd4eadb-105b-4f19-8dd9-b571e33ec832")
STOCKSDEVELOPER_ACCOUNT = os.getenv("STOCKSDEVELOPER_ACCOUNT", "AbhiZerodha")

# Test payload — 1 share of TATAMOTORS, intraday BUY
payload = {
    "command": "PLACE_ORDERS",
    "orders": [
        {
            "variety":     "REGULAR",
            "exchange":    "NSE",
            "symbol":      "TATAMOTORS",
            "tradeType":   "BUY",
            "orderType":   "MARKET",
            "productType": "INTRADAY",
            "quantity":    1,
        }
    ],
}

params = {
    "apiKey":  STOCKSDEVELOPER_API_KEY,
    "account": STOCKSDEVELOPER_ACCOUNT,
    "group":   "false",
}

print("=" * 50)
print("Sending test webhook to stocksdeveloper.in...")
print(f"URL    : {STOCKSDEVELOPER_URL}")
print(f"Account: {STOCKSDEVELOPER_ACCOUNT}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("=" * 50)

try:
    resp = requests.post(STOCKSDEVELOPER_URL, params=params, json=payload, timeout=10)
    print(f"\nHTTP Status : {resp.status_code}")
    print(f"Response    : {resp.text}")

    if resp.status_code == 200:
        print("\n✓ Webhook reached stocksdeveloper.in successfully.")
        print("  (If market is closed, Zerodha will reject the order — that is expected.)")
    else:
        print("\n✗ Unexpected status code. Check API key and account name.")

except requests.RequestException as e:
    print(f"\n✗ Connection failed: {e}")
    print("  Check internet connectivity and the stocksdeveloper URL.")
