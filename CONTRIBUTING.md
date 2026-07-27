# Contributing to FlowCore

Thank you for your interest in contributing to FlowCore. This document explains how to contribute effectively.

## Branch Strategy

The project follows a simple branching model:

| Branch | Purpose |
|--------|---------|
| `main` | Stable, production-ready code. Only merged via PRs. |
| `feature/*` | New features and enhancements. |
| `fix/*` | Bug fixes. |
| `release/*` | Release preparation branches. |

All work goes through Pull Requests. Direct pushes to `main` are prohibited.

## Development Setup

```bash
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
bash install.sh
```

## Code Style

The project enforces consistent code style through automated checks:

| Tool | Purpose |
|------|---------|
| Ruff | Python linting and formatting |
| Black | Python code formatting (line length 88) |
| ShellCheck | Shell script validation |

Run locally before pushing:

```bash
pip install ruff black
ruff check .
black --check .
```

## Testing

All code changes must include tests. Run the full test suite before opening a PR:

```bash
python3 flowcore.py selftest
```

The self-test validates imports, configuration, database, API endpoints, and CLI commands.

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes and add tests
3. Run `python3 flowcore.py selftest` — must pass
4. Update CHANGELOG.md if applicable
5. Push and open a Pull Request
6. Fill out the PR template completely

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code refactoring |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance tasks |
| `ci:` | CI/CD changes |
| `perf:` | Performance improvements |

Example: `feat(executor): add retry with exponential backoff`

## Security Guidelines

- Never commit credentials, API keys, or tokens
- API must always bind to `127.0.0.1` by default
- No `sudo`, `os.system()`, or `subprocess` with user input
- Report security issues via [SECURITY.md](SECURITY.md)

## Releasing

Releases are managed via GitHub Actions. To create a release:

```bash
git tag v1.1.0
git push origin v1.1.0
```

The `release.yml` workflow will automatically create the GitHub Release and update CHANGELOG.md.
