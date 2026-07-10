"""Manual API smoke test — requires running Flask on :5000."""
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:5000"


def test_export_flow():
    print("Starting automated API test...\n")

    print("1. Requesting report generation...")
    response = requests.post(f"{BASE_URL}/reports/generate", json={"user_id": 1, "rows": 50}, timeout=10)
    if response.status_code != 202:
        print(f"Failed to generate report. Status: {response.status_code}")
        print(response.json())
        sys.exit(1)

    task_id = response.json()["task_id"]
    print(f"Task accepted. Task ID: {task_id}\n")

    print("2. Polling status endpoint...")
    status = "QUEUED"
    while status in ("QUEUED", "PROCESSING", "PENDING"):
        time.sleep(2)
        status_res = requests.get(f"{BASE_URL}/reports/status/{task_id}", timeout=10)
        status = status_res.json().get("status")
        rows = status_res.json().get("rows_processed", 0)
        print(f"   Status: {status} | Rows: {rows}")

    if status == "FAILED":
        print(f"Task failed: {status_res.json().get('error_message')}")
        sys.exit(1)

    print("\n3. Downloading CSV...")
    download_res = requests.get(f"{BASE_URL}/reports/download/{task_id}", timeout=30)
    if download_res.status_code == 200:
        print(f"Download OK ({len(download_res.content)} bytes)")
    else:
        print(f"Download failed: {download_res.status_code}")
        sys.exit(1)


if __name__ == "__main__":
    test_export_flow()
