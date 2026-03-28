---
description: Review a task plan's frontend spec for styleguide compliance, UX quality, visual coherence, and completeness before implementation
argument-hint: <path-to-task-plan.md>
model: opus
---

# Pre-Implementation Design Plan Review

You are reviewing a **task plan** (not code) to catch design issues before a single line is written. Your job is to ensure every frontend task in the plan will produce UI that follows the design system, has great UX, looks polished, and integrates with the existing app.

## Setup

1. Read the task plan: `$ARGUMENTS`
   - If no argument, ask which plan to review

2. Read existing components/pages that the plan references or extends

3. If this plan depends on earlier phases, read those too

## Review: Design System Compliance

For every frontend task in the plan, check:

### Colors & Theming
- Does the plan specify which colors to use? If not, **flag it**
- Does the plan account for dark mode?
- Are semantic colors used correctly?

### Typography
- Does the plan describe text sizing that fits the type scale?
- Are heading levels implied correctly?

### Component Patterns
- Does the plan reuse existing components where possible?
- Are new components actually needed, or could existing ones be extended?

## Review: UX & Interaction Quality

### States & Feedback
- **Loading states** — Does each async operation describe what the user sees while waiting?
- **Empty states** — What happens with 0 items?
- **Error states** — What happens when an API call fails?
- **Success feedback** — How does the user know an action worked?

### Accessibility
- Are keyboard interactions described?
- Are icon-only buttons getting aria-labels?
- Is color the sole indicator of anything?

### User Flow
- Is the happy path obvious?
- Are edge cases covered? (long text, 0 items, 1000 items, missing data)
- Any dead ends where the user gets stuck?

## Review: Visual Design & Aesthetics

### Layout
- Will new UI elements fit the existing page's visual rhythm?
- Is spacing described or left ambiguous?

### Hierarchy
- Is the primary focal point clear?
- Are secondary elements visually subordinate?

### Consistency with Existing App
- Do new components follow existing visual patterns?
- Do action menus, dialogs, and forms match established style?

## Review: Completeness

Flag any frontend task missing:
- [ ] Dark mode behavior
- [ ] Loading/empty/error states
- [ ] Keyboard interaction description
- [ ] Mobile/responsive behavior
- [ ] Which existing components to reuse vs. create new
- [ ] How the new UI integrates visually with existing UI
- [ ] Test coverage for described behavior

## Output Format

```
## Plan Design Review: [plan name]

### Frontend Tasks Found
[List each frontend task with one-line summary]

### Well-Specified
- [Tasks/details that are clear and will produce good UI]

### Design System Issues
1. **Task X.Y** — [Issue] → [How to fix the spec]

### UX Gaps
1. **Task X.Y** — [Missing interaction/state] → [What to add]

### Visual Concerns
1. **Task X.Y** — [Potential problem] → [Recommendation]

### Missing Specifications
- Task X.Y: [missing: dark mode, empty state, ...]

### Readiness Score
- Design system compliance: Ready / Needs work / Not addressed
- UX completeness: Ready / Needs work / Not addressed
- Visual integration: Ready / Needs work / Not addressed
- **Overall: Ready for implementation / Needs revision / Significant gaps**
```

Be thorough but constructive. Distinguish "must fix before implementing" from "can figure out during implementation."
