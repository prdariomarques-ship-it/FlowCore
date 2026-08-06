#!/usr/bin/env bash
# FlowCore — ADB Homologation Diagnostic
# Runs a full diagnostic against a connected Android device via ADB.
# Does NOT stop on first failure. Captures exact error text everywhere.
#
# Usage:
#   ./tools/adb_homolog.sh [ADB_DEVICE_SERIAL]
#
# Examples:
#   ./tools/adb_homolog.sh                    # auto-selects if one device
#   ./tools/adb_homolog.sh emulator-5554
#   ./tools/adb_homolog.sh R3CT80NFZPB        # physical device serial

set -o pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLD='\033[1m'; RST='\033[0m'

ok()   { echo -e "${GRN}  ✓${RST}  $*"; }
warn() { echo -e "${YLW}  ⚠${RST}  $*"; }
fail() { echo -e "${RED}  ✗${RST}  $*"; }
hdr()  { echo -e "\n${BLD}═══ $* ═══${RST}"; }

# ── ADB setup ────────────────────────────────────────────────────────────────
export PATH="${ANDROID_HOME:-$HOME/android-sdk}/platform-tools:$PATH"

ADB_SERIAL="${1:-}"
ADB="adb"
[[ -n "$ADB_SERIAL" ]] && ADB="adb -s $ADB_SERIAL"

RESULTS=()   # accumulates PASS/WARN/FAIL tokens
STRATEGY=""  # set to "run-as" | "direct" | "none" at decision point

# ── Helpers ───────────────────────────────────────────────────────────────────
record() { RESULTS+=("$1"); }   # $1 = PASS | WARN | FAIL

run_as() {
    # Attempt a command via run-as com.termux; returns exit code + stdout
    local cmd="$*"
    $ADB shell "run-as com.termux $cmd" 2>&1
}

adb_shell() {
    $ADB shell "$@" 2>&1
}

# ── 1. ADB connectivity ───────────────────────────────────────────────────────
hdr "ADB"

if ! command -v adb &>/dev/null; then
    fail "adb not found in PATH (${PATH})"
    echo "Install: sudo apt-get install android-tools-adb  OR  place platform-tools on PATH"
    exit 1
fi
ok "adb found: $(command -v adb)"

DEVICES=$(adb devices 2>&1)
echo "$DEVICES"

CONNECTED=$(echo "$DEVICES" | grep -v '^List' | grep 'device$' | awk '{print $1}')
COUNT=$(echo "$CONNECTED" | grep -c . 2>/dev/null || true)

if [[ "$COUNT" -eq 0 ]]; then
    fail "No authorised devices attached — check USB cable and 'Allow USB debugging' dialog on device"
    exit 1
fi
if [[ "$COUNT" -gt 1 ]] && [[ -z "$ADB_SERIAL" ]]; then
    warn "Multiple devices found — pass serial as argument: ./tools/adb_homolog.sh <serial>"
    echo "Connected serials: $CONNECTED"
    exit 1
fi
ok "Device connected ($COUNT device(s))"
record PASS

# ── 2. Device info ────────────────────────────────────────────────────────────
hdr "Device"

MODEL=$(adb_shell getprop ro.product.model); ok "Model      : $MODEL"
RELEASE=$(adb_shell getprop ro.build.version.release); ok "Android    : $RELEASE"
SDK=$(adb_shell getprop ro.build.version.sdk); ok "SDK        : $SDK"
ARCH=$(adb_shell getprop ro.product.cpu.abi); ok "CPU ABI    : $ARCH"
record PASS

# ── 3. Termux installed ───────────────────────────────────────────────────────
hdr "Termux Package"

TERMUX_PKG=$(adb_shell "pm list packages com.termux" 2>&1)
if echo "$TERMUX_PKG" | grep -q "com.termux"; then
    ok "com.termux installed"
    record PASS
else
    fail "com.termux not found — install Termux (F-Droid, NOT Play Store for full ADB access)"
    record FAIL
