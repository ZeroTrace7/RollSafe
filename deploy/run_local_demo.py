#!/usr/bin/env python3
"""
RollSafe Standalone Local Demo Runner
Runs the full RollSafe Progressive Canary & Rollback Architecture locally
using standard Python 3 (no Docker or Kubernetes installation required).
"""

import json
import os
import random
import sys
import threading
import time
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

# Shared Runtime State
STATE = {
    "status": "IDLE",  # IDLE, DEPLOYING, ROLLED_BACK, COMPLETED
    "current_stage_index": -1,
    "stages": [5, 10, 25, 50, 100],
    "stage_start_time": 0,
    
    "canary_fault_active": False,
    "canary_weight": 0,   # Starts at 0%
    "stable_weight": 100, # Starts at 100%
    
    "consecutive_failures": 0,
    "threshold_required": 3,
    
    # Real metrics
    "stable_requests": 0,
    "canary_requests": 0,
    "stable_errors": 0,
    "canary_errors": 0,
    "stable_latency_sum": 0.0,
    "canary_latency_sum": 0.0,
    
    "last_error_rate": 0.0,
    "last_avg_latency_ms": 12.0,
    
    "timeline": []
}
LOCK = threading.RLock()

def add_timeline(msg):
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "msg": msg}
    STATE["timeline"].insert(0, entry)
    if len(STATE["timeline"]) > 30:
        STATE["timeline"].pop()
    try:
        print(f"[*] [{timestamp}] {msg.encode('ascii', 'ignore').decode('ascii')}")
    except Exception:
        pass

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
            "version": "v1.0.0",
            "deployment": "stable"
        }
        self.wfile.write(json.dumps(payload).encode())

# ---------------------------------------------------------
# 2. Canary Service Handler (:8082)
# ---------------------------------------------------------
class CanaryHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def do_GET(self):
        is_error = False
        with LOCK:
            is_error = STATE["canary_fault_active"]
        
        if is_error or self.path == "/error":
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
                "version": "v2.0.0",
                "deployment": "canary"
            }
            self.wfile.write(json.dumps(payload).encode())

# ---------------------------------------------------------
# 3. Gateway Reverse Proxy & Dashboard (:8080)
# ---------------------------------------------------------
class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/deployments/start":
            with LOCK:
                if STATE["status"] not in ["DEPLOYING"]:
                    STATE["status"] = "DEPLOYING"
                    STATE["current_stage_index"] = 0
                    STATE["canary_weight"] = STATE["stages"][0]
                    STATE["stable_weight"] = 100 - STATE["canary_weight"]
                    STATE["stage_start_time"] = time.time()
                    STATE["consecutive_failures"] = 0
                    STATE["canary_fault_active"] = False
                    
                    # Reset metrics for fresh comparison
                    STATE["stable_requests"] = 0
                    STATE["canary_requests"] = 0
                    STATE["stable_errors"] = 0
                    STATE["canary_errors"] = 0
                    STATE["stable_latency_sum"] = 0.0
                    STATE["canary_latency_sum"] = 0.0
                    STATE["timeline"] = []
                    
                    add_timeline("Deployment of v2.0.0 started")
                    add_timeline(f"Canary traffic set to {STATE['canary_weight']}%")
            
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "Deployment started"}')
            return

        if self.path == "/api/deployments/rollback":
            with LOCK:
                if STATE["status"] == "DEPLOYING":
                    STATE["status"] = "ROLLED_BACK"
                    STATE["canary_weight"] = 0
                    STATE["stable_weight"] = 100
                    add_timeline("Manual rollback triggered by user")
                    add_timeline("Traffic fully reverted to v1.0.0 stable")
            
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "Rolled back manually"}')
            return

        if self.path == "/inject-fault":
            with LOCK:
                STATE["canary_fault_active"] = True
                add_timeline("⚠️ Fault injected into Canary release")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "Fault injected"}')
            return
            
        if self.path == "/reset-system":
            with LOCK:
                STATE["status"] = "IDLE"
                STATE["current_stage_index"] = -1
                STATE["canary_weight"] = 0
                STATE["stable_weight"] = 100
                STATE["canary_fault_active"] = False
                STATE["consecutive_failures"] = 0
                STATE["timeline"] = []
                add_timeline("System reset to IDLE (100% stable)")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "System reset"}')
            return
            
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/status.json":
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with LOCK:
                s_req = max(1, STATE["stable_requests"])
                c_req = max(1, STATE["canary_requests"])
                
                s_err_rate = STATE["stable_errors"] / s_req
                c_err_rate = STATE["canary_errors"] / c_req
                
                s_lat = STATE["stable_latency_sum"] / s_req if STATE["stable_requests"] > 0 else 0
                c_lat = STATE["canary_latency_sum"] / c_req if STATE["canary_requests"] > 0 else 0
                
                data = {
                    "status": STATE["status"],
                    "stable_weight": STATE["stable_weight"],
                    "canary_weight": STATE["canary_weight"],
                    "stages": STATE["stages"],
                    "current_stage_index": STATE["current_stage_index"],
                    "consecutive_failures": STATE["consecutive_failures"],
                    "threshold_required": STATE["threshold_required"],
                    "metrics": {
                        "stable": {
                            "requests": STATE["stable_requests"],
                            "error_rate": s_err_rate,
                            "latency_ms": s_lat
                        },
                        "canary": {
                            "requests": STATE["canary_requests"],
                            "error_rate": c_err_rate,
                            "latency_ms": c_lat
                        }
                    },
                    "timeline": STATE["timeline"]
                }
            self.wfile.write(json.dumps(data).encode())
            return

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
                self.send_response(404)
                self.end_headers()
                return

        # Traffic proxying
        with LOCK:
            roll = random.randint(1, 100)
            if roll <= STATE["canary_weight"]:
                target_port = 8082
                STATE["canary_requests"] += 1
            else:
                target_port = 8081
                STATE["stable_requests"] += 1

        t0 = time.time()
        target_url = f"http://127.0.0.1:{target_port}{self.path}"
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "RollSafe-Gateway/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                lat = (time.time() - t0) * 1000
                with LOCK:
                    if target_port == 8081:
                        STATE["stable_latency_sum"] += lat
                    else:
                        STATE["canary_latency_sum"] += lat
                
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            lat = (time.time() - t0) * 1000
            with LOCK:
                if target_port == 8081:
                    STATE["stable_errors"] += 1
                    STATE["stable_latency_sum"] += lat
                else:
                    STATE["canary_errors"] += 1
                    STATE["canary_latency_sum"] += lat
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            lat = (time.time() - t0) * 1000
            with LOCK:
                if target_port == 8081:
                    STATE["stable_errors"] += 1
                    STATE["stable_latency_sum"] += lat
                else:
                    STATE["canary_errors"] += 1
                    STATE["canary_latency_sum"] += lat
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Bad Gateway", "details": str(e)}).encode())

