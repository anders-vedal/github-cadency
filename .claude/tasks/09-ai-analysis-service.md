# Task 09: AI Analysis Service & Endpoints

## Phase
Phase 2 — Backend APIs

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 03-pydantic-schemas

## Blocks
- 12-frontend-remaining-pages

## Description
Implement AI analysis per spec Sections 5.5 and 6.

## Deliverables

### backend/app/services/ai_analysis.py

**Data Preparation (Section 6.3)**
1. Query relevant text data from DB filtered by scope and date range:
   - For developer scope: their PR bodies, review bodies, issue comments
   - For team scope: all team members' interactions
   - For repo scope: all activity in the repo
2. Truncate individual items to 500 chars
3. Limit to 50 most recent items per category
4. Assemble structured prompt with clear sections
5. Record input_summary for auditing

**Analysis Types (Section 6.2)**

*communication* (scope: developer)
- Analyze PR descriptions, review comments, issue comments
- Score: clarity, constructiveness, responsiveness, tone (1-10 each)
- Output: scores + qualitative observations + recommendations

*conflict* (scope: team)
- Focus on CHANGES_REQUESTED reviews + regular comments
- Identify friction patterns between reviewer-author pairs
- Assess constructiveness of feedback
- Output: conflict score + friction pairs + recurring issues + recommendations

*sentiment* (scope: developer | team | repo)
- Lighter analysis of overall tone and morale
- Output: sentiment score + trend + notable patterns

**Claude API Integration**
- Use claude-sonnet-4-20250514 model
- System prompt instructs JSON structured output with defined schema
- Parse response with fallback (strip markdown fences, handle partial JSON)
- Track token usage per analysis

**Storage**
- Store full result in ai_analyses table
- Include: analysis_type, scope, date range, input_summary, structured result, raw_response, model, tokens, triggered_by

### backend/app/api/ai_analysis.py

**POST /api/ai/analyze**
- Request body: AIAnalyzeRequest (analysis_type, scope_type, scope_id, date_from, date_to)
- Validate scope exists (developer/team/repo)
- Run analysis (can be long-running — consider background task)
- Return AIAnalysisResponse with 201

**GET /api/ai/history**
- List past analyses, ordered by created_at desc
- Optional filters: analysis_type, scope_type

**GET /api/ai/history/{id}**
- Return specific analysis result or 404
