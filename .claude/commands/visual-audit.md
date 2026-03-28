---
description: Audit visual aesthetics — layout balance, hierarchy, polish, and overall design quality
argument-hint: <file-or-directory-to-review>
model: opus
---

# Visual Aesthetics Audit

You are reviewing frontend code as a visual designer. This goes beyond styleguide compliance — you're evaluating whether the design *looks good*, feels polished, and creates a cohesive visual experience.

## Setup

1. Read the target file(s): `$ARGUMENTS`
   - If no argument given, ask the user what to review

2. Read 2-3 existing pages for comparison:
   - `frontend/src/pages/` — check for established visual patterns
   - The component being reviewed's parent/sibling components

## Visual Assessment Criteria

### 1. Layout & Composition

- **Balance** — Is visual weight distributed well?
- **Alignment** — Do elements snap to an implicit grid?
- **Proportions** — Are sections sized proportionally to their importance?
- **Rhythm** — Is there a consistent vertical rhythm? Does spacing repeat predictably?
- **Density** — Is the information density appropriate?

### 2. Visual Hierarchy

- **Primary focal point** — Is there one clear thing the eye goes to first?
- **Size contrast** — Do headings, body, and captions create clear levels?
- **Weight contrast** — Is bold/medium/regular used to create emphasis intentionally?
- **Color as hierarchy** — Does color draw attention to the right things?
- **Depth cues** — Do shadows, borders, or backgrounds create appropriate layering?

### 3. Color Harmony

- **Palette cohesion** — Does the page feel like one unified palette?
- **Accent restraint** — Is the accent color reserved for key moments?
- **Neutral warmth** — Do neutrals feel appropriate for a data dashboard?
- **Semantic color clarity** — Are status indicators immediately recognizable?

### 4. Typography Quality

- **Hierarchy clarity** — Can you tell headings from body from captions at a glance?
- **Readability** — Line lengths comfortable (45-75 chars)? Adequate line height?
- **Number alignment** — In tables/lists with numbers, do they align properly?

### 5. Micro-Details & Polish

- **Border radius consistency** — All cards/buttons/inputs use the same radius family
- **Shadow consistency** — Shadow depth matches element elevation
- **Icon sizing** — Icons optically balanced with adjacent text
- **Dividers** — Lines/borders are subtle, not heavy
- **Transitions** — Hover/focus/active states have smooth transitions (150-200ms)
- **Cursor styles** — Interactive elements show pointer cursor

## Output Format

```
## Visual Audit: [file/feature]

### Overall Impression
[2-3 sentences on how this design feels]

### What Looks Great
- [Specific visual wins]

### Visual Issues
For each:
1. **[Category]** — `file:line` — [What looks off] → [Specific fix with values]
   Impact: High / Medium / Low

### Design Recommendations
[Concrete suggestions with specific CSS/Tailwind values]

### Consistency Score
- Layout & Composition: X/5
- Visual Hierarchy: X/5
- Color Harmony: X/5
- Typography: X/5
- Polish & Detail: X/5
- **Overall: X/5**
```

Be constructive and specific. Think in concrete CSS/Tailwind values.
