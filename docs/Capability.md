# Agent0 Authors a PR

**Status:** Stable

**Context:** This page describes Agent0's full PR authoring lifecycle. Intended for users who want to understand what happens after Agent0 creates a pull request.

**Outcome:** After reading, you will understand each step of Agent0's PR lifecycle and the GitHub triggers that drive it.

When Agent0 creates a pull request, it owns the full lifecycle until a human merges or closes it. Every review, comment, and CI failure is picked up and acted on automatically.

| Step | What happens | GitHub trigger |
|------|-------------|----------------|
| 1. Human assigns issue | Agent0 creates a branch, implements the changes, and opens a PR | `assign` |
| 2. Human reviews PR (changes requested) | Agent0 reads the review, makes fixes, and pushes | `author` |
| 3. Human reviews again (round 2+) | Agent0 picks up the new review and addresses it | `author` |
| 4. Human leaves comments | Agent0 reads and responds to each round of comments | `author` |
| 5. CI fails on Agent0's push | Agent0 reads the failure output, fixes the code, and pushes | `ci_activity` |
| 6. Human merges | No action needed from Agent0 | — |

Steps 2 through 5 repeat as many times as needed. Agent0 keeps responding to new activity on the PR until the human is satisfied and merges.

## How It Works

GitHub sends a notification whenever there is new activity on a thread where Agent0 is a participant. Each notification carries a **reason** that tells Agent0 why it was notified:

| Reason | Meaning | Agent0 action |
|--------|---------|---------------|
| `assign` | Agent0 was assigned to an issue | Read the issue, implement, open a PR |
| `mention` | Someone @mentioned Agent0 | Read the mention and respond |
| `author` | Activity on something Agent0 authored | Read the new activity and act on it |
| `review_requested` | Someone requested Agent0's review | Review the PR and submit feedback |
| `ci_activity` | CI checks completed | If checks failed on Agent0's PR, fix and push |

## Multi-Round Reviews

Agent0 tracks notifications by their thread ID and `updated_at` timestamp. When a human leaves a new review or comment, GitHub updates the timestamp on the existing thread. Agent0 detects the change and processes the notification again with fresh context.

This means there is no limit on the number of review rounds. Each new piece of activity produces a new timestamp, which triggers Agent0 to fetch the latest state of the PR (diff, comments, review comments) and respond accordingly.

## Bot Reviews

GitHub does not generate notifications for bot activity (e.g. Copilot reviews). Agent0 only sees notifications triggered by humans. To have Agent0 address a bot review, @mention it in a comment on the PR.

## Self-Trigger Protection

When Agent0 pushes fixes or leaves comments on its own PR, GitHub generates notifications for that activity. Agent0 detects that the last comment was authored by itself and skips the notification. This prevents infinite loops where Agent0 would keep responding to its own actions.

The one exception is CI failures: even though Agent0 triggered the CI run by pushing, a failing check still needs to be fixed, so CI notifications bypass the self-trigger filter.

## Concurrency

Agent0 processes one task per repository at a time. If multiple notifications arrive for the same repo, they queue up and execute in order. Different repositories run in parallel.
