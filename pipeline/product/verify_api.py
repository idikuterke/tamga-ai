import subprocess
import time
import requests
import json
import sys
from pathlib import Path

# Path configurations
product_dir = Path("C:/Users/pc/gokturk_pipeline/pipeline/product")
log_path = product_dir / "usage_log.jsonl"

# Clean existing log if any
if log_path.exists():
    log_path.unlink()

print("Starting production Uvicorn server...")
proc = subprocess.Popen(
    ["python", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=str(product_dir),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Wait for server to start and load the PyTorch model
print("Waiting 8 seconds for model to load...")
time.sleep(8)

url_translate = "http://127.0.0.1:8000/translate"
url_home = "http://127.0.0.1:8000/"

test_results = {}

try:
    # 1. Unauthenticated request -> 401
    print("\n--- Test 1: Unauthenticated request ---")
    r1 = requests.post(url_translate, json={"text": "bodun"})
    print(f"Status Code: {r1.status_code}, Detail: {r1.json().get('detail')}")
    test_results["test1_401"] = (r1.status_code == 401)

    # 2. Authenticated request with invalid key -> 401
    print("\n--- Test 2: Invalid API key request ---")
    r2 = requests.post(url_translate, json={"text": "bodun"}, headers={"X-API-Key": "invalid_key"})
    print(f"Status Code: {r2.status_code}, Detail: {r2.json().get('detail')}")
    test_results["test2_invalid_key"] = (r2.status_code == 401)

    # 3. Authenticated request with valid key -> 200
    print("\n--- Test 3: Valid API key request ---")
    headers_valid = {"X-API-Key": "gokturk_api_key_handev"}
    r3 = requests.post(url_translate, json={"text": "bodun"}, headers=headers_valid)
    print(f"Status Code: {r3.status_code}, Input: {r3.json().get('input')}, Mode: {r3.json().get('mode')}")
    # Print the runic text as hex representation to avoid encoding crashes
    runic_text = r3.json().get('gokturkce_text', '')
    runic_hex = [hex(ord(c)) for c in runic_text]
    print(f"Gokturkce text (codepoints): {runic_hex}")
    test_results["test3_valid_key"] = (r3.status_code == 200 and len(runic_text) > 0)

    # Check usage log
    print("\nChecking usage_log.jsonl...")
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        print(f"Log lines found: {len(lines)}")
        for idx, line in enumerate(lines):
            # Parse and print keys and ASCII values only to avoid console crash
            entry = json.loads(line.strip())
            print(f"Log entry {idx + 1}: Key={entry.get('api_key')}, Endpoint={entry.get('endpoint')}, Status={entry.get('status_code')}, Success={entry.get('success')}")
        test_results["test3_log_created"] = (len(lines) >= 3)
    else:
        print("Log file NOT found!")
        test_results["test3_log_created"] = False

    # 4. Send 35 requests to trigger rate limit -> 429
    print("\n--- Test 4: Rate Limiting (35 requests) ---")
    success_count = 1 if r3.status_code == 200 else 0
    limit_count = 0
    other_count = 0
    
    # Send 34 more requests
    for i in range(1, 35):
        r_lim = requests.post(url_translate, json={"text": "bodun"}, headers=headers_valid)
        if r_lim.status_code == 200:
            success_count += 1
        elif r_lim.status_code == 429:
            limit_count += 1
            if limit_count == 1:
                print(f"First Rate Limit Hit at request {i + 1}: Status 429, Detail: {r_lim.json().get('detail')}")
        else:
            other_count += 1
        time.sleep(0.05)
        
    print(f"Results: Total Requests = 35. 200 (Success) = {success_count}, 429 (Rate Limited) = {limit_count}, Other = {other_count}")
    test_results["test4_rate_limit"] = (limit_count > 0)

    # 5. Check home page (unprotected)
    print("\n--- Test 5: Web UI check ---")
    r_home = requests.get(url_home)
    print(f"Home status code: {r_home.status_code}")
    test_results["test5_web_ui"] = (r_home.status_code == 200)

finally:
    print("\nStopping server...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("Server stopped.")

print("\n--- Verification Summary ---")
all_passed = True
for k, v in test_results.items():
    print(f"{k}: {'PASS' if v else 'FAIL'}")
    if not v:
        all_passed = False

if all_passed:
    print("\nALL TESTS PASSED SUCCESSFULLY!")
    sys.exit(0)
else:
    print("\nSOME TESTS FAILED!")
    sys.exit(1)
