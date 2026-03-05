# Behavioral Contracts

Agent0 has four atomic behaviors. Each behavior is triggered by a GitHub notification and produces observable side-effects on the repository. This document defines the expected contract for each behavior and provides a runbook for manual validation.

## Behaviors

| # | Behavior | Trigger | Prompt |
|---|----------|---------|--------|
| 1 | **Respond to mention** | `@zero-bang` in issue or PR comment | `MENTION_ISSUE` / `MENTION_PR` |
| 2 | **Work on assigned issue** | Issue assigned to `zero-bang` | `ASSIGNED_ISSUE` |
| 3 | **Review a PR** | Review requested from `zero-bang` | `REVIEW_PR` |
| 4 | **Fix CI failure** | Check suite fails on Agent0's own PR | `CI_FAILURE` |

---

## 1. Respond to mention

### Contract

When `@zero-bang` is mentioned in a comment on an issue or PR, Agent0 must:

- **Question** — answer by commenting on the same thread
- **Task (no code)** — do the work (e.g. create an issue) and comment with what it did
- **Task (code change)** — create branch `agent0/{short-description}`, implement, commit, push, open PR, comment with summary
- **PR mention** — reply on the PR thread using `gh pr comment`

Agent0 must never ignore a mention. If the request is unclear, it must ask for clarification rather than guessing.

### Test scenarios

#### 1a. Question on issue

**Setup**: Create an issue, comment mentioning `@zero-bang` with a technical question about the codebase.

**Expected**: Agent0 replies on the same issue with a substantive answer. No branches created, no PRs opened.

**Verify**:
```bash
gh api repos/{owner}/{repo}/issues/{number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {body: .body[0:200]}'
```

#### 1b. Create a new issue from mention

**Setup**: Create an issue asking `@zero-bang` to create a separate issue with a spec for some feature.

**Expected**: Agent0 creates a new issue with the spec and comments back on the original issue with a link.

**Verify**:
```bash
# Check new issue was created by zero-bang
gh api repos/{owner}/{repo}/issues --jq '.[] | select(.user.login=="zero-bang") | {number, title}'
# Check comment on original issue
gh api repos/{owner}/{repo}/issues/{number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {body: .body[0:200]}'
```

#### 1c. Make a PR from mention

**Setup**: Create an issue describing a small code change, mention `@zero-bang` and ask it to make a PR.

**Expected**: Agent0 creates branch `agent0/{name}`, implements the change, opens a PR with "Closes #{number}", and comments on the issue.

**Verify**:
```bash
# Check PR was created
gh pr list --repo {owner}/{repo} --author zero-bang --state open
# Check PR body references the issue
gh api repos/{owner}/{repo}/pulls/{pr_number} --jq '.body'
# Check branch naming
gh api repos/{owner}/{repo}/pulls/{pr_number} --jq '.head.ref'
# Check comment on original issue
gh api repos/{owner}/{repo}/issues/{number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {body: .body[0:200]}'
```

#### 1d. Multi-round discussion (3+ rounds)

**Setup**: Create an issue with a question, let Agent0 respond, then reply with a follow-up, repeat at least 3 times.

**Expected**: Agent0 responds to each follow-up, maintaining full conversational context. Each response directly addresses the specific question asked in that round.

**Verify**: Read the full thread — each response should reference prior context and directly address the new question. No repeated or generic answers.

#### 1e. Mention on PR

**Setup**: Comment on an open PR mentioning `@zero-bang` with a question about the code changes.

**Expected**: Agent0 replies on the PR thread using `gh pr comment`. Response addresses the specific question about the diff.

**Verify**:
```bash
gh api repos/{owner}/{repo}/issues/{pr_number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {body: .body[0:200]}'
```

---

## 2. Work on assigned issue

### Contract

When an issue is assigned to `zero-bang`, Agent0 must:

1. Read the issue body and conversation
2. If the task is clear: create branch `agent0/{short-description}`, implement, commit, push, open PR with "Closes #{number}", comment on issue
3. If the task is unclear: comment asking for clarification (do not guess)

### Test scenario

