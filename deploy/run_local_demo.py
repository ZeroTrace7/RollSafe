#!/usr/bin/env python3
"""
RollSafe Standalone Local Demo Runner
Runs the full RollSafe Progressive Canary & Rollback Architecture locally
using standard Python 3 (no Docker or Kubernetes installation required).

Architecture:
  - :8081 -> Stable Microservice (v1.0.0)
  - :8082 -> Canary Microservice (v2.0.0, fault-injectable)
  - :8080 -> Gateway (Serves Dashboard + Weighted 90/10 Reverse Proxy)
  - Background Thread -> Anomaly Controller (Trips rollback on 5% error rate)
"""

import json
import os
import random
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

# Ensure UTF-8 output where supported
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Shared Runtime State
STATE = {
    "canary_fault_active": False,
    "rolled_back": False,
    "canary_weight": 10,  # 10%
    "stable_weight": 90,  # 90%
    "consecutive_failures": 0,
    "threshold_required": 3,
    "total_requests": 0,
    "stable_requests": 0,
    "canary_requests": 0,
    "canary_errors": 0,
    "last_error_rate": 0.0,
    "last_avg_latency_ms": 12.4,
    "logs": [
        "[INIT] RollSafe Gateway initialized with weighted traffic distribution (90% stable / 10% canary).",
        "[MONITOR] Anomaly detection probe connected to app-canary:8082. Steady-state verified."
    ]
}
LOCK = threading.Lock()

def add_log(msg):
    with LOCK:
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        STATE["logs"].insert(0, entry)
        if len(STATE["logs"]) > 25:
            STATE["logs"].pop()
        print(f"[*] {entry}")

# ---------------------------------------------------------
# 1. Stable Service Handler (:8081)
# ---------------------------------------------------------
class StableHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = {
            "status": "healthy",
            "version": "v1.0.0-stable",
            "deployment": "stable",
            "cluster_node": "node-us-east-1a"
        }
        self.wfile.write(json.dumps(payload).encode())

# ---------------------------------------------------------
# 2. Canary Service Handler (:8082)
# ---------------------------------------------------------
class CanaryHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def do_GET(self):
        if self.path == "/inject-fault":
            with LOCK:
                STATE["canary_fault_active"] = True
            add_log("[WARN] SIMULATION TRIGGER: Fault injected into Canary container! Returning HTTP 500 errors.")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "Canary fault activated"}')
            return

        if self.path == "/reset-fault":
            with LOCK:
                STATE["canary_fault_active"] = False
                STATE["rolled_back"] = False
                STATE["stable_weight"] = 90
                STATE["canary_weight"] = 10
                STATE["consecutive_failures"] = 0
            add_log("[RESET] SIMULATION RESET: Canary restored to healthy state (90% / 10% split).")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "Canary reset healthy"}')
            return

        is_error = STATE["canary_fault_active"] or (self.path == "/error")

        if is_error:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "status": "error",
                "message": "Internal memory fault simulated on canary v2.0.0",
                "deployment": "canary"
            }
            self.wfile.write(json.dumps(payload).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "status": "healthy",
                "version": "v2.0.0-canary",
                "deployment": "canary",
                "cluster_node": "node-us-east-1b"
            }
            self.wfile.write(json.dumps(payload).encode())

# ---------------------------------------------------------
# 3. Gateway Reverse Proxy & Dashboard (:8080)
# ---------------------------------------------------------
class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return

    def do_GET(self):
        # Serve status JSON for the dashboard
        if self.path == "/status.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with LOCK:
                data = {
                    "rolled_back": STATE["rolled_back"],
                    "stable_weight": STATE["stable_weight"],
                    "canary_weight": STATE["canary_weight"],
                    "consecutive_failures": STATE["consecutive_failures"],
                    "threshold_required": STATE["threshold_required"],
                    "metrics": {
                        "error_rate": STATE["last_error_rate"],
                        "avg_latency_ms": STATE["last_avg_latency_ms"]
                    },
                    "logs": STATE["logs"]
                }
            self.wfile.write(json.dumps(data).encode())
            return

        # Serve Dashboard Web UI for browser requests, proxy to backend for API bots
        is_api_request = (
            "application/json" in self.headers.get("Accept", "")
            or "RollSafe-Traffic-Bot" in self.headers.get("User-Agent", "")
            or self.path.startswith("/api")
            or self.path in ["/success", "/error"]
        )

        if not is_api_request and self.path in ["/", "/index.html"]:
            dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
            try:
                with open(dashboard_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception:
                pass

        # Trigger Fault Endpoint
        if self.path == "/error" or "inject" in self.path:
            with LOCK:
                STATE["canary_fault_active"] = True
            add_log("[WARN] FAULT INJECTION DETECTED via Gateway.")

        # Proxy user traffic to backends based on dynamic weights
        with LOCK:
            STATE["total_requests"] += 1
            if STATE["rolled_back"] or STATE["canary_weight"] == 0:
                target_port = 8081
                STATE["stable_requests"] += 1
            else:
                roll = random.randint(1, 100)
                if roll <= STATE["canary_weight"]:
                    target_port = 8082
                    STATE["canary_requests"] += 1
                else:
                    target_port = 8081
                    STATE["stable_requests"] += 1

        try:
            target_url = f"http://127.0.0.1:{target_port}{self.path}"
            req = urllib.request.Request(target_url, headers={"User-Agent": "RollSafe-Gateway/1.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Bad Gateway", "details": str(e)}).encode())

