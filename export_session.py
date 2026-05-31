"""One-shot: export current encrypted session to plaintext via the running API."""
import requests
import json
import time
import uuid

r = requests.get("http://127.0.0.1:19850/api/chats/load?id=chat_20260530_213611_d770")
data = r.json()

if not data.get("success"):
    print(f"FAILED: {data}")
    exit(1)

history = data["history"]
sid = f"chat_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
path = f"D:\\doraheart\\Projects\\DeepGravity\\logs\\chats\\{sid}.json"

with open(path, "w", encoding="utf-8") as f:
    json.dump(history, f, indent=2)

print(f"OK - {len(history)} messages -> {sid}.json")
