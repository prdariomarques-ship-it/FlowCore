#!/data/data/com.termux/files/usr/bin/bash
# Shared /proc-based process helpers for Termux.
#
# `pgrep`/`pkill` (procps) can die with "Bad system call" under some Android
# kernels' seccomp policy — when that happens the check silently behaves as
# "no matching process", old FlowCore/cloudflared instances never get killed,
# and a restart looks like it did nothing. These helpers read /proc directly
# and use plain `kill(2)` on a known PID instead, which is never blocked
# (every process manager, including Android's own, depends on it).
#
# Source this file, don't execute it: `. "$(dirname "$0")/proc_utils.sh"`

# _proc_pids <needle> — prints the PID of every process whose cmdline
# contains <needle>.
_proc_pids() {
    local needle="$1" entry pid cmdline
    for entry in /proc/[0-9]*; do
        pid="${entry#/proc/}"
        [ -r "$entry/cmdline" ] || continue
        cmdline="$(tr '\0' ' ' < "$entry/cmdline" 2>/dev/null)"
        case "$cmdline" in *"$needle"*) echo "$pid" ;; esac
    done
}

# _proc_running <needle> — true if any process matches.
_proc_running() {
    [ -n "$(_proc_pids "$1")" ]
}

# _proc_kill <needle> — SIGKILLs every matching process (never itself).
# Sleeps briefly afterwards so the port/socket is free before the caller
# starts a replacement process.
_proc_kill() {
    local needle="$1" pid killed=0
    for pid in $(_proc_pids "$needle"); do
        [ "$pid" = "$$" ] && continue
        kill -9 "$pid" 2>/dev/null && killed=1
    done
    [ "$killed" = 1 ] && sleep 2
    return 0
}
