"""Manual end-to-end polling test — requires Flask + Celery running."""
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:5000"
USER_ID = 1
ROWS_TO_EXPORT = 50000


def test_async_report_flow():
    print(f"Starting E2E test for {ROWS_TO_EXPORT} rows...")

    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/reports/generate",
        json={"user_id": USER_ID, "rows": ROWS_TO_EXPORT},
        timeout=10,
    )
    print(f"Flask responded in {time.time() - start_time:.4f}s")

    if response.status_code != 202:
        print(f"Expected 202, got {response.status_code}")
        sys.exit(1)

    task_id = response.json().get("task_id")
    print(f"Task queued: {task_id}")

    status = "QUEUED"
    attempts = 0
    while status in ("QUEUED", "PROCESSING", "PENDING"):
        attempts += 1
        time.sleep(2)
        status_res = requests.get(f"{BASE_URL}/reports/status/{task_id}", timeout=10)
        data = status_res.json()
        new_status = data.get("status")
        if new_status != status:
            print(f"State: {status} -> {new_status}")
            status = new_status
        print(f"Poll {attempts} | {status} | rows={data.get('rows_processed', 0)}")

    if status == "FAILED":
        print(f"Failed: {data.get('error_message')}")
        sys.exit(1)

    download_res = requests.get(f"{BASE_URL}/reports/download/{task_id}", timeout=60)
    if download_res.status_code == 200:
        file_name = f"export_{task_id}.csv"
        with open(file_name, "wb") as handle:
            handle.write(download_res.content)
        print(f"Downloaded: {file_name}")
    else:
        print(f"Download failed: {download_res.status_code}")


if __name__ == "__main__":
    test_async_report_flow()
