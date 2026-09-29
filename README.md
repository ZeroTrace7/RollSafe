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

## 4. Quickstart: How to Run & Demo RollSafe

We built RollSafe so that anyone—judges, evaluators, or students—can run and test the complete system in seconds. Choose either the **Zero-Dependency Python Runner** or the **Containerized Docker Stack**.

---

### Method A: Instant 10-Second Run (Zero Dependencies — Just Python)
*No Docker or Kubernetes installation required. Runs directly on your machine using standard Python 3.*

#### 1. Start the Complete SRE Stack
Open a terminal in the project root:
```bash
python deploy/run_local_demo.py
```
This automatically boots:
- The **Stable Microservice** (v1.0.0) on `:8081`
- The **Canary Microservice** (v2.0.0) on `:8082`
- The **Reverse Proxy Gateway** and **Telemetry Dashboard** on `:8080`
- The **Background Anomaly Controller** with automated tripping logic

#### 2. Open the Live Telemetry Station
Open your web browser and go to:
```
http://localhost:8080/
```
You will see the dark-themed **RollSafe Telemetry Station** displaying the active 90% stable / 10% canary traffic split, live SRE audit logs, and system health status.

#### 3. Send Normal Traffic
In a second terminal window, send simulated user requests:
```bash
python deploy/scripts/simulate_traffic.py --count 25
```
You will see approximately 90% of requests handled by `stable (v1)` and 10% handled by `canary (v2)`. All return `HTTP 200 OK` in green.

#### 4. Inject a Fault & Watch the Instant Rollback
In the second terminal, inject an intentional fault into the canary:
```bash
python deploy/scripts/simulate_traffic.py --inject-fault --count 15
```
**What happens in real-time:**
1. The canary begins returning HTTP 500 errors.
2. The controller evaluates error samples and logs 3 consecutive anomaly warnings.
3. The circuit breaker trips! In under 40 milliseconds, the controller rewires the gateway to divert **100% of traffic back to stable**.
4. Check your browser: The dashboard flips to **`EMERGENCY ROLLED BACK`** and user requests continue without a single dropped connection.

---

### Method B: Containerized Run (Docker Compose)
*For environments with Docker Desktop installed.*

#### 1. Launch All Containers
```bash
cd deploy
docker compose up -d
```
This starts all 4 containers (`gateway`, `app-stable`, `app-canary`, and `controller`).

#### 2. Verify Container Health
```bash
docker compose ps
```

#### 3. Access Dashboard & Test
- Open `http://localhost:8080/` in your browser.
- Run `python scripts/simulate_traffic.py --count 30` to test normal routing.
- Run `python scripts/simulate_traffic.py --inject-fault --count 20` to test automatic rollback.
- Tear down when finished: `docker compose down`.

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