# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

FlowCore takes security seriously. If you discover a vulnerability, please report it privately.

**Do NOT open a public issue for security vulnerabilities.**

### How to Report

1. Create a new issue with the `security` label
2. Mark it as confidential (if using GitHub)
3. Alternatively, contact the maintainer directly

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if available)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Assessment:** Within 1 week
- **Patch:** Within 2 weeks for critical issues

## Security Architecture

FlowCore is designed with the following security principles:

| Principle | Implementation |
|-----------|---------------|
| No network exposure | API binds to `127.0.0.1` by default |
| No privilege escalation | `auto_root: false`, no sudo dependencies |
| No hardcoded secrets | All credentials via environment variables |
| No dangerous calls | No `os.system()` or `subprocess` with user input |
| Minimal attack surface | Pure-Python dependencies, no C extensions |

## Security Audit

Run the built-in security audit at any time:

```bash
python3 scripts/audit.py
```

This checks for:
- Hardcoded Linux paths
- Sudo/root commands
- Network-exposed API binding
- Dangerous system calls
- Exposed credentials
- Python version compatibility