fi

# ── 4. run-as probe ───────────────────────────────────────────────────────────
hdr "run-as Probe"

RUNAS_OUT=$(run_as pwd 2>&1)
RUNAS_EC=$?
echo "  raw output: $RUNAS_OUT"
echo "  exit code : $RUNAS_EC"

if echo "$RUNAS_OUT" | grep -q "files/home"; then
    ok "run-as com.termux works — strategy: run-as"
    STRATEGY="run-as"
    record PASS
elif echo "$RUNAS_OUT" | grep -qi "not debuggable"; then
    warn "run-as failed: package not debuggable"
    warn "This is expected for Play Store / non-debug Termux builds"
    STRATEGY="direct"
    record WARN
elif echo "$RUNAS_OUT" | grep -qi "permission denied"; then
    warn "run-as failed: permission denied (SELinux or ro.debuggable=0 on this device)"
    STRATEGY="direct"
    record WARN
elif echo "$RUNAS_OUT" | grep -qi "not found\|unknown package"; then
    fail "run-as failed: Termux package not found by run-as"
    STRATEGY="none"
    record FAIL
else
    warn "run-as result unclear: '$RUNAS_OUT'"
    STRATEGY="direct"
    record WARN
fi

# ── 5. Python inside Termux ───────────────────────────────────────────────────
hdr "Python"

probe_python() {
    local out
    if [[ "$STRATEGY" == "run-as" ]]; then
        out=$(run_as files/usr/bin/python3 --version 2>&1)
    else
        # Ask ADB to launch a Termux command via am broadcast
        out=$(adb_shell "ls /data/data/com.termux/files/usr/bin/python3" 2>&1)
    fi
    echo "$out"
}

PYTHON_OUT=$(probe_python)
if echo "$PYTHON_OUT" | grep -qi "python"; then
    ok "Python found: $PYTHON_OUT"
    record PASS
elif echo "$PYTHON_OUT" | grep -q "No such file"; then
    fail "Python3 not found in Termux — run: pkg install python"
    record FAIL
else
    warn "Python probe inconclusive: $PYTHON_OUT"
    record WARN
fi

# ── 6. Key binaries ───────────────────────────────────────────────────────────
hdr "Termux Binaries (via direct ls)"

TERMUX_BIN="/data/data/com.termux/files/usr/bin"

check_binary() {
    local name="$1"
    local out
    out=$(adb_shell "ls $TERMUX_BIN/$name" 2>&1)
    if echo "$out" | grep -q "$name"; then
        ok "$name found"
        record PASS
    else
        warn "$name not found — $out"
        record WARN
    fi
}

check_binary python3
check_binary git
check_binary ssh
check_binary curl
check_binary sqlite3

# ── 7. Termux:API binaries ────────────────────────────────────────────────────
hdr "Termux:API Binaries"

API_BINS=(
    termux-battery-status
    termux-wifi-connectioninfo
    termux-notification
    termux-wake-lock
    termux-camera-photo
    termux-microphone-record
    termux-location
    termux-vibrate
    termux-torch
    termux-share
    termux-clipboard-get
    termux-clipboard-set
)

MISSING_API=()
for bin in "${API_BINS[@]}"; do
    out=$(adb_shell "ls $TERMUX_BIN/$bin" 2>&1)
    if echo "$out" | grep -q "$bin"; then
        ok "$bin"
    else
        warn "MISSING: $bin"
        MISSING_API+=("$bin")
        record WARN
    fi
done

# Bluetooth — explicitly note Android 16 situation
BT_OUT=$(adb_shell "ls $TERMUX_BIN/termux-bluetooth-get-adapters" 2>&1)
if echo "$BT_OUT" | grep -q "termux-bluetooth"; then
    ok "termux-bluetooth-get-adapters (present)"
else
    warn "termux-bluetooth-get-adapters ABSENT (expected on Android 16 — not a bug)"
fi

# ── 8. Termux HOME ────────────────────────────────────────────────────────────
hdr "Termux HOME"

