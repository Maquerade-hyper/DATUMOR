# M9.1 — Authentication and Authorization

## Step 1: User identity and database foundation

The identity model is stored in the `users` table.

Fields:
- `user_id`: UUID primary key.
- `email`: original email address.
- `email_normalized`: normalized unique email address.
- `password_hash`: password hash only; plaintext passwords are never stored.
- `full_name`: optional display name.
- `role`: customer, admin, or superadmin.
- `is_active`: account activation state.
- `is_email_verified`: email verification state.
- `created_at`, `updated_at`: database-managed timestamps.

Database constraints enforce role values, email length, and normalized email formatting.

Migration:
`migrations/sql/002_create_users.sql`

Model:
`apps/api/app/auth/user_model.py`

The migration is intentionally separate from application startup. Production schema changes must be applied through versioned migrations, not implicit `create_all()` calls.
## Authentication and authorization API

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{user_id}/role`

Access tokens are short-lived JWTs. Refresh tokens are random opaque values;
only SHA-256 hashes are persisted. Refresh rotates the token and reuse of a
revoked token revokes the token family.

Access-token authentication checks the associated database session on every
request. Revoked sessions therefore cannot continue using their access tokens.

Roles:
- customer
- admin
- superadmin

Use `ensure_resource_owner(owner_user_id, user)` in project, dataset, job,
report, and export endpoints before returning or mutating customer-owned data.
The helper returns 404 for cross-customer access to avoid disclosing resource
existence.

### Initial superadmin

Set these variables temporarily in the environment:
- DATUMOR_BOOTSTRAP_ADMIN_EMAIL
- DATUMOR_BOOTSTRAP_ADMIN_PASSWORD (minimum 16 characters)
- DATUMOR_BOOTSTRAP_ADMIN_NAME (optional)

Then run:

`python -m apps.api.app.auth.bootstrap_admin`

The bootstrap command refuses to create another superadmin once one exists.
Remove the temporary bootstrap password from the environment after use.

### Operational security notes

- Keep DATUMOR_AUTH_SECRET_KEY private and stable across API instances.
- Use HTTPS in production.
- Apply rate limiting at the reverse proxy/API gateway for login and refresh.
- Email verification is represented in the user model but requires a configured
  email delivery provider and verification workflow before it can be enforced.
- Password reset and MFA are not included in this milestone implementation.
- Refresh tokens are returned in the JSON response; browser clients should
  keep them in secure, HttpOnly, Secure, SameSite cookies via a deployment
  adapter rather than localStorage.
