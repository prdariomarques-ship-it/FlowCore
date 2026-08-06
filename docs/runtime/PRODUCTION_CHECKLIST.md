# FlowCore Android Production Checklist

> Run this before deploying FlowCore to a production Android device.
> Each item maps to a Doctor check or a manual step.

---

## 1. Android Environment

- [ ] Android 8.0+ (SDK 26+) — `getprop ro.build.version.sdk`
- [ ] Termux installed from F-Droid (not Google Play — Play version is frozen)
- [ ] Termux:API app installed from F-Droid
- [ ] `pkg install termux-api` executed inside Termux
- [ ] `termux-setup-storage` executed — `~/storage` symlinks exist

## 2. Core Package Verification

Run `python3 flowcore.py doctor` and confirm all the following are **OK**:

- [ ] `android_detected`
- [ ] `android_version` (SDK ≥ 26)
- [ ] `termux_detected`
- [ ] `termux_api`
- [ ] `termux_storage`
- [ ] `termux_pkg`
- [ ] `python3`
- [ ] `pip`
- [ ] `git`
- [ ] `ssh`
- [ ] `sqlite3`
- [ ] `curl`

## 3. Android Permissions

Grant these permissions via **Settings → Apps → Termux → Permissions**:

- [ ] **Notifications** — required for `sendNotification`
- [ ] **Camera** — required for `takePhoto`
- [ ] **Microphone** — required for `recordAudio`
- [ ] **Location** — required for `getLocation`
- [ ] **Storage** — required for `readFile` / `writeFile` on shared storage

## 4. Battery Optimization

- [ ] Settings → Battery → Termux → **Unrestricted** (prevents background kill)
- [ ] Settings → Battery → FlowCore → **Unrestricted** (if listed separately)

> Without this, Android will kill FlowCore when the screen turns off.

## 5. Capability Verification

Run `python3 flowcore.py status` and confirm the following capabilities resolve:

- [ ] `getBattery` → `android.battery`
- [ ] `getClipboard` → `android.clipboard`
- [ ] `setClipboard` → `android.clipboard`
- [ ] `sendNotification` → `android.notification`
- [ ] `getNetworkInfo` → `android.wifi`
- [ ] `readFile` → `android.storage` or `termux.filesystem`
- [ ] `writeFile` → `android.storage` or `termux.filesystem`
- [ ] `runPython` → `termux.python`
- [ ] `runGit` → `termux.git`
- [ ] `httpRequest` → `termux.http`
- [ ] `runShell` → `termux.shell`

## 6. Runtime Passport

- [ ] `python3 flowcore.py boot` succeeds
- [ ] `~/.flowcore/flowcore.runtime.json` is present and valid JSON
- [ ] `generated_at` timestamp is recent (within last 24 hours)
- [ ] `is_android` is `true`
- [ ] `is_termux` is `true`

## 7. Wake Lock

- [ ] `termux-wake-lock` is available (`which termux-wake-lock`)
- [ ] FlowCore acquires wake lock before long-running tasks
- [ ] Wake lock is released when tasks complete

## 8. Network

- [ ] DNS resolution works (`python3 -c "import socket; socket.getaddrinfo('8.8.8.8', None)"`)
- [ ] HTTPS reachable (`curl -sS https://example.com`)
- [ ] Required remote hosts are reachable (set `FLOWCORE_ORACLE_HOST` if used)

## 9. Storage Validation

- [ ] `~/storage/shared` symlink exists
- [ ] FlowCore can read and write to `~/storage/shared/FlowCore/`
- [ ] `~/.flowcore/` directory exists with `logs/`, `data/`, `services/` subdirs

## 10. Python Dependencies

- [ ] `python3 -m pip install -r requirements.txt` succeeds
- [ ] `import loguru` works
- [ ] `import aiosqlite` works (if API server is used)

## 11. Doctor Green

- [ ] `python3 flowcore.py doctor` shows 0 FAIL
- [ ] Any WARN items are reviewed and accepted or resolved

## 12. Final Boot Test

```bash
python3 flowcore.py boot --verbose
python3 flowcore.py status
python3 flowcore.py selftest
```

All three commands must complete without errors.

---

## Quick Reference: Common Fixes

| Issue | Fix |
|-------|-----|
| Termux:API missing | `pkg install termux-api` |
| Storage not set up | `termux-setup-storage` |
| Battery killed | Settings → Battery → Termux → Unrestricted |
| pkg update fails | `pkg update && pkg upgrade -y` |
| pip missing | `python3 -m ensurepip --upgrade` |
| Runtime Passport stale | `python3 flowcore.py boot` |
| Corrupted environment | `python3 flowcore.py repair` |

---

*Last updated: Sprint 9 — Runtime Kernel*
