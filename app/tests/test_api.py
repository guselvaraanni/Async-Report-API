# test_api.py
import requests
import time
import sys

BASE_URL = "http://127.0.0.1:5000"

def test_export_flow():
    print("🚀 Starting Automated API Test...\n")
    
    # 1. Trigger the Report Generation
    print("1️⃣ Requesting report generation...")
    payload = {"user_id": 1, "rows": 50}
    response = requests.post(f"{BASE_URL}/reports/generate", json=payload)
    
    if response.status_code != 202:
        print(f"❌ Failed to generate report. Status: {response.status_code}")
        print(response.json())
        sys.exit(1)
        
    data = response.json()
    task_id = data['task_id']
    print(f"✅ Task accepted! Task ID: {task_id}\n")
    
    # 2. Poll the Status Endpoint
    print("2️⃣ Polling status endpoint...")
    status = "PENDING"
    while status in ["PENDING", "PROCESSING"]:
        time.sleep(2) # Wait 2 seconds before checking again
        status_res = requests.get(f"{BASE_URL}/reports/status/{task_id}")
        
        if status_res.status_code == 200:
            status_data = status_res.json()
            status = status_data['status']
            print(f"   ⏳ Status: {status} (Rows Processed: {status_data.get('rows_processed', 0)})")
        else:
            print("❌ Error checking status.")
            sys.exit(1)
            
    if status == "FAILED":
        print(f"❌ Task Failed! Error: {status_data.get('error_message')}")
        sys.exit(1)
        
    print("\n✅ Report generation COMPLETED!\n")
    
    # 3. Download the File
    print("3️⃣ Downloading CSV file...")
    download_res = requests.get(f"{BASE_URL}/reports/download/{task_id}")
    
    if download_res.status_code == 200:
        file_name = f"test_download_{task_id}.csv"
        with open(file_name, 'wb') as f:
            f.write(download_res.content)
            
        print(f"✅ File downloaded successfully: {file_name}")
        
        # 4. Read the file to prove it isn't empty!
        print("\n📄 File Contents:")
        with open(file_name, 'r') as f:
            content = f.read()
            if not content.strip():
                print("⚠️ THE FILE IS COMPLETELY EMPTY!")
                print("💡 Hint: Check `app/tasks/export_tasks.py` to see how it writes data, or ensure User 1 has data in the database.")
            else:
                print(content[:500]) # Print first 500 characters
                if len(content) > 500:
                    print("... [file truncated for display]")
    else:
        print(f"❌ Failed to download file. Status: {download_res.status_code}")

if __name__ == "__main__":
    test_export_flow()