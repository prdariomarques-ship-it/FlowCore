# FlowCore Frontend Deployment Guide

Safe, reversible frontend updates for FlowCore.

## Quick Deploy

```bash
# 1. Download new version (or copy new index.html)
cp /path/to/new/index.html .

# 2. Deploy safely (creates automatic backup)
bash deploy-flowcore.sh index.html

# 3. Verify in browser (clear cache if needed)
# Open: http://localhost:8080 (or your URL)
# Chrome: Ctrl+Shift+Del | Safari: Cmd+Shift+Del
```

## What Gets Updated

✅ **Only frontend files are modified:**
- `web/index.html` - Dashboard UI, navigation, styling

✅ **What's preserved (NOT touched):**
- Backend (`api/`, `agents/`, `flowcore.py`)
- Database (all stored data)
- Configuration (`~/.flowcore/ai.json`)
- API keys, tokens, secrets
- Environment variables

## Safety Features

- ✅ Automatic timestamped backups before deployment
- ✅ HTML validation before and after deployment
- ✅ File permission preservation
- ✅ Verification of successful deployment
- ✅ One-command rollback if something breaks

## Rollback (If Something Goes Wrong)

```bash
# Automatic rollback to latest backup
bash rollback-flowcore.sh --latest

# Or specify a specific backup
bash rollback-flowcore.sh backups/index.html.20260905_183045.bak

# List all available backups
ls -lh backups/index.html.*.bak
```

## Advanced Usage

### Custom Web Path

If FlowCore is installed elsewhere:

```bash
FLOWCORE_WEB_PATH=/opt/flowcore/web bash deploy-flowcore.sh index.html
```

### Custom Backup Location

```bash
BACKUP_DIR=/mnt/backups bash deploy-flowcore.sh index.html
```

### View Deployment Logs

Logs are printed to console. Save to file:

```bash
bash deploy-flowcore.sh index.html 2>&1 | tee deployment.log
```

## Troubleshooting

### 1. Changes Don't Appear

**Problem:** Updated HTML deployed but old version shows in browser

**Solution:**
```bash
# Clear browser cache:
# Chrome: Ctrl+Shift+Del → Clear all
# Safari: Cmd+Shift+Del → Clear all
# Firefox: Ctrl+Shift+Del

# Or open in private/incognito window
```

### 2. Deployment Failed

**Check script output** - It will show:
- Path validation errors
- HTML validation failures  
- File permission issues

**Fix and retry:**
```bash
bash deploy-flowcore.sh index.html
```

### 3. Frontend Broke After Deploy

**Instant recovery:**
```bash
bash rollback-flowcore.sh --latest
```

Then investigate what went wrong in the backup.

### 4. Backend Not Responding

**This is NOT a frontend issue.** Check backend:

```bash
# Is FlowCore running?
pgrep -f flowcore

# Restart backend
cd ~/FlowCore && bash deploy/restart.sh

# Frontend deployment won't restart backend
```

## Deployment Process Details

```
┌─────────────────────────────────────────┐
│ 1. Validate Input File                  │
│    - Check HTML structure               │
│    - Verify key elements present        │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│ 2. Create Timestamped Backup            │
│    - Save current index.html            │
│    - Stored in backups/ directory       │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│ 3. Deploy New File                      │
│    - Copy to web/index.html             │
│    - Preserve file permissions          │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│ 4. Verify Deployment                    │
│    - File exists and has content        │
│    - Key elements present               │
│    - All checks passed                  │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│ ✅ Success!                             │
│    Backup location: backups/...         │
│    Ready for testing                    │
└─────────────────────────────────────────┘
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FLOWCORE_WEB_PATH` | `/home/user/flowcore/web` | Frontend directory |
| `BACKUP_DIR` | `/home/user/flowcore/backups` | Backup storage location |

## Permissions

Both scripts require:
- Read access to source file
- Write access to `FLOWCORE_WEB_PATH`
- Write access to `BACKUP_DIR`

If you get permission errors:

```bash
# Fix permissions
chmod 755 deploy-flowcore.sh rollback-flowcore.sh
sudo chown $USER:$USER /path/to/backups
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Deploy FlowCore Frontend
  run: |
    cd ~/FlowCore
    bash deploy-flowcore.sh web/index.html
```

### Before Merging

```bash
# Local validation before push
bash deploy-flowcore.sh index.html.new
# Open browser to verify
# If OK, commit and push
# If broken, rollback automatically created backup
bash rollback-flowcore.sh --latest
```

## FAQ

**Q: Will this restart FlowCore?**
A: No. The script only updates frontend files. Backend keeps running.

**Q: Can I use this for backend updates?**
A: No. This is frontend-only. Backend updates need separate process.

**Q: How many backups are kept?**
A: All of them (timestamped). You can delete old ones: `rm backups/index.html.*.bak`

**Q: Is deployment atomic?**
A: Effectively yes. Either the full deployment succeeds or everything rolls back.

**Q: Can I deploy while FlowCore is running?**
A: Yes, safe to deploy while backend is running. Just clear browser cache.

**Q: What if backup creation fails?**
A: Deployment stops (exits with error). Checks for backup directory existence.

## Support

If deployment fails:

1. **Check script output** - Shows exact error
2. **View latest backup** - `ls -lh backups/ | tail -1`
3. **Rollback if needed** - `bash rollback-flowcore.sh --latest`
4. **Review change** - What was different in the new HTML?

---

**Last Updated:** 2026-09-05  
**Version:** 1.0  
**Status:** Production-ready