**Setup**: Create an issue with a clear, small task. Assign it to `zero-bang`.

**Expected**: Agent0 creates a branch, implements the change, opens a PR referencing the issue, and comments on the issue with a summary.

**Verify**:
```bash
# Check PR was created referencing the issue
gh pr list --repo {owner}/{repo} --author zero-bang --state open
gh api repos/{owner}/{repo}/pulls/{pr_number} --jq '.body' | grep "Closes #"
# Check comment on issue
gh api repos/{owner}/{repo}/issues/{number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {body: .body[0:200]}'
```

---

## 3. Review a PR

### Contract

When a review is requested from `zero-bang`, Agent0 must:

**First review**:
- Read the diff, check for bugs, edge cases, missing tests, style, security
- Check existing review threads — reply +1 to duplicates, never open new thread on same issue
- Submit exactly ONE review event with inline comments on specific files/lines
- Never use `gh pr comment` or `gh issue comment` for review feedback
- If clean: approve with "LGTM"
- If issues found: request changes with inline comments

**Re-review** (after author pushes fixes and re-requests review):
- Only verify previously raised comments — do NOT look for new issues
- For each previous comment: check if the issue was fixed in current diff
- If all resolved: approve
- If some remain: reply to unresolved threads, request changes

### Test scenarios

#### 3a. First review with issues

**Setup**: Create a PR with code that has deliberate bugs. Request review from `zero-bang`.

**Expected**: Agent0 submits CHANGES_REQUESTED with inline comments on specific files and lines.

**Verify**:
```bash
# Check review state
gh api repos/{owner}/{repo}/pulls/{number}/reviews \
  --jq '.[] | select(.user.login=="zero-bang") | {state, body: .body[0:200]}'
# Check inline comments exist
gh api repos/{owner}/{repo}/pulls/{number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {path, line, body: .body[0:100]}'
```

#### 3b. Re-review after partial fix

**Setup**: Fix some of the issues Agent0 found, leave others. Push and re-request review.

**Expected**: Agent0 identifies which issues are fixed and which remain. Submits CHANGES_REQUESTED. Replies to unresolved threads.

**Verify**:
```bash
# Latest review should be CHANGES_REQUESTED
gh api repos/{owner}/{repo}/pulls/{number}/reviews \
  --jq '.[-1] | {state, body: .body[0:300]}'
```

#### 3c. Re-review after full fix — approval

**Setup**: Fix all remaining issues. Push and re-request review.

**Expected**: Agent0 confirms all issues resolved and submits APPROVED.

**Verify**:
```bash
# Latest review should be APPROVED
gh api repos/{owner}/{repo}/pulls/{number}/reviews \
  --jq '.[-1] | {state, body: .body[0:300]}'
```

---

## 4. Fix CI failure

### Contract

When CI checks fail on a PR authored by `zero-bang`, Agent0 must:

1. Read the failure output
2. Look at the relevant code
3. Fix the issue on the current branch
4. Commit and push
5. Comment on the PR with what was fixed

### Test scenario

**Note**: This requires a repository with CI configured (GitHub Actions). Cannot be tested without a real CI pipeline.

**Setup**: Ensure Agent0 has an open PR. Introduce a CI failure (e.g. failing test, lint error).

**Expected**: Agent0 reads the failure, pushes a fix commit, and comments on the PR.

**Verify**:
```bash
# Check for new commits after CI failure
gh api repos/{owner}/{repo}/pulls/{number}/commits --jq '.[-1] | {sha: .sha[0:8], message: .commit.message}'
# Check comment explaining fix
gh api repos/{owner}/{repo}/issues/{number}/comments \
  --jq '.[] | select(.user.login=="zero-bang") | {body: .body[0:200]}' | tail -1
```

---

## Running the full validation

Prerequisites:
- Agent0 Docker container running (`docker ps --filter name=agent0`)
- GitHub token with repo access configured
- `gh` CLI authenticated

The tests should be run sequentially. Each test creates real GitHub artifacts (issues, PRs, comments, branches) on the target repository. After validation, close test PRs and issues.

Typical run: ~15 minutes, ~$3-5 in API costs.
