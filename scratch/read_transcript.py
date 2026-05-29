import json
import os

f_path = r'C:\Users\mendela.a\.gemini\antigravity\brain\a7fedab2-d591-41eb-90d3-92e542908924\.system_generated\logs\transcript.jsonl'
if os.path.exists(f_path):
    with open(f_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print("All User Input Messages:")
    for line in lines:
        try:
            d = json.loads(line)
            if d.get('type') == 'USER_INPUT':
                print(f"Step {d.get('step_index')}: {d.get('content')}")
        except Exception:
            pass
else:
    print("Transcript file does not exist!")
