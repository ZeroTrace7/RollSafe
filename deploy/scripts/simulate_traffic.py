#!/usr/bin/env python3
"""
RollSafe Traffic Simulation & Fault Injection Script
Simulates realistic concurrent user traffic against the RollSafe gateway.
Pass --inject-fault to force high failure rates on the canary container.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

# Ensure UTF-8 output where supported
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def send_request(url: str):
    start = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RollSafe-Traffic-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            elapsed = (time.time() - start) * 1000
            data = json.loads(resp.read().decode())
            return resp.status, data.get("deployment", "unknown"), data.get("version", ""), elapsed
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - start) * 1000
        return e.code, "canary-fault", "v2-error", elapsed
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return 503, "gateway-error", str(e), elapsed

def main():
    parser = argparse.ArgumentParser(description="RollSafe Traffic Generator")
    parser.add_argument("--url", default="http://localhost:8080", help="Target gateway URL")
    parser.add_argument("--count", type=int, default=30, help="Total requests to send")
    parser.add_argument("--delay", type=float, default=0.15, help="Delay between requests in seconds")
    parser.add_argument("--inject-fault", action="store_true", help="Simulate broken canary release")
    args = parser.parse_args()

    print("=" * 65)
    print(f"[ROLLSAFE] Traffic Generator -> {args.url}")
    if args.inject_fault:
        print("[!] FAULT INJECTION ENABLED: Sending requests to trigger canary 500s!")
    else:
        print("[OK] NORMAL TRAFFIC MODE: Testing progressive weighted distribution")
    print("=" * 65)

    stats = {"stable": 0, "canary": 0, "errors": 0}
    target = f"{args.url}/error" if args.inject_fault else f"{args.url}/"

    for i in range(1, args.count + 1):
        status, deployment, version, elapsed = send_request(target)
        if status == 200:
            stats[deployment] = stats.get(deployment, 0) + 1
            print(f"Req #{i:02d} | HTTP {status} | Deploy: {deployment:<12} | Ver: {version} | Latency: {elapsed:.1f}ms")
        else:
            stats["errors"] += 1
            print(f"Req #{i:02d} | HTTP {status} | Deploy: {deployment:<12} | Latency: {elapsed:.1f}ms (SIMULATED FAULT)")

        time.sleep(args.delay)

    print("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    total_ok = stats.get("stable", 0) + stats.get("canary", 0)
    print(f"Total Requests: {args.count}")
    print(f"Stable (v1):    {stats.get('stable', 0)} ({(stats.get('stable',0)/max(1,total_ok))*100:.1f}%)")
    print(f"Canary (v2):    {stats.get('canary', 0)} ({(stats.get('canary',0)/max(1,total_ok))*100:.1f}%)")
    print(f"Errors/Faults:  {stats.get('errors', 0)}")
    print("=" * 69)

if __name__ == "__main__":
    main()
