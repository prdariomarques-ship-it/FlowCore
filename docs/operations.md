# FlowCore Operations Runbook

This document covers production deployment on a Linux host (including WSL2), persistent services, self-healing, and troubleshooting. It supersedes manual `nohup python3 flowcore.py serve` workflows.

## 1. Service: `flowcore.service` (systemd --user)

Create `~/.config/systemd/user/flowcore.service` (adjust `ExecStart` if Python lives elsewhere):

```ini
[Unit]
Description=FlowCore Market Radar API
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=/home/%u/FlowCore
EnvironmentFile=-/home/%u/FlowCore/.env
Environment="FLOWCORE_OLLAMA=http://127.0.0.1:11434"
Environment="FLOWCORE_OLLAMA_TIMEOUT=10"
Environment="FLOWCORE_AGENT_ALLOW_CLOUD=true"
Environment="FLOWCORE_MODEL=qwen3:4b"
ExecStartPre=/bin/bash -c 'source /home/%u/miniconda3/etc/profile.d/conda.sh 2>/dev/null; conda activate base 2>/dev/null; true'
ExecStart=/home/%u/miniconda3/bin/python3 /home/%u/FlowCore/flowcore.py serve
Restart=always
RestartSec=8
StandardOutput=append:/home/%u/flowcore.log
StandardError=append:/home/%u/flowcore.log
TimeoutStartSec=90

[Install]
WantedBy=default.target
```

Enable:

```bash
mkdir -p ~/.config/systemd/user
systemctl --user daemon-reload
systemctl --user enable --now flowcore
sudo loginctl enable-linger $(whoami)   # survives logout
```

> `StartLimitBurst=5` with `RestartSec=8` gives the host a breathing window: if the process crashes 5 times within 5 minutes it stops instead of busy-looping.

## 2. Service: `cloudflared.service` (systemd --user)

Create `~/.config/systemd/user/cloudflared.service`:

```ini
[Unit]
Description=Cloudflare Tunnel -> FlowCore
After=network-online.target flowcore.service
Requires=flowcore.service
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8090
Restart=always
RestartSec=10
StandardOutput=append:/home/%u/tunnel.log
StandardError=append:/home/%u/tunnel.log
TimeoutStartSec=60

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now cloudflared
```

The tunnel URL is written to `~/tunnel.log`; extract it with:

```bash
grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' ~/tunnel.log | tail -1
```

## 3. Self-healing watchdog (cron, every 5 min)

```bash
#!/bin/bash
# ~/flowcore_watchdog.sh
TOKEN=$(grep '^FLOWCORE_API_TOKEN=' ~/FlowCore/.env | cut -d= -f2 | tr -d '"')
ok=$(curl -s --max-time 15 -H "X-FlowCore-Token: $TOKEN" http://127.0.0.1:8090/api/health | grep -c '"status":"ok"')
if [ "$ok" != "1" ]; then
  echo "$(date) [watchdog] API indisponível — restart" >> ~/flowcore_watchdog.log
  systemctl --user restart flowcore
  sleep 10
  systemctl --user restart cloudflared
fi
```

Install:

```bash
chmod +x ~/flowcore_watchdog.sh
(crontab -l 2>/dev/null | grep -v flowcore_watchdog; echo "*/5 * * * * /home/$(whoami)/flowcore_watchdog.sh") | crontab -
```

The watchdog is intentionally simple: it only restarts when the API is actually unreachable, avoiding restart storms while the host is under load.

## 4. Logs

| Log | Path |
|---|---|
| FlowCore service | `~/flowcore.log` (systemd or nohup) |
| Cloudflare tunnel | `~/tunnel.log` |
| Remote tail via API | `curl -H "X-FlowCore-Token: $TOKEN" $URL/api/logs` |
| Decision ledger | `~/.flowcore/decision_log.jsonl` + rendered `~/.flowcore/decision_log.md` |

## 5. Common troubleshooting

| Symptom | Check |
|---|---|
| `/api/ask` timeouts or 404 model | `ollama list`; set `FLOWCORE_MODEL` to an installed model; confirm `ollama ps` |
| Chat returns `urlopen timed out` to 172.26.80.1 | Set `FLOWCORE_OLLAMA=http://127.0.0.1:11434` in `.env` and restart service |
| Tunnel URL changed | Re-extract from `~/tunnel.log`; trycloudflare URLs rotate on restart |
| Port 8090 "address already in use" | `kill $(lsof -ti:8090)`; ensure no leftover nohup process beside the systemd service |
| Ollama slow on first call (disk load) | First call after reboot always pays the load cost; `FLOWCORE_OLLAMA_TIMEOUT` must exceed model load time |
| Container `darioos-caddy-1` zombie PID | `sudo kill -9 <PID>`; zombie caddy blocks `openwa` restarts |

## 6. WSL2 reboot recovery

After `wsl --shutdown` or Windows reboot, user services start automatically if linger is enabled (section 1). Verify with:

```bash
systemctl --user is-active flowcore cloudflared
curl -s http://127.0.0.1:8090/api/health
```

If Docker containers (`darioos-*`) also need to start, add them to a user target or a boot script; they are managed separately from FlowCore.