# ---------------------------------------------------------
# 4. Background Controller Daemon (Progressive Rollout & Rollback)
# ---------------------------------------------------------
def controller_worker():
    add_timeline("System initialized. Awaiting deployment commands.")
    while True:
        time.sleep(1.0)
        
        with LOCK:
            status = STATE["status"]
            canary_w = STATE["canary_weight"]
            
        if status != "DEPLOYING" or canary_w == 0:
            continue

        # Active Anomaly Probing
        errors = 0
        samples = 5
        for _ in range(samples):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8082/health", timeout=0.8) as resp:
                    if resp.status >= 500:
                        errors += 1
            except Exception:
                errors += 1
            time.sleep(0.02)

        error_rate = errors / samples

        with LOCK:
            # Check for failure
            if error_rate > 0.05:
                STATE["consecutive_failures"] += 1
                if STATE["consecutive_failures"] >= STATE["threshold_required"]:
                    STATE["status"] = "ROLLED_BACK"
                    STATE["canary_weight"] = 0
                    STATE["stable_weight"] = 100
                    add_timeline(f"⚠️ Anomaly detected: Error rate {error_rate*100:.0f}% exceeded threshold")
                    add_timeline("🚨 EMERGENCY AUTO-ROLLBACK TRIGGERED")
                    add_timeline("Traffic fully reverted to v1.0.0 stable")
            else:
                STATE["consecutive_failures"] = 0
                
                # Check for stage progression (Promote every 10 seconds)
                if STATE["status"] == "DEPLOYING":
                    elapsed = time.time() - STATE["stage_start_time"]
                    if elapsed >= 10.0:
                        next_idx = STATE["current_stage_index"] + 1
                        if next_idx < len(STATE["stages"]):
                            STATE["current_stage_index"] = next_idx
                            new_weight = STATE["stages"][next_idx]
                            STATE["canary_weight"] = new_weight
                            STATE["stable_weight"] = 100 - new_weight
                            STATE["stage_start_time"] = time.time()
                            add_timeline(f"Health checks passed. Traffic increased to {new_weight}%")
                            
                            if new_weight == 100:
                                STATE["status"] = "COMPLETED"
                                add_timeline("✅ Deployment of v2.0.0 completed successfully")

def start_server(port, handler_class):
    server = ThreadedHTTPServer(("0.0.0.0", port), handler_class)
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
    print("[OK] [Port 8081] Stable Microservice (v1.0.0) online")
    print("[OK] [Port 8082] Canary Microservice (v2.0.0) online")
    print("[OK] [Port 8080] RollSafe Gateway & API online")
    print("[OK] [Daemon]    Progressive Delivery Controller running")
    print("=" * 70)
    print("\n>>> OPEN YOUR BROWSER AT:  http://localhost:8080/")
    print("=" * 70)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down RollSafe local demo...")
