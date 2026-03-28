---
description: Review frontend design for styleguide compliance — colors, typography, spacing, dark mode, brand
argument-hint: <file-or-directory-to-review>
model: opus
---

# Design System Compliance Review

You are reviewing frontend code for strict adherence to the DevPulse design system. This is a technical audit — flag every deviation, no matter how small.

## Setup

1. Read the file(s) or directory specified by the user: `$ARGUMENTS`
   - If a directory, scan all `.tsx`, `.ts`, and `.css` files within it
   - If no argument given, ask the user what to review

2. Read existing pages/components for reference patterns:
   - Check `frontend/src/pages/` for established page patterns
   - Check `frontend/src/components/` for reusable component patterns

## Review Checklist

Work through each category below. For every violation, cite the exact file, line, and the rule being broken.

### 1. Color Compliance

- [ ] **No hardcoded hex/rgb values** — all colors must use CSS custom properties or Tailwind tokens
- [ ] **Consistent color usage** — primary, secondary, accent colors used per their intended role
- [ ] **Semantic colors used correctly** — success, warning, error, info colors for status indicators only
- [ ] **Contrast ratios** — text on backgrounds meets WCAG AA (4.5:1 normal text, 3:1 large text)

### 2. Typography Compliance

- [ ] **Font family consistency** — heading fonts vs body fonts used correctly
- [ ] **Type scale adherence** — sizes follow established tokens (not arbitrary pixel values)
- [ ] **Weight rules** — font weights used intentionally for hierarchy
- [ ] **Minimum sizes** — nothing below 12px, interactive elements at least 14px

### 3. Dark Mode

- [ ] **All colors use tokens/variables** that invert properly (no hardcoded light-only values)
- [ ] **Surface colors invert** — backgrounds swap correctly for dark mode
- [ ] **Text colors invert** — readable in both modes

### 4. Spacing & Layout

- [ ] **Consistent spacing scale** — uses Tailwind's spacing system (4px increments), no arbitrary pixel values
- [ ] **Card/section padding** is consistent across the page
- [ ] **Gap consistency** — similar element groups use the same gap values
- [ ] **Responsive considerations** — no fixed widths that would break on smaller viewports

### 5. Component Patterns

- [ ] **No inline styles** that duplicate what Tailwind classes provide
- [ ] **CSS custom properties** preferred over Tailwind arbitrary values (e.g., `bg-[#134E4A]` is a violation)
- [ ] **Accessible primitives** — using proper semantic HTML and ARIA attributes

## Output Format

```
## Design System Review: [file/directory]

### Compliant
- [List what's done correctly]

### Violations Found
For each violation:
1. **[Category]** — `file:line` — [What's wrong] → [What it should be]

### Summary
- Total violations: X
- Critical (contrast/accessibility): X
- Minor (spacing/consistency): X
- Recommendations: [brief list]
```

Be thorough but fair. Distinguish between hard violations (wrong color, wrong font) and soft suggestions (could be slightly better spacing).
