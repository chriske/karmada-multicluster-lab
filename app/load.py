"""Simple, bounded resource-metrics load for an in-cluster local Service."""
import concurrent.futures
import os
import time
import urllib.request
import threading

URL = os.getenv('TARGET_URL', 'http://placement-demo.demo.svc.cluster.local:8080/burn?ms=100')
WORKERS = max(1, min(32, int(os.getenv('LOAD_WORKERS', '4'))))
STOP = threading.Event()

def loop():
    while not STOP.is_set():
        try:
            with urllib.request.urlopen(URL, timeout=3) as response:
                response.read()
        except Exception:
            time.sleep(0.25) # Expected before Service has local endpoints

if __name__ == '__main__':
    print(f'loadgen start: workers={WORKERS}, target={URL}', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(loop) for _ in range(WORKERS)]
        for future in futures:
            future.result()
