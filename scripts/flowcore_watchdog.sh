#!/bin/bash
TOKEN=$(grep '^FLOWCORE_API_TOKEN=' ~/FlowCore/.env | cut -d= -f2 | tr -d '"')
ok=$(curl -s --max-time 15 -H "X-FlowCore-Token: $TOKEN" http://127.0.0.1:8090/api/health | grep -c '"status":"ok"')
if [ "$ok" != "1" ]; then
  echo "$(date) [watchdog] API indisponivel — restart" >> ~/flowcore_watchdog.log
  systemctl --user restart flowcore
  sleep 10
  systemctl --user restart cloudflared
fi
