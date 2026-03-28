# Slash Commands

All commands are invoked as `/command-name [arguments]` in Claude Code.

---

## Quick Reference

### Development

| Command | What it does | Example |
|---------|-------------|---------|
| `/task-planner` | Full guided development: research → plan → TDD → implement → review → document | `/task-planner add team comparison view` |
| `/fix-error` | Diagnose an error, find root cause, apply verified fix | `/fix-error paste the traceback here` |
| `/branch-push` | Create branch, commit, push — optionally merge to main | `/branch-push` or `/branch-push merge` |

### Code Quality & Review

| Command | What it does | Example |
|---------|-------------|---------|
| `/design-review` | Review frontend for design system compliance (colors, typography, spacing, dark mode) | `/design-review frontend/src/pages/` |
| `/ux-review` | Review UX: accessibility, interaction design, user flows, responsiveness | `/ux-review frontend/src/pages/Dashboard.tsx` |
| `/visual-audit` | Audit visual aesthetics: layout balance, hierarchy, polish | `/visual-audit frontend/src/components/` |
| `/review-plan-design` | Review a task plan's frontend spec before implementation | `/review-plan-design .claude/tasks/my-feature.md` |
| `/tech-debt` | Scan for outdated deps, security issues, code quality | `/tech-debt dependencies` |

---

## Command Details

### `/task-planner <feature description>`

Full guided development workflow with 8 phases:

| Phase | What happens |
|-------|-------------|
| 1. Discovery | Classify scope and affected areas |
| 2. Exploration | Launch code-explorer agents to understand existing patterns |
| 3. Questions | Resolve all ambiguities before designing |
| 4. Architecture | Design the approach with code-architect agents |
| 5. Specification | Define concrete technical requirements, test strategy |
| 6. Implementation | Build the feature following conventions |
| 7. Quality Review | Code review, design review |
| 8. Summary | Document what was built, update project docs |

### `/fix-error <error text>`

Paste an error message, stack trace, or describe a problem. The command will:
1. Parse the error to identify the failing component
2. Read the relevant source files
3. Diagnose the root cause
4. Apply a fix
5. Verify the fix works

### `/branch-push [merge]`

Creates a branch from current changes, commits, and pushes. If `merge` is passed, also merges into main.

```
/branch-push          # Create branch + push
/branch-push merge    # Create branch + push + merge to main
```

### `/design-review <path>`

Reviews frontend code against the design system. Checks colors, typography, spacing, dark mode support, and component patterns.

### `/ux-review <path>`

Reviews UX patterns: accessibility (WCAG), interaction design, user flows, responsive behavior, keyboard navigation, error states.

### `/visual-audit <path>`

Audits visual aesthetics: layout balance, visual hierarchy, polish level, consistency within and across pages.

### `/review-plan-design <plan path>`

Reviews a task plan's frontend specification before implementation. Catches design issues early — run this after `/task-planner` Phase 5 and before Phase 6.

### `/tech-debt [focus area]`

Scans the DevPulse codebase for tech debt: dependency health, security concerns, code quality, infrastructure gaps, and test coverage.

---

## Typical Workflows

### "I want to add a feature"
```
/task-planner <feature>        # Full guided development
```

### "I need to fix an error"
```
/fix-error <paste the error>   # Automatic diagnosis + fix
```

### "Is the frontend up to standard?"
```
/design-review <path>          # Design system compliance
/ux-review <path>              # Accessibility + interaction
/visual-audit <path>           # Aesthetics + polish
```

### "Health check"
```
/tech-debt                     # Scan for issues
```
