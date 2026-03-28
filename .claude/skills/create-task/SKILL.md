---
name: create-task
description: Create structured task files under .claude/tasks/. Use when the user asks to create a task, plan a task, write a task, break something into tasks, or describes work that should be tracked as a task file. Trigger phrases include "create a task", "make a task", "add a task", "plan out", "break this into tasks", "write up a task", "task this out".
---

# Task Creator

You are creating structured task files for DevPulse. Research the codebase for context and produce complete task files under `.claude/tasks/`.

## Process

1. **Research first** — scan existing tasks in `.claude/tasks/` (and subfolders) to understand numbering, naming, what's completed, and dependency chains. Read relevant spec docs (`DEVPULSE_SPEC.md`, `DEVPULSE_MANAGEMENT_FEATURES.md`) if the task relates to them. Read relevant existing code to understand what already exists.
2. **Pick the right folder**:
   - Core spec tasks (phases 1-3): `.claude/tasks/`
   - Management improvement tasks: `.claude/tasks/management-improvements/`
   - Other feature groups: `.claude/tasks/<group-name>/` (create if needed)
3. **Determine task ID and filename**:
   - Core: `NN-short-name.md` (next number in sequence)
   - Management: `MN-short-name.md` (next M-number)
   - Other groups: clear prefix + descriptive name
4. **Write the file** in this exact format:

```markdown
# Task [ID]: [Title]

## Phase
[Phase name and number]

## Status
pending

## Blocked By
- [task-filename-without-extension]
(or "None" if no dependencies)

## Blocks
- [task-filename-without-extension]
(or "None" if nothing depends on this)

## Description
[1-3 sentences on what this delivers and why]

## Deliverables

### [file/path or component name]
- Specific implementation details
- Endpoint signatures, schema fields, computation logic
- Reference spec sections where applicable
```

5. **Present summary** — task ID, title, location, dependencies, and key deliverables.

## Rules

- Status is always `pending` for new tasks
- Blocked By / Blocks reference task filenames without `.md`
- Deliverables grouped by file path, not abstract concepts
- Include enough detail to implement without re-reading the full spec
- One task = one completable scope. If too large, split into multiple linked tasks with correct dependency wiring
- After implementation, mark `## Status` as `completed`

## Splitting Heuristics

If the request is too large for one task:
- DB migration + model + service + API = single backend task per feature
- AI-powered features = separate from the data-gathering tasks they depend on
- If a task touches 6+ files across 3+ directories, consider splitting
- Create separate files with correct Blocked By / Blocks wiring between them
