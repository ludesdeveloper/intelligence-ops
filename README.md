# Intelligence Ops 🤖

> AI-powered Kubernetes monitoring agent that automatically investigates cluster issues and delivers diagnosis to Slack using ReAct pattern.

---

## Overview

Intelligence Ops is an autonomous SRE agent that bridges the gap between traditional monitoring tools and intelligent incident response. When an issue occurs in your Kubernetes cluster, Intelligence Ops automatically:

1. **Detects** anomalies via Prometheus alert rules
2. **Receives** alerts through Slack (via Grafana)
3. **Investigates** the cluster dynamically using ReAct pattern
4. **Delivers** a complete diagnosis back to Slack — in seconds

No more manual `kubectl` hunting. No more context switching. Just answers.

---

## Architecture

```mermaid
flowchart TD
    A[Kubernetes Cluster] -->|metrics| B[Prometheus]
    A -->|logs| C[Promtail]
    C -->|push logs| D[Loki]
    B -->|evaluate rules| E[Grafana]
    E -->|FIRING alert| F[Slack Channel]
    F -->|detect attachment| G[claude_k8s_agent.py]
    G -->|ReAct loop| H{Claude AI}
    H -->|decide command| G
    G -->|execute| I[kubectl]
    I -->|output| G
    H -->|final answer| G
    G -->|post diagnosis| F

    style H fill:#7c3aed,color:#fff
    style G fill:#1a0a2e,color:#c4b5fd
    style F fill:#4a154b,color:#fff
```

---

## ReAct Pattern

The core of Intelligence Ops is the **ReAct (Reasoning + Acting)** pattern — a 2022 research concept where AI iteratively thinks, acts, and observes until it has enough information to answer.

```mermaid
sequenceDiagram
    participant S as Slack
    participant A as Agent (Python)
    participant C as Claude AI
    participant K as kubectl

    S->>A: [FIRING] CrashLoopBackOff detected
    A->>C: "Investigate this alert"
    C->>A: {"action": "kubectl", "cmd": "get pods -A"}
    A->>K: kubectl get pods -A
    K->>A: pod-x CrashLoopBackOff 5 restarts
    A->>C: "Output: pod-x crashing. What next?"
    C->>A: {"action": "kubectl", "cmd": "logs pod-x -n default"}
    A->>K: kubectl logs pod-x -n default
    K->>A: OOMKilled
    A->>C: "Output: OOMKilled. What next?"
    C->>A: {"action": "answer", "text": "Pod is OOMKilled..."}
    A->>S: Post diagnosis in thread
```

**Claude decides** what to investigate. **Python executes** the commands. Enterprise policies that block AI from running bash directly are bypassed elegantly — Claude only reasons, Python acts.

---

## Building Blocks

| Component | Role | Tools Used |
|-----------|------|-----------|
| Container Orchestration | Where your apps run | Kubernetes (Kind for local) |
| Observability Stack | Detect anomalies | Prometheus + Grafana + Loki + Promtail |
| Communication Channel | Alert + response interface | Slack |
| AI / LLM | Reasoning and diagnosis | Claude (via CLI) |
| Agent Orchestrator | Glue everything together | Python (`claude_k8s_agent.py`) |

> The building block approach means you can swap any component. Using Teams instead of Slack? GPT-4 instead of Claude? The system adapts.

---

## Prerequisites

