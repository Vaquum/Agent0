# Disposition Ledger

**Status:** Stable

**Context:** How Agent0's PR-review prompts force every outstanding finding — from any participant — into an explicit, written verdict before a review is submitted. Intended for engineers maintaining the review prompts in `src/agent0/prompts.py`.

**Outcome:** After reading, you can explain what the Disposition Ledger is, which prompt steps produce and gate it, and how to extend or test it.

## Overview

A PR review used to let a finding's fate track the quality of its *argument* rather than the severity of the *bug*: eloquently-argued catches got fixed, terse or bot findings drifted, and a red CI check could merge without anyone stating why it was safe. The Disposition Ledger makes every finding's fate an explicit, written decision and orders scrutiny by blast radius rather than rhetoric.

The change is entirely in the `REVIEW_PR` and `RE_REVIEW_PR` templates in `src/agent0/prompts.py`. No executor or router logic changes; the ledger is rendered inline in the review body and is produced by the existing prompt-driven review.

## Concepts

- **Participant** — any source of a finding on the PR: a human reviewer thread, a bot comment, or a failing CI check. Each is treated as a first-class participant whose finding deserves a written disposition.
- **Disposition** — one of four written verdicts a finding can receive:
  - `addressed` — fixed; cites the resolving commit SHA or `file:line`.
  - `confirmed` — still a real problem; blocking.
  - `refuted` — investigated and shown not to be a problem; gives reasoning.
  - `carry-forward` — real but out of scope; named for a follow-up.
- **Blast radius** — the breadth of harm if the finding is real and merges (call sites, users, downstream consumers affected), graded `high` / `med` / `low`. The ledger is ordered by this, descending.
- **Disposition Ledger** — the structured list, emitted in the review body, of every outstanding finding with its disposition and blast-radius grade.

## How It Works

In `REVIEW_PR`:

1. **Gather (step 2).** After reading the diff, the review enumerates outstanding findings from all three participant classes:
   - Human reviewer threads and bot comments via `gh api repos/{owner}/{repo}/pulls/{number}/comments`.
   - Failing CI checks via `gh api repos/{owner}/{repo}/commits/{head_ref}/check-runs` (a check-run fetch failure is surfaced loudly, never silently skipped — per the no-silent-failures contract).
2. **Disposition & grade (step 4).** Each finding is assigned one of the four dispositions with its required justification and a blast-radius grade, then ordered descending.
3. **Gate (hard rule).** No verdict may be submitted while any ledger row's disposition is blank. A `refuted` or `carry-forward` is valid; a blank is not. Every `addressed` must cite a commit or line; every `refuted` must give reasoning; a red CI check must receive a written safe-to-merge or blocking disposition.
4. **Render (step 5).** The ledger is emitted in the review body, including on a clean approval (where it states there were no outstanding findings).

In `RE_REVIEW_PR`, the per-thread reply loop is extended so bot threads and previously-red checks each receive a written disposition reply, not only the agent's own prior threads. A previously-red check has no inline thread, so its disposition is stated in the review body. Because `RE_REVIEW_PR` is not passed a `head_ref`, it resolves the head SHA inline via `gh api repos/{owner}/{repo}/pulls/{number} --jq .head.sha` before fetching check-runs.

## Why check-runs are fetched in-prompt

`REVIEW_PR` receives `formatted_comments` (the human and bot conversation) and `head_ref`, but it is **not** passed `check_failures` (that is a `CI_FAILURE`-event input). The ledger therefore fetches check-run status with `gh api` at review time rather than relying on a template placeholder.

## Testing

Contract tests in `tests/test_prompts.py`:

- `test_review_pr_has_disposition_ledger` — the ledger and the four dispositions are present.
- `test_review_pr_enumerates_all_participants` — human threads, bot comments, and `check-runs` are all enumerated.
- `test_review_pr_gates_verdict_on_blank_disposition` — a verdict cannot be submitted while any row is blank, and a red check must carry a disposition.
- `test_re_review_pr_dispositions_all_participants` — the re-review loop covers bots and checks.

## References

- `src/agent0/prompts.py` — `REVIEW_PR` and `RE_REVIEW_PR` templates.
- `tests/test_prompts.py` — contract tests.
- `docs/Disposition-Ledger.md` — the user-facing view.
- Issue #114 (RFC) — the proposal this implements.
