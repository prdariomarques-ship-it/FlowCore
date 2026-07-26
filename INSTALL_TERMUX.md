# Install FlowCore on Android (Termux)

> Copy-paste these commands directly into Termux.

---

## One-line install

```bash
pkg install python git && \
git clone https://github.com/prdariomarques-ship-it/FlowCore.git && \
cd FlowCore && \
bash install.sh
```

---

## Step by step

### 1. Install Termux packages

```bash
pkg update
pkg install python git openssl
```

### 2. Clone the repository

```bash
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
```

### 3. Run the installer

```bash
bash install.sh
```

### 4. Start FlowCore

```bash
# Option A: Start the API server
python3 flowcore.py serve

# Option B: Start as background daemon
python3 daemon.py start
```

### 5. Verify it works

```bash
# Health check
python3 flowcore.py health

# Or with curl
curl http://127.0.0.1:8080/api/health
```

---

## Daily usage

```bash
# Start daemon
python3 daemon.py start

# Check status
python3 daemon.py status

# Stop daemon
python3 daemon.py stop

# Restart daemon
python3 daemon.py restart
```

---

## Maintenance

```bash
# Diagnostics
bash doctor.sh

# Security audit
python3 scripts/audit.py

# Update
bash update.sh

# Repair
bash repair.sh

# Optimize
bash optimize.sh
```

---

## Uninstall

```bash
bash uninstall.sh          # Keep data and config
bash uninstall.sh --purge  # Remove everything
```