- Docker
- [Kind](https://kind.sigs.k8s.io/) or any Kubernetes cluster
- kubectl
- [Claude CLI](https://claude.ai/code) (logged in)
- Python 3.8+
- Helm 3+
- Slack workspace with admin access

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ludesdeveloper/intelligence-ops.git
cd intelligence-ops
```

### 2. Setup Kubernetes cluster (local)

```bash
# Create cluster
kind create cluster

# Verify
kubectl get nodes
```

### 3. Deploy sample applications

```bash
# Deploy healthy nginx app
kubectl apply -f nginx-deployment.yaml

# Verify
kubectl get pods -n default
```

### 4. Install observability stack

```bash
# Add helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Create namespace
kubectl create namespace monitoring

# Install Prometheus + Grafana + Alertmanager
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin123 \
  --set grafana.sidecar.datasources.enabled=true \
  --set alertmanager.enabled=true \
  --wait

# Fix inotify limits (required for Promtail on Kind)
sudo sysctl -w fs.inotify.max_user_instances=512
sudo sysctl -w fs.inotify.max_user_watches=524288

# Install Loki
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

# Install Promtail
helm install promtail grafana/promtail \
  --namespace monitoring \
  --set config.lokiAddress=http://loki-gateway.monitoring.svc.cluster.local:80/loki/api/v1/push \
  --wait
```

See `monitoring-stack/` folder for additional monitoring configurations.

### 5. Setup alert rules

Apply CrashLoopBackOff alert rule via Grafana UI or kubectl:

```bash
# Via kubectl
kubectl apply -f - << YAML
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: crashloop-alert
  namespace: monitoring
  labels:
    app: kube-prometheus-stack
    release: monitoring
spec:
  groups:
  - name: kubernetes.pods
    rules:
    - alert: PodCrashLooping
      expr: |
        kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"} == 1
      for: 0m
      labels:
        severity: critical
      annotations:
        summary: "Pod {{ \$labels.pod }} is crash looping"
        description: "Pod {{ \$labels.pod }} in namespace {{ \$labels.namespace }} is in CrashLoopBackOff state."
YAML
```

### 6. Setup Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 7. Setup Slack

- Create a Slack app at https://api.slack.com/apps
- Add Bot Token Scopes: `app_mentions:read`, `channels:history`, `channels:read`, `chat:write`
- Enable Socket Mode and generate App Token
- Subscribe to events: `app_mention`, `message.channels`
- Install app to workspace

### 8. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

### 9. Configure Grafana → Slack notification

- Open Grafana: `kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80`
- Go to Alerting → Contact Points → Add Slack contact point
- Set recipient and bot token
- Set notification policy to use Slack contact point

---

## Usage

### Start the agent

```bash
source venv/bin/activate
python3 claude_k8s_agent.py
```

```
✅ claude_k8s_agent.py starting...
👂 Listening: manual mention + Grafana alerts
⚡️ Bolt app is running!
```

### Manual investigation

Mention the bot in Slack:

```
@intelligence-ops-bot check my cluster
@intelligence-ops-bot why is my pod crashing?
@intelligence-ops-bot check resource usage in production namespace
```

### Automatic investigation

Deploy a crashloop pod to trigger the full automated flow:

```bash
kubectl apply -f crashloop-deployment.yaml
```

Within 1-2 minutes:
1. Prometheus detects CrashLoopBackOff
2. Grafana fires alert to Slack
3. Agent detects `[FIRING` in Slack message attachments
4. ReAct loop investigates cluster
5. Claude posts diagnosis in Slack thread

Cleanup:

```bash
kubectl delete -f crashloop-deployment.yaml
```

---

## Project Structure

```
intelligence-ops/
├── claude_k8s_agent.py           # Main agent - ReAct loop + Slack handlers
├── kubernetes-tools/             # Kubernetes utilities and helper scripts
├── monitoring-stack/             # Monitoring stack additional configurations
├── crashloop-deployment.yaml     # Sample crashloop deployment for testing
├── nginx-deployment.yaml         # Sample healthy nginx deployment
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
├── .gitignore
└── README.md
```

---

## How It Works

### Two Triggers

**Trigger 1: Manual Mention**
```
User: @intelligence-ops-bot check pods
         ↓
app_mention event
         ↓
ReAct loop
         ↓
Diagnosis in thread
```

**Trigger 2: Grafana Alert**
```
Grafana fires alert → Slack
         ↓
Agent detects [FIRING in attachments
(not in text field — Grafana sends alerts in attachments!)
         ↓
ReAct loop
         ↓
Diagnosis in thread
```

### Why Attachments, Not Text?

Grafana sends alerts with an empty `text` field. The actual alert content is in the `attachments` array. This is a common gotcha when integrating Grafana with Slack bots.

```python
# Wrong - always empty from Grafana
text = event.get("text", "")

# Correct
attachments = event.get("attachments", [])
attachment_text = attachments[0].get("title", "") + attachments[0].get("text", "")
```

---

## Known Limitations

- Claude Enterprise policy may block bash tool execution — this is by design. The ReAct pattern was specifically chosen to work within enterprise constraints.
- Claude CLI must be authenticated and available in PATH
- Grafana alert to Slack requires incoming webhook or bot token configured as contact point

---

## Blog Series

Full journey documented in Bahasa Indonesia:

| Part | Title |
|------|-------|
| [Part 1](https://ludesdeveloper.wordpress.com/2026/05/11/intelligence-ops-part-1-latar-belakang-kenapa-ai-dan-building-block/) | Latar Belakang, Kenapa AI dan Building Block |
| Part 2 | Reveal Tools *(coming soon)* |
| Part 3 | Setup Environment *(coming soon)* |
| Part 4 | Setup Slack *(coming soon)* |
| Part 5 | Observability Stack *(coming soon)* |
| Part 6 | ReAct Agent *(coming soon)* |
| Part 7 | Demo + Lessons Learned *(coming soon)* |

---

## License

MIT License — feel free to use, modify, and distribute.

---

*Built with frustration, curiosity, and too many CrashLoopBackOffs.* 😄
