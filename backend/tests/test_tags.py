"""Tests for Tag CRUD endpoints and auto-tagging."""

import pytest


class TestCreateTag:
    """Tests for POST /api/v1/tags."""

    def test_create_tag(self, client, auth_headers):
        """Create a new tag successfully."""
        response = client.post(
            "/api/v1/tags",
            json={"name": "my-project", "color": "#ff6600"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "my-project"
        assert data["color"] == "#ff6600"
        assert data["usage_count"] == 0
        assert "id" in data

    def test_create_tag_default_color(self, client, auth_headers):
        """Create a tag with default color."""
        response = client.post(
            "/api/v1/tags",
            json={"name": "default-color"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["color"] == "#6366f1"

    def test_create_duplicate_tag(self, client, auth_headers, test_tags):
        """Cannot create a tag with the same name."""
        response = client.post(
            "/api/v1/tags",
            json={"name": "backend"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_tag_invalid_color(self, client, auth_headers):
        """Invalid color format is rejected."""
        response = client.post(
            "/api/v1/tags",
            json={"name": "bad-color", "color": "not-a-color"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_requires_auth(self, client):
        """Tag creation requires authentication."""
        response = client.post("/api/v1/tags", json={"name": "test"})
        assert response.status_code == 401


class TestListTags:
    """Tests for GET /api/v1/tags."""

    def test_list_tags_empty(self, client, auth_headers):
        """Empty list when no tags exist."""
        response = client.get("/api/v1/tags", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["tags"] == []

    def test_list_tags(self, client, auth_headers, test_tags):
        """List all user's tags."""
        response = client.get("/api/v1/tags", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["tags"]) == 3
        names = [t["name"] for t in data["tags"]]
        assert "backend" in names
        assert "production" in names
        assert "feature-x" in names

    def test_list_tags_with_counts(self, client, auth_headers, test_tagged_logs, test_tags):
        """Tags include usage counts."""
        response = client.get("/api/v1/tags", headers=auth_headers)
        data = response.json()
        tag_map = {t["name"]: t["usage_count"] for t in data["tags"]}
        assert tag_map["backend"] >= 1
        assert tag_map["production"] >= 1

    def test_requires_auth(self, client):
        """Listing tags requires authentication."""
        response = client.get("/api/v1/tags")
        assert response.status_code == 401


class TestDeleteTag:
    """Tests for DELETE /api/v1/tags/{tag_id}."""

    def test_delete_tag(self, client, auth_headers, test_tags):
        """Delete a tag successfully."""
        tag_id = test_tags[0].id
        response = client.delete(f"/api/v1/tags/{tag_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify deleted
        response = client.get("/api/v1/tags", headers=auth_headers)
        names = [t["name"] for t in response.json()["tags"]]
        assert "backend" not in names

    def test_delete_nonexistent_tag(self, client, auth_headers):
        """Deleting a non-existent tag returns 404."""
        response = client.delete("/api/v1/tags/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404


class TestAttachTags:
    """Tests for POST /api/v1/logs/{log_id}/tags."""

    def test_attach_tags(self, client, auth_headers, test_usage_logs, test_tags):
        """Attach tags to a log entry."""
        log_id = test_usage_logs[2].id  # anthropic log
        tag_id = test_tags[2].id  # feature-x

        response = client.post(
            f"/api/v1/logs/{log_id}/tags",
            json={"tag_ids": [tag_id]},
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify via log detail
        response = client.get(f"/api/v1/logs/{log_id}", headers=auth_headers)
        assert "feature-x" in response.json()["tags"]

    def test_attach_to_nonexistent_log(self, client, auth_headers, test_tags):
        """Attaching to a non-existent log returns 404."""
        response = client.post(
            "/api/v1/logs/nonexistent/tags",
            json={"tag_ids": [test_tags[0].id]},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDetachTag:
    """Tests for DELETE /api/v1/logs/{log_id}/tags/{tag_id}."""

    def test_detach_tag(self, client, auth_headers, test_tagged_logs, test_tags):
        """Remove a tag from a log entry."""
        log_id = test_tagged_logs[0].id
        tag_id = test_tags[0].id  # backend

        response = client.delete(
            f"/api/v1/logs/{log_id}/tags/{tag_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify removed
        response = client.get(f"/api/v1/logs/{log_id}", headers=auth_headers)
        assert "backend" not in response.json()["tags"]