HOME_OUT=$(adb_shell "ls /data/data/com.termux/files/home" 2>&1)
echo "$HOME_OUT" | head -20
if echo "$HOME_OUT" | grep -qiE "permission denied|no such file"; then
    warn "Cannot read Termux HOME directly — this is normal on locked-down builds"
    record WARN
else
    ok "Termux HOME accessible"
    record PASS
fi

# ── 9. FlowCore presence ───────────────────────────────────────────────────────
hdr "FlowCore on Device"

FC_OUT=$(adb_shell "ls /data/data/com.termux/files/home/FlowCore/flowcore.py" 2>&1)
if echo "$FC_OUT" | grep -q "flowcore.py"; then
    ok "FlowCore installed: /data/data/com.termux/files/home/FlowCore/"
    record PASS
else
    warn "FlowCore not found at ~/FlowCore/flowcore.py"
    record WARN
fi

# ── Decision Tree ─────────────────────────────────────────────────────────────
hdr "DIAGNOSIS & RECOMMENDED STRATEGY"

PASS_COUNT=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^PASS$" || true)
WARN_COUNT=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^WARN$" || true)
FAIL_COUNT=$(printf '%s\n' "${RESULTS[@]}" | grep -c "^FAIL$" || true)

echo "  Results: ${PASS_COUNT} PASS  /  ${WARN_COUNT} WARN  /  ${FAIL_COUNT} FAIL"
echo ""

case "$STRATEGY" in
    run-as)
        ok "Strategy: RUN-AS"
        echo "  run-as com.termux works. You can drive FlowCore remotely:"
        echo ""
        echo "  # Example:"
        echo "  adb shell \"run-as com.termux files/usr/bin/python3 files/home/FlowCore/flowcore.py boot\""
        echo ""
        echo "  Automate in CI by wrapping the above in your pipeline."
        ;;
    direct)
        warn "Strategy: DIRECT INSIDE TERMUX"
        echo "  run-as is blocked (non-debuggable package or SELinux)."
        echo "  Remote execution must go through Termux itself, not run-as."
        echo ""
        echo "  Options:"
        echo "    A) Open Termux manually, run commands inside it."
        echo "    B) Use Termux:Tasker + am broadcast to fire scripts."
        echo "    C) Start an SSH server inside Termux (pkg install openssh)"
        echo "       then: adb forward tcp:8022 tcp:8022"
        echo "             ssh -p 8022 localhost 'cd ~/FlowCore && python3 flowcore.py boot'"
        echo "    D) Use adb shell am start to open Termux, then input-text."
        echo ""
        echo "  Recommended: SSH tunnel (option C) — reliable, scriptable."
        echo "    Inside Termux:  pkg install openssh && sshd"
        echo "    On your machine: adb forward tcp:8022 tcp:8022"
        echo "                     ssh -p 8022 -o StrictHostKeyChecking=no localhost"
        ;;
    none)
        fail "Strategy: NONE — Termux not accessible via ADB"
        echo "  Possible causes:"
        echo "    • Termux not installed or not the same AID run-as expects"
        echo "    • Device is locked / Secure Folder active"
        echo "    • The ADB daemon does not have access to the app data dir"
        echo ""
        echo "  Next steps:"
        echo "    1. Confirm Termux is installed and was opened at least once."
        echo "    2. Try: adb shell pm list packages | grep termux"
        echo "    3. On rooted devices: adb shell su -c 'ls /data/data/com.termux'"
        ;;
    *)
        warn "Strategy undetermined — review output above"
        ;;
esac

echo ""
if [[ ${#MISSING_API[@]} -gt 0 ]]; then
    warn "Missing Termux:API tools: ${MISSING_API[*]}"
    echo "  Inside Termux: pkg install termux-api"
    echo "  Then grant permissions: Android Settings → Apps → Termux:API → Permissions"
fi

echo ""
echo -e "${BLD}Done.${RST}"
