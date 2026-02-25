import pytest
from pathlib import Path
from kodadocs.models import (
    SessionConfig, AuthConfig, Framework, RunManifest,
    StepStatus, StepResult,
)

def test_session_config_defaults(tmp_path):
    config = SessionConfig(project_path=tmp_path)
    assert config.app_url == "http://localhost:3000"
    assert config.ai_model == "claude-sonnet-4-6"
    assert config.generation_model == "claude-haiku-4-5-20251001"
    assert config.skip_ai is False
    assert config.auth is None
    assert config.framework == "Unknown"  # use_enum_values stores as string
    assert config.brand_color == "#3e8fb0"

def test_session_config_explicit_app_url(tmp_path):
    config = SessionConfig(app_url="http://localhost:8080", project_path=tmp_path)
    assert config.app_url == "http://localhost:8080"

def test_session_config_with_auth(tmp_path):
    auth = AuthConfig(username="user", password="pass", auth_url="http://localhost/login")
    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        auth=auth
    )
    assert config.auth.username == "user"
    assert config.auth.password == "pass"

def test_framework_enum():
    assert Framework.NEXTJS.value == "Next.js"
    assert Framework.SVELTEKIT.value == "SvelteKit"
    assert Framework.RAILS.value == "Rails"
    assert Framework.LARAVEL.value == "Laravel"

def test_run_manifest_creation(tmp_path):
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="test_123", config=config)
    assert manifest.session_id == "test_123"
    assert manifest.discovered_routes == []
    assert manifest.articles == []
    assert manifest.config_hash is None

def test_run_manifest_serialization(tmp_path):
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(
        session_id="test_456",
        config=config,
        config_hash="abc123",
        discovered_routes=["/", "/about"],
        product_summary="Test product",
    )
    json_str = manifest.model_dump_json()
    restored = RunManifest.model_validate_json(json_str)
    assert restored.session_id == "test_456"
    assert restored.config_hash == "abc123"
    assert restored.discovered_routes == ["/", "/about"]
    assert restored.product_summary == "Test product"

def test_step_result_defaults():
    step = StepResult(name="TestStep")
    assert step.status == "pending"  # use_enum_values
    assert step.cost_estimate == 0.0
    assert step.error is None

def test_use_enum_values():
    """ConfigDict(use_enum_values=True) stores enum as its value string."""
    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=Path("/tmp/test"),
        framework=Framework.NEXTJS,
    )
    # With use_enum_values=True, framework is stored as the string value
    assert config.framework == "Next.js"


# ── New Framework enum values ──────────────────────────────────────────────


def test_framework_new_enum_values():
    """Verify the new Framework enum members added in B5 exist with correct values."""
    assert Framework.NUXT.value == "Nuxt"
    assert Framework.HONO.value == "Hono"
    assert Framework.REMIX.value == "Remix"
    assert Framework.ASTRO.value == "Astro"
    assert Framework.REACT_NATIVE.value == "React Native"
    assert Framework.CHROME_EXTENSION.value == "Chrome Extension"


# ── RunManifest new fields ─────────────────────────────────────────────────


def test_run_manifest_new_field_defaults(tmp_path):
    """New RunManifest fields default to empty collections or None."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="defaults", config=config)

    assert manifest.detected_services == []
    assert manifest.ui_components == []
    assert manifest.data_models == []
    assert manifest.route_metadata == {}
    assert manifest.deployment_platform is None


def test_run_manifest_serialization_new_fields(tmp_path):
    """Serialization roundtrip preserves new RunManifest fields."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(
        session_id="roundtrip",
        config=config,
        detected_services=["Stripe", "SendGrid"],
        ui_components=["Button", "Modal", "Sidebar"],
        data_models=["User", "Post", "Comment"],
        route_metadata={
            "/users": {"dynamic": False, "type": "page", "visibility": "public"},
            "/users/[id]": {"dynamic": True, "type": "page", "visibility": "private"},
        },
        deployment_platform="Vercel",
    )

    json_str = manifest.model_dump_json()
    restored = RunManifest.model_validate_json(json_str)

    assert restored.detected_services == ["Stripe", "SendGrid"]
    assert restored.ui_components == ["Button", "Modal", "Sidebar"]
    assert restored.data_models == ["User", "Post", "Comment"]
    assert restored.route_metadata["/users"]["type"] == "page"
    assert restored.route_metadata["/users/[id]"]["dynamic"] is True
    assert restored.deployment_platform == "Vercel"


# ── blur_pii and pii_regions fields ──────────────────────────────────────


def test_session_config_blur_pii_default(tmp_path):
    """SessionConfig.blur_pii should default to True."""
    config = SessionConfig(project_path=tmp_path)
    assert config.blur_pii is True


def test_run_manifest_pii_regions_default(tmp_path):
    """RunManifest.pii_regions should default to empty dict."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="pii_test", config=config)
    assert manifest.pii_regions == {}


# ── Deploy fields ─────────────────────────────────────────────────────


def test_run_manifest_deploy_url_default(tmp_path):
    """RunManifest.deploy_url should default to None."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="deploy_test", config=config)
    assert manifest.deploy_url is None


def test_run_manifest_deploy_status_default(tmp_path):
    """RunManifest.deploy_status should default to None."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="deploy_test", config=config)
    assert manifest.deploy_status is None


def test_run_manifest_deploy_fields_roundtrip(tmp_path):
    """Deploy fields survive serialization roundtrip."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(
        session_id="deploy_rt",
        config=config,
        deploy_url="https://mysite.pages.dev",
        deploy_status="success",
    )
    json_str = manifest.model_dump_json()
    restored = RunManifest.model_validate_json(json_str)
    assert restored.deploy_url == "https://mysite.pages.dev"
    assert restored.deploy_status == "success"


# ── Pro tier fields ────────────────────────────────────────────────────


def test_session_config_license_key_default(tmp_path):
    """SessionConfig.license_key should default to None."""
    config = SessionConfig(project_path=tmp_path)
    assert config.license_key is None


def test_session_config_site_slug_default(tmp_path):
    """SessionConfig.site_slug should default to None."""
    config = SessionConfig(project_path=tmp_path)
    assert config.site_slug is None


def test_session_config_license_key_explicit(tmp_path):
    """SessionConfig accepts an explicit license_key."""
    config = SessionConfig(project_path=tmp_path, license_key="kd_pro_abc12345")
    assert config.license_key == "kd_pro_abc12345"


def test_session_config_site_slug_explicit(tmp_path):
    """SessionConfig accepts an explicit site_slug."""
    config = SessionConfig(project_path=tmp_path, site_slug="myapp")
    assert config.site_slug == "myapp"


def test_run_manifest_site_slug_default(tmp_path):
    """RunManifest.site_slug should default to None."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(session_id="slug_test", config=config)
    assert manifest.site_slug is None


def test_run_manifest_site_slug_roundtrip(tmp_path):
    """site_slug survives serialization roundtrip."""
    config = SessionConfig(project_path=tmp_path)
    manifest = RunManifest(
        session_id="slug_rt",
        config=config,
        site_slug="myapp",
    )
    json_str = manifest.model_dump_json()
    restored = RunManifest.model_validate_json(json_str)
    assert restored.site_slug == "myapp"