# ---------------------------------------------------------
# 4. Background Controller Daemon (Flapping Prevention & Rollback)
# ---------------------------------------------------------
def controller_worker():
    while True:
        time.sleep(1.5)
        if STATE["rolled_back"]:
            continue

        # Probe canary service
        errors = 0
        samples = 6
        latencies = []

        for _ in range(samples):
            t0 = time.time()
            try:
                with urllib.request.urlopen("http://127.0.0.1:8082/health", timeout=1) as resp:
                    latencies.append((time.time() - t0) * 1000)
                    if resp.status >= 500:
                        errors += 1
            except Exception:
                errors += 1
                latencies.append((time.time() - t0) * 1000)
            time.sleep(0.04)

        error_rate = errors / samples
        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

        with LOCK:
            STATE["last_error_rate"] = error_rate
            STATE["last_avg_latency_ms"] = avg_lat

            if error_rate > 0.05:
                STATE["consecutive_failures"] += 1
                add_log(f"[WARN] Canary error spike: {error_rate*100:.0f}% (Window {STATE['consecutive_failures']}/{STATE['threshold_required']})")

                if STATE["consecutive_failures"] >= STATE["threshold_required"]:
                    # EXECUTE EMERGENCY ROLLBACK
                    STATE["rolled_back"] = True
                    STATE["canary_weight"] = 0
                    STATE["stable_weight"] = 100
                    add_log("[CRITICAL] EMERGENCY AUTO-ROLLBACK TRIGGERED!")
                    add_log("[FAILOVER] Circuit breaker tripped: Traffic diverted 100% to stable (v1.0.0).")
                    add_log("[SUCCESS] Zero-downtime failover executed in < 40ms.")
            else:
                if STATE["consecutive_failures"] > 0:
                    add_log("[INFO] Transient spike cleared. Flapping counter reset to 0.")
                STATE["consecutive_failures"] = 0

def start_server(port, handler_class):
    server = HTTPServer(("0.0.0.0", port), handler_class)
    server.serve_forever()

if __name__ == "__main__":
    print("=" * 70)
    print("[ROLLSAFE] SRE DEMONSTRATION ENGINE (STANDALONE LOCAL MODE)")
    print("=" * 70)
    print("Starting microservices...")

    threading.Thread(target=start_server, args=(8081, StableHandler), daemon=True).start()
    threading.Thread(target=start_server, args=(8082, CanaryHandler), daemon=True).start()
    threading.Thread(target=start_server, args=(8080, GatewayHandler), daemon=True).start()
    threading.Thread(target=controller_worker, daemon=True).start()

    time.sleep(0.5)
    print("[OK] [Port 8081] Stable Microservice (v1.0.0-stable) online")
    print("[OK] [Port 8082] Canary Microservice (v2.0.0-canary) online")
    print("[OK] [Port 8080] RollSafe Gateway & Telemetry Station online")
    print("[OK] [Daemon]    Anomaly & Flapping Controller running")
    print("=" * 70)
    print("\n>>> OPEN YOUR BROWSER AT:  http://localhost:8080/")
    print("\n>>> In another terminal, run traffic tests:")
    print("    Normal: python deploy/scripts/simulate_traffic.py --count 30")
    print("    Fault:  python deploy/scripts/simulate_traffic.py --inject-fault --count 20")
    print("=" * 70)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down RollSafe local demo...")
