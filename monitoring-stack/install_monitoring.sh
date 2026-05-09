#!/bin/bash
# ================================================
# Full Kubernetes Monitoring Stack
# Prometheus + Grafana + Alertmanager + Loki + Promtail
# ================================================

set -e

echo "=================================================="
echo "🚀 Installing Full Kubernetes Monitoring Stack"
echo "Prometheus + Grafana + Alertmanager + Loki + Promtail"
echo "=================================================="

# ─────────────────────────────────────────
# 1. Fix inotify limits (required for Promtail on kind)
# ─────────────────────────────────────────
echo ""
echo "🔧 Fixing inotify limits..."
sudo sysctl -w fs.inotify.max_user_instances=512
sudo sysctl -w fs.inotify.max_user_watches=524288

# Make permanent
grep -qxF 'fs.inotify.max_user_instances=512' /etc/sysctl.conf || echo "fs.inotify.max_user_instances=512" | sudo tee -a /etc/sysctl.conf
grep -qxF 'fs.inotify.max_user_watches=524288' /etc/sysctl.conf || echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf
echo "✅ inotify limits fixed"

# ─────────────────────────────────────────
# 2. Add Helm Repos
# ─────────────────────────────────────────
echo ""
echo "📦 Adding Helm repos..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
echo "✅ Repos added"

# ─────────────────────────────────────────
# 3. Create Namespace
# ─────────────────────────────────────────
echo ""
echo "📁 Creating monitoring namespace..."
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
echo "✅ Namespace ready"

# ─────────────────────────────────────────
# 4. Install kube-prometheus-stack
#    Prometheus + Grafana + Alertmanager + Node Exporter + kube-state-metrics
# ─────────────────────────────────────────
echo ""
echo "📊 Installing kube-prometheus-stack..."
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin123 \
  --set grafana.sidecar.datasources.enabled=true \
  --set prometheus.prometheusSpec.retention=7d \
  --set alertmanager.enabled=true \
  --wait
echo "✅ kube-prometheus-stack installed"

# ─────────────────────────────────────────
# 5. Install Loki (log storage)
# ─────────────────────────────────────────
echo ""
echo "📝 Installing Loki..."
helm install loki grafana/loki \
  --namespace monitoring \
  --set deploymentMode=SingleBinary \
  --set loki.auth_enabled=false \
  --set loki.commonConfig.replication_factor=1 \
  --set loki.storage.type=filesystem \
  --set singleBinary.replicas=1 \
  --set read.replicas=0 \
  --set write.replicas=0 \
  --set backend.replicas=0 \
  --set loki.useTestSchema=true \
  --wait
echo "✅ Loki installed"

# ─────────────────────────────────────────
# 6. Install Promtail (log collector)
#    Points to loki-gateway (correct URL)
# ─────────────────────────────────────────
echo ""
echo "🔍 Installing Promtail..."
helm install promtail grafana/promtail \
  --namespace monitoring \
  --set config.lokiAddress=http://loki-gateway.monitoring.svc.cluster.local:80/loki/api/v1/push \
  --wait
echo "✅ Promtail installed"

# ─────────────────────────────────────────
# 7. Add Loki datasource to Grafana
# ─────────────────────────────────────────
echo ""
echo "🔗 Adding Loki datasource to Grafana..."
kubectl apply -f - << YAML
apiVersion: v1
kind: ConfigMap
metadata:
  name: loki-datasource
  namespace: monitoring
  labels:
    grafana_datasource: "1"
data:
  loki.yaml: |
    apiVersion: 1
    datasources:
    - name: Loki
      type: loki
      url: http://loki-gateway.monitoring.svc.cluster.local:80
      access: proxy
      isDefault: false
      jsonData:
        maxLines: 1000
YAML

# Restart Grafana to pick up new datasource
kubectl rollout restart deployment/monitoring-grafana -n monitoring
kubectl rollout status deployment/monitoring-grafana -n monitoring
echo "✅ Loki datasource added"

# ─────────────────────────────────────────
# 8. Verify Installation
# ─────────────────────────────────────────
echo ""
echo "🔍 Checking all pods..."
kubectl get pods -n monitoring

echo ""
echo "=================================================="
echo "✅ FULL MONITORING STACK INSTALLED!"
echo "=================================================="
echo ""
echo "📊 Access Grafana:"
echo "   kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80"
echo "   URL:      http://localhost:3000"
echo "   Username: admin"
echo "   Password: admin123"
echo ""
echo "📈 Access Prometheus:"
echo "   kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090"
echo "   URL:      http://localhost:9090"
echo ""
echo "🔔 Access Alertmanager:"
echo "   kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-alertmanager 9093:9093"
echo "   URL:      http://localhost:9093"
echo ""
echo "📝 Query Logs in Grafana:"
echo "   Explore → Loki → {namespace='default'}"
echo "   Explore → Loki → {namespace='monitoring'}"
echo ""
echo "📦 What's installed:"
echo "   ✅ Prometheus    - Metrics collection"
echo "   ✅ Grafana       - Dashboards (metrics + logs)"
echo "   ✅ Alertmanager  - Alerts"
echo "   ✅ Loki          - Log storage"
echo "   ✅ Promtail      - Log collection from all pods"
echo "   ✅ Node Exporter - Node metrics"
echo "   ✅ kube-state-metrics - Pod/deployment metrics"
echo "=================================================="