# RollSafe

> **Automated Progressive Canary Delivery & Zero-Downtime Resilience Engine**  
> *Built for Jāgriti Hacks 2026 — Track: DevOps & Cloud | Theme: Ideas For a Safer Tomorrow*

[![GitHub License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Go Version](https://img.shields.io/badge/Go-1.21+-00ADD8.svg)](core/go.mod)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](deploy/docker-compose.yml)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Argo%20Rollouts-326CE5.svg)](k8s/argo-rollouts/rollout.yaml)

---

### Team & Contributors
- **Shourya Pratap** ([@shourya2101](https://github.com/shourya2101)) — System Architecture, Go Microservice & Kubernetes Engineering
- **ZeroTrace7** ([@ZeroTrace7](https://github.com/ZeroTrace7)) — Reliability Testing, Anomaly Detection & Telemetry

---

## 1. The Real-World Problem

In critical systems—such as hospital patient databases, payment gateways, and municipal dispatch networks—bad software deployments are catastrophic. Traditional deployments often replace 100% of running application instances at once ("big bang" deployments). When an unhandled nil pointer, database connection leak, or schema mismatch slips past staging tests into production, thousands of active users crash simultaneously.

Even when monitoring tools detect an outage, the average **Mean Time to Recovery (MTTR)** across engineering teams remains between 15 to 45 minutes:
1. An on-call engineer gets paged by PagerDuty.
2. The engineer opens logs to confirm the issue.
3. The team coordinates over Slack and manually runs `kubectl rollout undo` or redeploys the previous Docker image.
4. During those 20 minutes, transactions are dropped and users are stranded.

**RollSafe** treats deployments like an electrical fuse box. Instead of sending all live users to an untested release, it routes a small slice of traffic (10%) to a canary instance, monitors health and error metrics continuously, and automatically trips the circuit—severing traffic back to 100% stable in under 50 milliseconds if errors spike.

---

## 2. Physical Analogy: The Electrical Circuit Breaker

Think of RollSafe like the circuit breaker in your home's breaker panel. 

When a kitchen appliance shorts out, you don't wait for an electrician to drive over and flip a switch while the wiring overheats. The mechanical fuse trips instantly because the current crossed a physical safety limit.

RollSafe acts as that automated circuit breaker for web traffic:
- **Normal Current:** 90% of requests flow through the main stable line (`v1`), 10% sample through the canary wire (`v2`).
- **Short Circuit:** The canary starts throwing HTTP 500 errors or latency spikes past 1,500ms.
- **Trip Mechanism:** If the error rate exceeds 5% across 3 consecutive sampling cycles, the controller flips the upstream weight to zero. Active user sessions never experience a sustained outage.

```
                    Live Inbound User Traffic
                               │
                               ▼
                   ┌───────────────────────┐
                   │   RollSafe Gateway    │ (NGINX Reverse Proxy)
                   │  Dynamic Weighting    │
                   └───────────┬───────────┘
                               │
            ┌──────────────────┴──────────────────┐
     90% of requests                       10% of requests
            ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐
│  app-stable (v1.0.0)  │             │  app-canary (v2.0.0)  │
│  Known Good State     │             │  New Release Candidate│
└───────────────────────┘             └───────────┬───────────┘
                                                  │
                                          Health Telemetry
                                                  │
                                                  ▼
                                      ┌───────────────────────┐
                                      │   RollSafe Engine     │
                                      │  Anomaly Detection &  │
                                      │  Auto-Trip Controller │
                                      └───────────┬───────────┘
                                                  │
                     If Canary Error Rate > 5%    │
                     Across 3 Check Cycles        │
                                                  ▼
                                      [ Emergency Rollback ]
                                      Set Canary Weight -> 0%
                                      Divert 100% to Stable
                                      Duration: < 50ms
```

---

## 3. Engineering Decisions & Honest Trade-offs

We deliberately built RollSafe with a **Dual-Engine Architecture** to address both local edge setups and large-scale cloud clusters:

### Trade-off 1: Standalone Docker Compose vs. Full Kubernetes
* **The Kubernetes Dilemma:** While Kubernetes is the cloud standard, running a multi-node cluster with Prometheus and Argo Rollouts requires 6-8 GB of RAM and complex ingress controllers. On edge appliances, local hospital servers, or resource-constrained environments, running Kubernetes is impractical.
* **Our Solution:** We provide both:
  1. **Standalone Mode (`deploy/`):** Runs on plain Docker Compose using NGINX and a Python controller daemon. It takes 150 MB of memory and starts in 3 seconds. Perfect for edge computing and quick evaluation.
  2. **Enterprise Kubernetes Mode (`k8s/`):** Production manifests utilizing Argo Rollouts, Prometheus metric analysis (`AnalysisTemplate`), and Flagger for teams running full cloud infrastructure.

### Trade-off 2: Metric Flapping Prevention
* A naive rollback script triggers an abort the moment a single request fails. In the real world, temporary network jitter or DNS timeouts can drop a single packet. If you roll back instantly on one 500 error, you get **metric flapping**—deployments abort constantly on false alarms.
* **Our Implementation:** RollSafe requires **3 consecutive failed evaluation windows** before pulling the plug. If a brief glitch occurs and the next cycle returns 100% healthy, the counter resets.

---

## 4. Quickstart: 2-Minute Local Demo

You can run and test the complete system locally with Docker Desktop.

### Step 1: Clone and Launch
```bash
git clone https://github.com/shourya2101/RollSafe.git
cd RollSafe/deploy

docker compose up -d
```

Verify all 4 containers are running:
```bash
docker compose ps
```
- `gateway`: Listening on `http://localhost:8080`
- `app-stable`: Serving version `v1.0.0`
- `app-canary`: Serving version `v2.0.0`
- `controller`: Running background telemetry checks

---

### Step 2: Open the Telemetry Station
Open your web browser and navigate to:
```
http://localhost:8080/
```
You will see the **RollSafe Telemetry Station** dashboard displaying the live 90/10 traffic split and health status.

---

### Step 3: Send Baseline Traffic
In a new terminal window, simulate normal user traffic:
```bash
python scripts/simulate_traffic.py --count 30
```
**Output:** You will observe approximately 9 out of 10 requests handled by `stable (v1)` and 1 out of 10 handled by `canary (v2)`. All return `HTTP 200 OK`.

---

### Step 4: Inject Failure & Observe Instant Rollback
Now, simulate a broken release on the canary container:
```bash
python scripts/simulate_traffic.py --inject-fault --count 20
```

**What Happens in Real-time:**
1. The script hits the canary's fault endpoint, generating HTTP 500 errors.
2. The RollSafe controller detects the error rate crossing the 5% threshold.
3. The controller logs:
   ```text
   [RollSafe-Engine] ⚠️ Anomaly detected! Consecutive fail count: 1/3
   [RollSafe-Engine] ⚠️ Anomaly detected! Consecutive fail count: 2/3
   [RollSafe-Engine] 🚨 TRIGGERING INSTANT ROLLBACK: Error rate 100.0% exceeded threshold (5.0%)
   [RollSafe-Engine] ✅ NGINX dynamic weights updated: Traffic diverted to 100% stable.
   [RollSafe-Engine] ✅ Zero-downtime failover completed in < 50ms.
   ```
4. Check `http://localhost:8080/` in your browser: The dashboard flips to `EMERGENCY ROLLED BACK` and 100% of user traffic is safely served by `app-stable`. Zero downtime.

---

## 5. Enterprise Kubernetes Deployment

For clusters running Kubernetes, all manifests are pre-configured under `k8s/`:

### Argo Rollouts Progressive Delivery
```bash
# 1. Apply namespace and cluster services
kubectl apply -f k8s/argo-rollouts/service.yaml
kubectl apply -f k8s/argo-rollouts/ingress.yaml

# 2. Deploy Prometheus metric analysis template
kubectl apply -f k8s/argo-rollouts/analysistemplate.yaml

# 3. Deploy RollSafe Rollout resource
kubectl apply -f k8s/argo-rollouts/rollout.yaml
```

The rollout will step through weights:
- **20%** $\rightarrow$ pause 1m
- **50%** $\rightarrow$ Prometheus checks success share $\ge 99\%$
- **80%** $\rightarrow$ final validation
- **100%** $\rightarrow$ promotion complete

If Prometheus detects the canary's success rate dropping below 99%, Argo Rollouts halts progression and reverts the ingress controller to 100% stable immediately.

---

## 6. Project Structure

```text
RollSafe/
├── core/                         # Core Go Microservice
│   ├── main.go                   # HTTP server with Prometheus instrumentation
│   ├── go.mod                    # Module definition
│   ├── go.sum                    # Dependency checksums
│   └── Dockerfile                # Multi-stage lightweight container build
├── deploy/                       # Standalone Demo & Edge Deployment Stack
│   ├── docker-compose.yml        # Orchestration (Gateway + Stable + Canary + Controller)
│   ├── nginx/
│   │   └── nginx.conf            # Weighted upstream reverse proxy
│   ├── controller/
│   │   └── monitor.py            # Anomaly detection & auto-rollback daemon
│   ├── dashboard/
│   │   └── index.html            # Real-time SRE telemetry dashboard
│   └── scripts/
│       └── simulate_traffic.py   # Traffic bot & canary fault injector
├── k8s/                          # Production Kubernetes Manifests
│   ├── argo-rollouts/            # Argo Rollouts CRD & Prometheus AnalysisTemplate
│   └── flagger/                  # Flagger Progressive Delivery Custom Resources
├── tests/
│   └── k6/
│       └── script.js             # K6 automated load testing scenario
└── LICENSE                       # MIT License
```

---

## 7. Rubric Alignment (Jāgriti Hacks)

| Hackathon Criterion | How RollSafe Delivers |
| :--- | :--- |
| **Technical Execution & Code Quality (30 pts)** | Multi-stage Go microservice, Prometheus telemetry collector, Docker Compose stack, and clean Python controller. |
| **Architecture Correctness & Justification (25 pts)** | Dual-engine design (Standalone Docker + Enterprise K8s). Explained trade-offs between heavy Kubernetes and lightweight edge setups. |
| **Handling Constraints & Edge Cases (25 pts)** | Built-in flapping prevention (3 consecutive cycles), timeout drains, and sub-50ms connection preservation. |
| **Demo Quality & Clarity (20 pts)** | Visual SRE dashboard, single-command setup, and clear terminal scripts for a 10-minute presentation video. |

---

## 8. License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.