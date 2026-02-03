"""Quick test script for the chat API."""
import requests
import time
import subprocess
import sys

def main():
    # Start server
    print("Starting server...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "8082"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(3)

    try:
        # Test status endpoint
        print("\n1. Testing /api/status...")
        resp = requests.get("http://127.0.0.1:8082/api/status")
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {resp.json()}")

        # Test chat endpoint
        print("\n2. Testing /api/chat...")
        resp = requests.post(
            "http://127.0.0.1:8082/api/chat",
            json={"message": "Say hi in one word."}
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Response: {data['response']}")
            print(f"   Conversation ID: {data['conversation_id']}")
        else:
            print(f"   Error: {resp.text}")

        print("\n✓ Tests completed!")

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()
