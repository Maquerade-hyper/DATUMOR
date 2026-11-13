# DATUMOR API Reference

Generated from the running application's OpenAPI schema.

- OpenAPI version: 3.1.0
- API title: DATUMOR API
- API version: 0.1.0
- Local schema endpoint: `/openapi.json`

## Authentication

Use the authentication scheme defined by the API. Protected endpoints require valid credentials. Consult the login and registration endpoints below for the current request schemas.

## Endpoints

| Method | Path | Summary | Tags |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Register | Authentication |
| `POST` | `/api/v1/auth/login` | Login | Authentication |
| `POST` | `/api/v1/auth/refresh` | Refresh | Authentication |
| `POST` | `/api/v1/auth/logout` | Logout | Authentication |
| `GET` | `/api/v1/auth/me` | Me | Authentication |
| `POST` | `/api/v1/auth/change-password` | Change Password | Authentication |
| `GET` | `/api/v1/admin/users` | List Users | Administration |
| `PATCH` | `/api/v1/admin/users/{user_id}/role` | Change Role | Administration |
| `GET` | `/api/v1/projects` | List All | Projects and Dashboard |
| `POST` | `/api/v1/projects` | Create | Projects and Dashboard |
| `GET` | `/api/v1/projects/{project_id}` | Retrieve | Projects and Dashboard |
| `PATCH` | `/api/v1/projects/{project_id}` | Update | Projects and Dashboard |
| `POST` | `/api/v1/projects/{project_id}/archive` | Archive | Projects and Dashboard |
| `POST` | `/api/v1/projects/{project_id}/restore` | Restore | Projects and Dashboard |
| `GET` | `/api/v1/projects/{project_id}/activity` | Activity | Projects and Dashboard |
| `GET` | `/api/v1/dashboard` | Dashboard | Projects and Dashboard |
| `GET` | `/api/v1/admin/projects` | List All Customer Projects | Project Administration |
| `GET` | `/api/v1/jobs` | List Jobs | processing |
| `POST` | `/api/v1/jobs` | Create Job | processing |
| `GET` | `/api/v1/jobs/{job_id}` | Get Job | processing |
| `GET` | `/api/v1/jobs/{job_id}/events` | Job Events | processing |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Cancel Job | processing |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Retry Job | processing |
| `GET` | `/api/v1/admin/jobs` | Admin List Jobs | processing-admin |
| `GET` | `/api/v1/usage/me` | My Usage | usage |
| `GET` | `/api/v1/usage/policy` | Public Policy | usage |
| `GET` | `/api/v1/admin/usage/policy` | Read Policy | usage-admin |
| `PUT` | `/api/v1/admin/usage/policy` | Update Policy | usage-admin |
| `GET` | `/api/v1/admin/usage/resources` | System Resources | usage-admin |
| `GET` | `/health` | Health | — |
| `POST` | `/api/v1/ingestion/files` | Upload File | — |
| `POST` | `/api/v1/ingestion/github` | Ingest Github | — |
| `GET` | `/api/v1/sources` | List Sources | — |
| `GET` | `/api/v1/sources/{source_id}` | Get Source | — |
| `GET` | `/api/v1/reports` | M94 List Reports | — |
| `GET` | `/api/v1/reports/{job_id}` | M94 Get Report | — |
| `GET` | `/api/v1/reports/{job_id}/download/{format}` | M94 Download Report | — |
| `GET` | `/api/v1/reports/{job_id}/artifacts` | M94 List Artifacts | — |
| `GET` | `/api/v1/reports/{job_id}/artifacts/download` | M94 Download Artifact | — |
| `GET` | `/api/v1/reports/{job_id}/versions` | M94 List Versions | — |
| `POST` | `/api/v1/reports/{job_id}/versions` | M94 Create Version | — |
| `GET` | `/api/v1/reports/{job_id}/versions/{version}/manifest` | M94 Get Version Manifest | — |
| `GET` | `/api/v1/reports/{job_id}/versions/compare` | M94 Compare Versions | — |

## Request and response schemas

The authoritative request, response, validation, and security schemas are available in the generated OpenAPI document at `/openapi.json`. Use Swagger UI at `/docs` when enabled by the application.