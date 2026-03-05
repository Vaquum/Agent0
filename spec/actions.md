# Actions Specification

## 1. Overview

Agent0 performs exactly four types of actions. Each action is triggered by a specific
GitHub event and follows a defined workflow. The action type is determined by the router
and shapes the prompt given to the Claude Code executor.

| # | Trigger | Action |
|---|---|---|
| 1 | Assigned to issue (implementation task) | Code the solution, create a PR |
| 2 | Assigned to issue (spec task) | Write the spec, post it in the issue |
| 3 | Assigned as reviewer to PR | Review the code, approve or request changes |
| 4 | @mentioned in issue or PR | Read the context, post a comment |

## 2. Action 1: Code and PR

### Trigger

- Notification reason: `assign`
- Subject type: `Issue`
- The issue describes a task that requires code changes (implementation, bug fix,
  refactor, etc.)

### How the Router Decides This vs. Action 2

The router does not make this decision. The Claude Code executor receives the full
issue context and decides whether the task requires code (Action 1) or a spec
(Action 2). The prompt instructs Claude Code to make this judgment:

- If the issue asks for implementation, code changes, bug fixes, feature additions,
  refactoring, or any work that results in code → Action 1 (code and PR)
- If the issue asks for a specification, design document, architecture plan, research,
  or analysis → Action 2 (write spec in issue)

### Workflow

1. Read the issue title, body, labels, and conversation
2. If the task is unclear, comment asking for clarification and stop
3. Create a branch: `agent0/{issue-number}-{short-description}`
4. Implement the changes
5. Run tests if a test command is available (from `CLAUDE.md` or detected)
6. Commit with a clear message referencing the issue
7. Push the branch
8. Create a PR:
   - Title: concise description of the change
   - Body: summary of what was done, why, and how. Include `Closes #{number}`
9. Comment on the issue: brief summary of what was done with a link to the PR

### Branch Naming

`agent0/{issue-number}-{short-description}`

Examples:
- `agent0/42-fix-login-validation`
- `agent0/15-add-retry-logic`
- `agent0/7-refactor-config-loading`

### Commit Messages

Follow conventional style:
- `fix: correct login validation for empty passwords (#42)`
- `feat: add retry logic to API client (#15)`
- `refactor: simplify config loading (#7)`

If the repo's `CLAUDE.md` specifies a different commit message convention, follow that.

## 3. Action 2: Spec and Post

### Trigger

- Notification reason: `assign`
- Subject type: `Issue`
- The issue describes a task that requires a specification, design, research, or
  analysis rather than code changes

### Workflow

1. Read the issue title, body, labels, and conversation
2. If the task is unclear, comment asking for clarification and stop
3. Read relevant code in the repo to inform the spec (if applicable)
4. Write the specification or analysis
5. Post the spec as a comment on the issue in markdown format
6. If the spec is very long, break it into sections with clear headings

### Output Format

The spec is posted as a single issue comment using GitHub-flavored markdown. Example
structure:

```markdown
## Specification: {title}

### Overview
{high-level summary}

### Details
{detailed specification}

### Open Questions
{any unresolved questions or decisions needed}
```

The exact format depends on what the issue asks for — Claude Code has judgment to
structure the response appropriately.

## 4. Action 3: Review PR

### Trigger

- Notification reason: `review_requested`
- Subject type: `PullRequest`

### Workflow

1. Read the PR title, description, and conversation
2. Read the diff
3. Check out the PR branch if needed to inspect files in full context
4. Review the code for:
   - Correctness — does the logic do what it claims?
   - Bugs — are there edge cases, off-by-one errors, null handling issues?
   - Tests — are changes tested? Are tests meaningful?
   - Style — does the code follow the repo's conventions?
   - Security — are there injection risks, leaked secrets, unsafe operations?
   - Clarity — is the code readable and well-structured?
5. Submit the review:
   - **Approve** (`gh pr review {number} --approve`) if the code is good
   - **Request changes** (`gh pr review {number} --request-changes`) if there are
     issues that must be fixed before merging
   - The review body should list specific findings with file/line references

### Review Style

- Be constructive and specific
- Reference exact lines or code blocks
- Distinguish between blocking issues ("must fix") and suggestions ("consider")
- If the PR is large, organize feedback by file
- If the overall approach is wrong, say so clearly rather than listing minor issues

### What It Does NOT Do

- Does not merge PRs
- Does not push changes to the PR branch (only the PR author does that)
- Does not dismiss other reviews

## 5. Action 4: Comment on Mention

### Trigger

- Notification reason: `mention`
- Subject type: `Issue` or `PullRequest`
- Someone wrote `@zero-bang` in a comment

### Workflow

1. Read the full issue/PR context (title, body, conversation)
2. Read the specific comment that mentions `@zero-bang`
3. Parse what is being asked — the text after `@zero-bang`
4. Respond appropriately:
   - If it's a question about the code → read the relevant code and answer
   - If it's a request for information → research and respond
   - If it's a request to do something → do it (may escalate to Action 1 or 2)
   - If it's unclear → ask for clarification
5. Post the response as a comment on the issue/PR

### Scope

The mention response is context-dependent. `@zero-bang` can be asked to:

- Answer questions ("@zero-bang what does this function do?")
- Give opinions ("@zero-bang should we use approach A or B?")
- Do small tasks ("@zero-bang add a docstring to this function")
- Provide information ("@zero-bang what's the test coverage for this module?")

If the request is substantial enough to warrant a PR (code changes), Claude Code
creates a branch and PR just like Action 1. The prompt gives it judgment to decide.

## 6. Decision: Code vs. Spec

When assigned to an issue, Claude Code must decide whether to produce code (Action 1)
or a spec (Action 2). The decision heuristic in the prompt:

**Code (Action 1)** when the issue:
- Uses words like "implement", "fix", "add", "build", "create", "refactor", "update"
- Describes a bug to fix
- Describes a feature to build
- Has labels like `bug`, `feature`, `enhancement`
- References specific files or functions to change

**Spec (Action 2)** when the issue:
- Uses words like "design", "specify", "spec", "plan", "research", "analyze", "propose"
- Asks for a document or write-up
- Asks for architecture or design decisions
- Has labels like `spec`, `design`, `documentation`, `rfc`
- Asks "how should we..." rather than "please implement..."

When ambiguous, Claude Code defaults to commenting on the issue asking whether the
requester wants code or a spec.

## 7. Error Behavior

For all actions, if Claude Code encounters a problem it cannot resolve:

1. Comment on the issue/PR explaining what went wrong
2. The comment should be specific: "I tried to run the tests but got error X"
3. Do not leave the task silently incomplete — always communicate status
