# Disposition Ledger

**Status:** Stable

**Context:** What you will see in the body of an Agent0 PR review. Intended for anyone whose PR Agent0 reviews — authors, reviewers, and observers.

**Outcome:** After reading, you understand the Disposition Ledger that appears in every Agent0 review and can trust what each row claims.

## What It Is

When Agent0 reviews your pull request, the review summary includes a **Disposition Ledger**: a compact list giving every outstanding finding a written verdict. The findings are gathered from *every* source on the PR — human reviewer comments, automated bot comments, and failing CI checks — so none is left wondering whether it registered.

## What You Will See

The ledger appears in the review body, ordered by blast radius (broadest impact first):

```
Disposition Ledger (ordered by blast radius):
- [high]  bot: unbounded retry on 5xx — confirmed, blocking. See inline on poller.py:88.
- [med]   reviewer @x: dedup key collision — addressed in a1b2c3d.
- [med]   CI: pyright failing on executor.py — confirmed, blocking; type error is real.
- [low]   reviewer @y: rename suggestion — carry-forward, noted for follow-up.
```

Each row carries:

- A **blast-radius grade** in brackets — `high`, `med`, or `low` — for how widely the problem would spread if it merged.
- The **source** of the finding — a reviewer, a bot, or CI.
- A short description and a **disposition**, one of:
  - **addressed** — fixed; the row cites the commit or line that resolved it.
  - **confirmed** — still a real problem and blocking.
  - **refuted** — looked into and shown not to be a problem, with the reason given.
  - **carry-forward** — real, but out of scope for this PR; named for a follow-up.

## Why It Matters

- **No source is second-class.** A terse bot comment and a failing check get the same written verdict as the most eloquently-argued human review.
- **"Addressed" is verifiable.** Because every row is a written decision that cites its evidence, a later reviewer can trust the word "addressed" without re-deriving it.
- **No red check merges silently.** A failing CI check always receives a written verdict explaining why it is safe to merge — or that it is not.

Agent0 will not submit a review verdict while any finding is left without a disposition. If you see the ledger, every participant's finding has been accounted for.

## References

- `docs/Developer/Disposition-Ledger.md` — how it is implemented.
- `docs/CI-Failures.md` — how Agent0 handles failing CI checks.
