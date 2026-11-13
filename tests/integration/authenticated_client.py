import uuid
from fastapi.testclient import TestClient as BaseTestClient
from apps.api.app.main import app


def _find_project_id(value):
    if isinstance(value, dict):
        for key in ("project_id", "id"):
            if value.get(key):
                return str(value[key])
        for child in value.values():
            found = _find_project_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_project_id(child)
            if found:
                return found
    return None


class TestClient(BaseTestClient):
    def __init__(self, *args, **kwargs):
        if args:
            super().__init__(*args, **kwargs)
        else:
            super().__init__(app, **kwargs)

        suffix = uuid.uuid4().hex[:12]
        email = f"datumor-test-{suffix}@example.com"
        password = f"Test-{uuid.uuid4().hex}-Aa1!"
        full_name = "DATUMOR Integration Test"

        registered = super().post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": full_name,
            },
        )
        if registered.status_code != 201:
            raise RuntimeError(
                f"Test customer registration failed: "
                f"{registered.status_code} {registered.text}"
            )

        login = super().post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if login.status_code != 200:
            raise RuntimeError(
                f"Test customer login failed: "
                f"{login.status_code} {login.text}"
            )

        token = login.json().get("access_token")
        if not token:
            raise RuntimeError("Login response did not contain access_token")

        self._auth_headers = {"Authorization": f"Bearer {token}"}

        project = super().post(
            "/api/v1/projects",
            headers=self._auth_headers,
            json={"name": f"Integration {suffix}"},
        )
        if project.status_code not in (200, 201):
            raise RuntimeError(
                f"Test project creation failed: "
                f"{project.status_code} {project.text}"
            )

        self._project_id = _find_project_id(project.json())
        if not self._project_id:
            raise RuntimeError(
                f"Project response has no project ID: {project.json()}"
            )

    def _auth_headers_for(self, supplied=None):
        return {**self._auth_headers, **(supplied or {})}

    def post(self, url, *args, **kwargs):
        kwargs["headers"] = self._auth_headers_for(kwargs.get("headers"))
        if url == "/api/v1/ingestion/files":
            data = dict(kwargs.get("data") or {})
            data["project_id"] = self._project_id
            kwargs["data"] = data
        return super().post(url, *args, **kwargs)

    def get(self, url, *args, **kwargs):
        kwargs["headers"] = self._auth_headers_for(kwargs.get("headers"))
        return super().get(url, *args, **kwargs)
