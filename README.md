<h1 align="center">
  <br>
<a href="https://github.com/Vaquum"><img src="https://github.com/Vaquum/Home/raw/main/assets/Logo.png" alt="Vaquum" width="150"></a>
<br>
</h1>
<h3 align="center">Agent0 is an autonomous software engineer that lives on GitHub.</h3>
<p align="center">
<a href="#value-proposition">Value Proposition</a> •
<a href="#quick-start">Quick Start</a> •
<a href="#contributing">Contributing</a> •
<a href="#license">License</a>
</p>
<hr>

# Value Proposition

Agent0 polls GitHub notifications, classifies actionable events (mentions, assignments, review requests, CI failures), runs Claude Code tasks in isolated workspaces, and posts results back — all without human intervention.

# Quick Start

If your environment is already configured, use these three examples:

1) Running the app

```bash
make dev
```

2) Checking the dashboard

```bash
curl http://localhost:9999/health
```

3) Triggering Agent0

```
@your-agent-github-user please fix the typo in README.md
```

For complete setup, configuration, and deployment instructions, see [Get Started](docs/Developer/Setup.md).

# Contributing

The simplest way to contribute is by joining open discussions or picking up an issue:

- [Open discussions](https://github.com/Vaquum/Agent0/issues?q=is%3Aissue%20state%3Aopen%20label%3Aquestion%2Fdiscussion)
- [Open issues](https://github.com/Vaquum/Agent0/issues)

Before contributing, start with [Get Started](docs/Developer/Setup.md).

# Vulnerabilities

Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/Vaquum/Agent0/security/advisories/new).

# Citations

If you use Agent0 for published work, please cite:

Agent0 [Computer software]. (2026). Retrieved from http://github.com/vaquum/agent0.

# License

[MIT License](LICENSE).
