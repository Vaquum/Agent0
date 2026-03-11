# Self-Reflection

**Status:** Stable

**Context:** This page covers how Agent0's self-reflection works and what it produces. Intended for anyone using or managing an Agent0 deployment.

**Outcome:** After reading, you will understand when reflections happen, what they produce, and how to monitor them.

## How It Works

After Agent0 reviews and merges enough PRs, it automatically selects one and performs a post-mortem reflection. The reflection produces an RFC (Request for Comments) issue on the Agent0 repository with observations and proposed improvements.

**Trigger:** A reflection scan runs approximately every 10 minutes. If at least 6 new merged PRs that Agent0 reviewed have accumulated since the last reflection, one reflection is fired for that batch.

**Output:** A GitHub issue using the RFC template, filed on the Agent0 repository.

## What Gets Reflected On

Agent0 tracks merged PRs across all whitelisted organizations. When at least 6 new merged PRs have accumulated since the last reflection scan, it picks one of those PRs at random and reflects on it. Any additional PRs beyond that first batch of 6 are considered as part of the same scan and will not trigger extra reflections until more PRs are merged. The reflection examines:

- The PR description and code changes
- Reviews and inline comments
- Conversation thread
- CI results

## What the RFC Contains

The RFC issue captures patterns, lessons learned, and proposed changes that emerged from reviewing the PR. These may include observations about code quality, testing gaps, workflow improvements, or tooling suggestions.

## Monitoring

Reflection activity appears in the daemon logs:

- `Reflection scan: N new merged PRs, need 6 to trigger` — below threshold, no action
- `Reflection scan: N new merged PRs >= 6, reflecting on owner/repo#number` — reflection triggered
- `Phase 1: reflecting on owner/repo#number` — open-ended reflection in progress
- `Phase 2: creating RFC from reflection on owner/repo#number` — RFC creation in progress
- `RFC created: https://github.com/...` — reflection complete

## Configuration

No additional configuration is needed. Self-reflection uses the existing `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, and `WHITELISTED_ORGS` settings.
