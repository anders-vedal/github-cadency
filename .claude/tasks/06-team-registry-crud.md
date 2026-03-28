# Task 06: Team Registry CRUD API

## Phase
Phase 2 — Backend APIs

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 03-pydantic-schemas

## Blocks
- 11-frontend-dashboard-team

## Description
Implement developer CRUD endpoints per spec Section 5.1, plus bearer token auth middleware per Section 5.6.

## Deliverables

### Auth middleware
- Bearer token validation against DEVPULSE_ADMIN_TOKEN env var
- FastAPI dependency that extracts and validates `Authorization: Bearer <token>`
- Applied to all endpoints except `/api/webhooks/github` and `/api/health`
- Return 401 with clear error on missing/invalid token

### backend/app/api/developers.py

**GET /api/developers**
- Query params: team (optional), is_active (optional, default true)
- Returns list of developers
- Ordered by display_name

**POST /api/developers**
- Request body: DeveloperCreate schema
- Validate github_username uniqueness (return 409 on conflict)
- Set created_at/updated_at
- Return created developer with 201 status

**GET /api/developers/{id}**
- Return single developer or 404

**PATCH /api/developers/{id}**
- Request body: DeveloperUpdate schema (partial update)
- Only update provided fields
- Update updated_at timestamp
- Return updated developer or 404

**DELETE /api/developers/{id}**
- Soft-delete: set is_active=false
- Return 204 on success, 404 if not found
