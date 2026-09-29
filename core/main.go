package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	requestCounter = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "rollsafe_requests_total",
			Help: "Total HTTP requests handled by the RollSafe microservice",
		},
		[]string{"success", "deployment"},
	)
)

func init() {
	prometheus.MustRegister(collectors.NewBuildInfoCollector())
	prometheus.MustRegister(requestCounter)
}

type ServiceResponse struct {
	Status     string `json:"status"`
	Version    string `json:"version"`
	Deployment string `json:"deployment"`
	Pod        string `json:"pod,omitempty"`
	Node       string `json:"node,omitempty"`
}

func handleSuccess(deployment, version, pod, node string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		requestCounter.WithLabelValues("true", deployment).Inc()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)

		_ = json.NewEncoder(w).Encode(ServiceResponse{
			Status:     "healthy",
			Version:    version,
			Deployment: deployment,
			Pod:        pod,
			Node:       node,
		})
	}
}

func handleError(deployment string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		requestCounter.WithLabelValues("false", deployment).Inc()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)

		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":     "error",
			"message":    "Internal server error simulated on canary release",
			"deployment": deployment,
		})
	}
}

func handleHealth(version, deployment string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":     "UP",
			"version":    version,
			"deployment": deployment,
		})
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok && value != "" {
		return value
	}
	return fallback
}

func main() {
	httpPort := getEnv("HTTP_PORT", "8080")
	metricsPort := getEnv("METRICS_PORT", "9090")
	enableMetrics := getEnv("PROMETHEUS_ENABLED", "true") == "true"

	version := getEnv("APP_VERSION", "v1.0.0")
	deployment := getEnv("DEPLOYMENT_ENV", "stable")
	pod := getEnv("KUBERNETES_POD", getEnv("HOSTNAME", "local-pod"))
	node := getEnv("KUBERNETES_NODE", "local-node")

	if enableMetrics {
		metricsMux := http.NewServeMux()
		metricsMux.Handle("/monitoring/metrics", promhttp.Handler())
		metricsMux.Handle("/metrics", promhttp.Handler())
		go func() {
			log.Printf("[RollSafe Telemetry] Exposing Prometheus metrics on port :%s", metricsPort)
			if err := http.ListenAndServe(fmt.Sprintf(":%s", metricsPort), metricsMux); err != nil {
				log.Fatalf("[RollSafe Telemetry Error] %v", err)
			}
		}()
	}

	appMux := http.NewServeMux()
	appMux.HandleFunc("/", handleSuccess(deployment, version, pod, node))
	appMux.HandleFunc("/health", handleHealth(version, deployment))
	appMux.HandleFunc("/success", handleSuccess(deployment, version, pod, node))
	appMux.HandleFunc("/error", handleError(deployment))

	log.Printf("[RollSafe Core] Starting microservice %s (%s) on port :%s", version, deployment, httpPort)
	if err := http.ListenAndServe(fmt.Sprintf(":%s", httpPort), appMux); err != nil {
		log.Fatalf("[RollSafe Core Error] %v", err)
	}
}
