---
description: Review UX patterns — accessibility, interaction design, user flows, responsiveness, and usability
argument-hint: <file-or-directory-or-feature-to-review>
model: opus
---

# UX & Interaction Design Review

You are reviewing frontend code for usability, accessibility, and interaction quality. Focus on how the UI *feels* to use — not just whether it follows the styleguide (that's `/design-review`).

## Setup

1. Read the file(s) or feature specified by the user: `$ARGUMENTS`
   - If a directory, scan all `.tsx` files
   - If no argument given, ask the user what to review

2. Read existing related components to understand established interaction patterns:
   - Check sibling pages/components for consistency
   - Look at `frontend/src/pages/` for reference implementations

## Review Checklist

### 1. Accessibility (WCAG 2.1 AA)

- [ ] **Keyboard navigation** — all interactive elements reachable via Tab, logical tab order, visible focus indicators
- [ ] **Focus management** — modals trap focus, return focus on close
- [ ] **ARIA labels** — icons without text have `aria-label`, form inputs have associated labels
- [ ] **Heading hierarchy** — one h1 per page, headings don't skip levels
- [ ] **Color not sole indicator** — errors/status use icons or text in addition to color
- [ ] **Touch targets** — interactive elements at least 44x44px on touch, 24x24px on desktop
- [ ] **Reduced motion** — animations respect `prefers-reduced-motion`

### 2. Interaction Patterns

- [ ] **Loading states** — async operations show loading indicators
- [ ] **Empty states** — lists show helpful empty states with guidance
- [ ] **Error states** — API failures show user-friendly messages with retry options
- [ ] **Feedback on actions** — clicks produce immediate visual response
- [ ] **Undo/cancel** — destructive actions have confirmation

### 3. Navigation & Information Architecture

- [ ] **Context** — user always knows where they are
- [ ] **Back navigation** — browser back button works correctly with React Router
- [ ] **Deep linking** — page state reflected in URL where appropriate
- [ ] **Consistent placement** — primary actions in predictable locations

### 4. Visual Hierarchy & Readability

- [ ] **Scanning pattern** — most important information visible without scrolling
- [ ] **Grouping** — related items visually grouped
- [ ] **Text density** — appropriate line length (45-75 characters), adequate line height
- [ ] **Whitespace** — breathing room between sections

### 5. Responsive & Adaptive Design

- [ ] **Breakpoint behavior** — layout adapts at standard breakpoints
- [ ] **No horizontal scroll** — content fits viewport width
- [ ] **Content priority on small screens** — most important content first

### 6. Consistency with Existing App

- [ ] **Pattern matching** — new UI follows same patterns as existing pages
- [ ] **Shared components reused** — uses existing components rather than reinventing
- [ ] **State management** — follows established patterns
- [ ] **API client usage** — follows existing data fetching patterns

## Output Format

```
## UX Review: [file/feature]

### User Flow Summary
[Brief description of what this UI does and the primary user journey]

### Strengths
- [What works well]

### Issues Found
For each issue:
1. **[Category]** — `file:line` — [Problem] → [Recommended fix]
   Severity: Critical / Major / Minor

### Enhancement Suggestions
- [Optional improvements]

### Summary
- Critical issues: X
- Major issues: X
- Minor issues: X
```

Focus on real user impact. A missing loading state is more important than a slightly inconsistent margin.
