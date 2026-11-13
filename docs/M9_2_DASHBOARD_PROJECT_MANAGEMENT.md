# M9.2 — Dashboard and Project Management

## Database

Migration: `migrations/sql/004_create_projects.sql`

Tables:
- `projects`: customer-owned project records with active/archived lifecycle.
- `project_activity`: append-only activity records for project creation, updates, archiving, and restoration.

Projects reference `users.user_id`. Deleting a user cascades to their projects. Deleting a project cascades to its activity records. Activity actor references are set to NULL if the actor is deleted.

## Customer APIs

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `PATCH /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/archive`
- `POST /api/v1/projects/{project_id}/restore`
- `GET /api/v1/projects/{project_id}/activity`
- `GET /api/v1/dashboard`

List query parameters:
- `status`: active, archived, or all (default active)
- `limit`: 1–100 (default 50)
- `offset`: zero or greater

## Administrator API

- `GET /api/v1/admin/projects`
- Optional `owner_user_id`, `limit`, and `offset`.

Only admin and superadmin roles can use this endpoint.

## Ownership and security

Customer project reads and writes are scoped to the authenticated user's ID. Cross-customer access returns 404. Admin and superadmin users can inspect projects across customers.

Project creation always assigns the authenticated user as owner. The request cannot set `owner_user_id`.

Archiving is soft deletion. Archived projects remain available in history and can be restored. Archived projects cannot be edited until restored.

## Dashboard

The dashboard returns:
- Total projects.
- Active projects.
- Archived projects.
- Five recently updated visible projects.
- Ten most recent visible project activity records.

Customer dashboards are owner-scoped. Administrator dashboards include all projects.

## Scope boundary

This milestone does not attach existing ingestion sources, datasets, processing jobs, reports, or exports to projects. That integration is handled by subsequent processing and delivery milestones.
