import urllib.request
import urllib.error

endpoints = [
    'http://localhost:8000/health',
    'http://localhost:8000/',
    'http://localhost:8000/login',
    'http://localhost:8000/statisty/form016',
    'http://localhost:8000/records/add',
]

for url in endpoints:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            print(f"URL: {url} -> Status: {resp.status} (Length: {len(resp.read())})")
    except urllib.error.HTTPError as e:
        print(f"URL: {url} -> HTTP Error: {e.code} ({e.reason})")
    except Exception as e:
        print(f"URL: {url} -> Connection Error: {e}")
