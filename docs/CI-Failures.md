# CI Failure Handling

**Status:** Stable

**Context:** How Agent0 detects and responds to CI failures on open pull requests. Intended for users who want to understand Agent0's automated CI fix behavior.

**Outcome:** After reading, you understand when Agent0 acts on CI failures, what it does, and how to control this behavior.

## How It Works

Every 5 poll cycles (approximately 2.5 minutes at default settings), Agent0 scans for CI failures across all whitelisted organizations:

1. Searches GitHub for recently-updated open PRs authored by the agent
2. Fetches check suite status for each PR's head commit
3. Identifies PRs where checks have failed
4. Spawns a Claude Code task to analyze and fix the failure

## What Agent0 Does

When a CI failure is detected, Agent0:

- Clones or updates the repository workspace
- Checks out the PR branch
- Analyzes the failing CI logs
- Attempts to fix the issue and push a new commit
- Posts a comment on the PR explaining what was changed

## Scope

Agent0 only acts on CI failures for PRs it authored. It does not intervene in PRs created by other users unless explicitly mentioned.

## Limitations

- Only check suite conclusions are inspected (not individual check runs)
- If multiple CI systems report, all must pass for the PR to be considered green
- Agent0 will not retry indefinitely — each CI failure produces one fix attempt per scan cycle
