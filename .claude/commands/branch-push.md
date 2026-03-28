---
description: Create branch, commit all changes, push, and optionally merge into main
argument-hint: "merge" to also merge into main, or leave empty to just push
---

# Git Branch, Commit & Push Workflow

You are executing an automated git workflow. Follow these steps precisely.

## Step 1: Pre-flight checks

Run these in parallel:
- `git status` (never use `-uall`) to see all changed/untracked files
- `git diff --stat` to see a summary of changes
- `git log --oneline -5` to see recent commit style
- `git branch --show-current` to confirm current branch

If there are no changes (no modified, deleted, or untracked files), tell the user "No changes to commit" and stop.

If already on a non-main branch, skip branch creation and use the current branch.

## Step 2: Create a new branch

Only if currently on `main`:
- Generate a descriptive branch name from the changes (e.g., `fix/typescript-build-errors`, `feat/add-search-api`, `chore/update-deps`)
- Use the pattern: `<type>/<short-description>` where type is `feat`, `fix`, `chore`, `refactor`, `docs`, or `test`
- Run: `git checkout -b <branch-name>`

## Step 3: Stage all changes

- Stage all relevant files. Prefer `git add <specific-files>` over `git add -A`.
- NEVER stage files that look like secrets (`.env`, `credentials.json`, `*.key`, `*.pem`). Warn the user if such files exist.
- Show what was staged.

## Step 4: Create the commit

- Analyze ALL staged changes (read diffs if needed) to write an accurate commit message.
- Follow the commit style from recent history (Step 1).
- The commit message should:
  - Summarize the "why" not just the "what"
  - Be concise (1-2 sentences)
  - Use imperative mood
- Always append the co-author trailer.
- Use a HEREDOC for the message:

```
git commit -m "$(cat <<'EOF'
<commit message>
EOF
)"
```

## Step 5: Push the branch

- Push with upstream tracking: `git push -u origin <branch-name>`

## Step 6: Merge decision

Check the user's argument: `$ARGUMENTS`

**If the argument contains "merge"** (case-insensitive):
1. Switch to main: `git checkout main`
2. Pull latest: `git pull origin main`
3. Merge the branch: `git merge <branch-name>`
4. Push main: `git push origin main`
5. Delete the remote branch: `git push origin --delete <branch-name>`
6. Delete the local branch: `git branch -d <branch-name>`
7. Report: "Merged `<branch-name>` into main and cleaned up."

**If no argument or argument does not contain "merge"**:
- Report: "Branch `<branch-name>` pushed to origin. To merge later, run `/branch-push merge` or create a PR."

## Rules

- NEVER force push (`--force`, `-f`)
- NEVER skip hooks (`--no-verify`)
- NEVER push to main directly (always go through a branch)
- If any step fails, stop and report the error clearly — do not retry destructively
- If a pre-commit hook fails, fix the issue, re-stage, and create a NEW commit (never amend)
