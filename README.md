# k8s-agent

A Slack bot that diagnoses Kubernetes cluster issues using Claude as the reasoning engine. The bot listens for Slack mentions and Grafana firing alerts, then runs a ReAct loop where Claude decides which `kubectl` commands to execute, observes the output, and produces a diagnosis.

## How it works

`claude_k8s_agent.py` is the main service. It uses [`slack_bolt`](https://slack.dev/bolt-python/) Socket Mode to receive events and invokes the local `claude` CLI as a subprocess to plan investigations.

The ReAct loop (`react_loop`) prompts Claude to respond with one of two JSON actions:

- `{"action": "kubectl", "cmd": "..."}` — Python runs `kubectl <cmd>` and feeds the output back into the conversation
- `{"action": "answer", "text": "..."}` — final diagnosis returned to Slack

It iterates up to 5 times before giving up.

Two Slack triggers are wired up:

- `app_mention` — direct user questions (`@bot why is pod X crashing?`)
- `message` — Grafana alerts (only acts when an attachment contains `[FIRING`, ignores its own messages and thread replies)

## Layout

```
claude_k8s_agent.py            # Main Slack bot + ReAct loop
crashloop-deployment.yaml      # Test workload that intentionally crashes
nginx-deployment.yaml          # Test workload (healthy nginx)
requirements.txt               # Python deps
kubernetes-tools/
  generate_readonly_kubeconfig.sh  # Creates a read-only ServiceAccount + kubeconfig
monitoring-stack/
  install_monitoring.sh        # One-shot installer: kube-prometheus-stack + Loki + Promtail
  values-monitoring.yaml       # Helm values for kube-prometheus-stack
  values-loki.yaml             # Helm values for Loki
  values-promptail.yaml        # Helm values for Promtail (empty placeholder)
```

## Setup

1. Install Python dependencies:
   ```
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Install the `claude` CLI and authenticate it — the bot shells out to it via `subprocess`.
3. Make sure `kubectl` is on PATH and points at the cluster you want to diagnose. Optionally use the read-only kubeconfig (see below).
4. Create a `.env` with:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   ```
   The Slack app needs Socket Mode enabled and the `app_mention` + `message.channels` event subscriptions.

## Run

```
python claude_k8s_agent.py
```

Then mention the bot in a Slack channel:

```
@bot any pods crashlooping?
```

Or post a Grafana alert into a channel the bot is in — it auto-investigates anything containing `[FIRING`.

## Test workloads

Apply one of the demo manifests to give the bot something to find:

```
kubectl apply -f crashloop-deployment.yaml   # intentional crashloop
kubectl apply -f nginx-deployment.yaml       # healthy baseline
```

## Read-only kubectl access

`kubernetes-tools/generate_readonly_kubeconfig.sh` provisions a `readonly-agent` ServiceAccount with `get/list/watch` on common resources and writes `~/.kube/readonly-config`. Point the agent at this kubeconfig (`KUBECONFIG=~/.kube/readonly-config`) so it can't accidentally mutate the cluster.

## Monitoring stack

`monitoring-stack/install_monitoring.sh` installs a full local observability stack via Helm:

- kube-prometheus-stack (Prometheus, Grafana, Alertmanager, node-exporter, kube-state-metrics)
- Loki (single-binary, filesystem storage)
- Promtail (log shipper pointed at `loki-gateway`)
- Loki datasource pre-wired into Grafana

It also raises `fs.inotify.max_user_instances` / `max_user_watches`, which Promtail tends to hit on local clusters (kind, WSL2, etc.).

Run it once after creating your cluster:

```
./monitoring-stack/install_monitoring.sh
```

Grafana defaults: `admin` / `admin123` on `localhost:3000` after `kubectl port-forward`.

## Troubleshooting

### Promtail pods stuck in `CrashLoopBackOff` / `Error`

Symptom: Promtail logs show errors like `too many open files` or `inotify_init1: too many open files`.

Cause: the host's inotify limits are too low. Common on `kind` and WSL2.

Fix — bump the limits on the host (not the container):

```
sudo sysctl -w fs.inotify.max_user_instances=512
sudo sysctl -w fs.inotify.max_user_watches=524288
```

Make it persist across reboots:

```
echo 'fs.inotify.max_user_instances=512' | sudo tee -a /etc/sysctl.conf
echo 'fs.inotify.max_user_watches=524288' | sudo tee -a /etc/sysctl.conf
```

Then restart the Promtail pods:

```
kubectl rollout restart daemonset/promtail -n monitoring
```

`install_monitoring.sh` already applies and persists these values, so you only need this if you skipped that script or are running on a fresh host.

## Notes

- The bot truncates Slack replies to 3500 chars.
- `kubectl` calls have a 10-second timeout; Claude calls have 60 seconds.
