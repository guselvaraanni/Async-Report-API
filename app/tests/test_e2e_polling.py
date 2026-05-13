import requests
import time
import sys

BASE_URL = "http://127.0.0.1:5000"
USER_ID = 1
ROWS_TO_EXPORT = 50000

def test_async_report_flow():
    print(f"🚀 Starting End-to-End Asynchronous Test for {ROWS_TO_EXPORT} rows...")

    # 1. Trigger the job (Testing non-blocking primary cycle)
    print("\n[1] Triggering Report Generation...")
    start_time = time.time()
    response = requests.post(f"{BASE_URL}/reports/generate", json={
        "user_id": USER_ID,
        "rows": ROWS_TO_EXPORT
    })
    
    # Prove that the API responded instantly
    response_time = time.time() - start_time
    print(f"⏱️  Flask responded in {response_time:.4f} seconds.")
    
    if response.status_code != 202:
        print(f"❌ Failed! Expected 202 Accepted, got {response.status_code}")
        sys.exit(1)

    task_id = response.json().get('task_id')
    print(f"✅ Task successfully queued. Task ID: {task_id}")

    # 2. State Management Polling
    print("\n[2] Initiating RESTful Polling...")
    status = "PENDING"
    attempts = 0
    
    while status in ["PENDING", "PROCESSING"]:
        attempts += 1
        time.sleep(2) # Poll every 2 seconds
        
        status_res = requests.get(f"{BASE_URL}/reports/status/{task_id}")
        if status_res.status_code != 200:
            print("❌ Failed to fetch status.")
            sys.exit(1)
            
        data = status_res.json()
        new_status = data.get('status')
        rows_processed = data.get('rows_processed', 0)
        
        # Highlight state transitions
        if new_status != status:
            print(f"🔄 State Transition: {status} ➡️  {new_status}")
            status = new_status
            
        print(f"   ↳ Polling attempt {attempts} | Status: {status} | Rows: {rows_processed}")

    if status == "FAILED":
        print(f"\n❌ Background thread failed: {data.get('error_message')}")
        sys.exit(1)

    # 3. File Retrieval
    print("\n[3] Task Completed. Initiating Download...")
    download_res = requests.get(f"{BASE_URL}/reports/download/{task_id}")
    
    if download_res.status_code == 200:
        file_name = f"export_{task_id}.csv"
        with open(file_name, 'wb') as f:
            f.write(download_res.content)
        print(f"✅ Success! File downloaded: {file_name}")
    else:
        print(f"❌ Download failed with status {download_res.status_code}")

if __name__ == "__main__":
    test_async_report_flow()