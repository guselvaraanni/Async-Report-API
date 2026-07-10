"""Manual concurrency smoke test — requires Flask on :5000."""
import time

import requests

BASE_URL = "http://127.0.0.1:5000"
REQUEST_COUNT = 5
ROWS_PER_REQUEST = 50000


def test_non_blocking_architecture():
    print(f"Firing {REQUEST_COUNT} heavy requests simultaneously...")
    task_ids = []
    start_time = time.time()

    for i in range(REQUEST_COUNT):
        response = requests.post(
            f"{BASE_URL}/reports/generate",
            json={"user_id": 2, "rows": ROWS_PER_REQUEST},
            timeout=10,
        )
        if response.status_code == 202:
            task_ids.append(response.json().get("task_id"))
        else:
            print(f"Request {i + 1} failed: {response.status_code}")

    total_time = time.time() - start_time
    print(f"\nQueued {len(task_ids)} tasks in {total_time:.4f}s")
    for tid in task_ids:
        print(f" - {tid}")


if __name__ == "__main__":
    test_non_blocking_architecture()
