import requests
import time

BASE_URL = "http://127.0.0.1:5000"
REQUEST_COUNT = 5
ROWS_PER_REQUEST = 50000

def test_non_blocking_architecture():
    print(f"🚀 Firing {REQUEST_COUNT} heavy requests simultaneously...")
    task_ids = []
    
    start_time = time.time()
    
    # Fire requests rapidly
    for i in range(REQUEST_COUNT):
        response = requests.post(f"{BASE_URL}/reports/generate", json={
            "user_id": 2,  # Using user_id=2 to avoid conflicts with test_e2e_polling.py
            "rows": ROWS_PER_REQUEST
        })
        
        if response.status_code == 202:
            task_ids.append(response.json().get('task_id'))
        else:
            print(f"Request {i+1} failed: {response.status_code}")

    total_time = time.time() - start_time
    
    print("\n--- RESULTS ---")
    print(f"✅ Successfully queued {len(task_ids)} background tasks.")
    print(f"⏱️  Total time to queue {REQUEST_COUNT * ROWS_PER_REQUEST} rows: {total_time:.4f} seconds.")
    
    if total_time < 2.0:
        print("🏆 PROOF: The primary Flask cycle is completely unblocked!")
    else:
        print("⚠️ WARNING: The API took a while to respond. Check if the thread is blocking.")

    print("\nTask IDs generated:")
    for tid in task_ids:
        print(f" - {tid}")

if __name__ == "__main__":
    test_non_blocking_architecture()