import json
from kodadocs.utils.framework import (
    heuristic_detect,
    detect_services,
    detect_ui_components,
    detect_deployment,
)
from kodadocs.models import Framework


def test_detect_nextjs(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"next": "14.0.0", "react": "18.0.0"}}'
    )
    assert heuristic_detect(tmp_path) == Framework.NEXTJS


def test_detect_react(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "18.0.0"}}')
    assert heuristic_detect(tmp_path) == Framework.REACT


def test_detect_vue(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"vue": "3.0.0"}}')
    assert heuristic_detect(tmp_path) == Framework.VUE


def test_detect_angular(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"@angular/core": "17.0.0"}}'
    )
    assert heuristic_detect(tmp_path) == Framework.ANGULAR


def test_detect_sveltekit(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"devDependencies": {"@sveltejs/kit": "2.0.0"}}'
    )
    assert heuristic_detect(tmp_path) == Framework.SVELTEKIT


def test_detect_express(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "4.0.0"}}')
    assert heuristic_detect(tmp_path) == Framework.EXPRESS


def test_detect_generic_javascript(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"lodash": "4.0.0"}}')
    assert heuristic_detect(tmp_path) == Framework.JAVASCRIPT


def test_detect_django_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["django>=4.0"]'
    )
    assert heuristic_detect(tmp_path) == Framework.DJANGO


def test_detect_fastapi_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi>=0.100"]'
    )
    assert heuristic_detect(tmp_path) == Framework.FASTAPI


def test_detect_django_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("django==4.2\ncelery==5.3")
    assert heuristic_detect(tmp_path) == Framework.DJANGO


def test_detect_fastapi_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.104\nuvicorn==0.24")
    assert heuristic_detect(tmp_path) == Framework.FASTAPI


def test_detect_generic_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["requests"]')
    assert heuristic_detect(tmp_path) == Framework.PYTHON


def test_detect_rails(tmp_path):
    (tmp_path / "Gemfile").write_text(
        "source 'https://rubygems.org'\ngem 'rails', '~> 7.0'"
    )
    assert heuristic_detect(tmp_path) == Framework.RAILS


def test_detect_laravel(tmp_path):
    (tmp_path / "composer.json").write_text(
        '{"require": {"laravel/framework": "^10.0"}}'
    )
    assert heuristic_detect(tmp_path) == Framework.LARAVEL


def test_detect_unknown(tmp_path):
    # Empty directory
    assert heuristic_detect(tmp_path) == Framework.UNKNOWN


def test_nextjs_takes_priority_over_react(tmp_path):
    """Next.js check comes before React check, so a project with both should detect as Next.js."""
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"next": "14.0.0", "react": "18.0.0"}}'
    )
    assert heuristic_detect(tmp_path) == Framework.NEXTJS


# ============================================================
# New Framework enum values in heuristic_detect
# ============================================================


class TestHeuristicDetectNewFrameworks:
    """Tests for newly added Framework enum values."""

    def test_detect_nuxt(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"nuxt": "3.9.0", "vue": "3.4.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.NUXT

    def test_detect_nuxt_devdependency(self, tmp_path):
        (tmp_path / "package.json").write_text('{"devDependencies": {"nuxt": "3.9.0"}}')
        assert heuristic_detect(tmp_path) == Framework.NUXT

    def test_detect_remix(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"@remix-run/react": "2.5.0", "react": "18.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.REMIX

    def test_detect_astro(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"astro": "4.1.0"}}')
        assert heuristic_detect(tmp_path) == Framework.ASTRO

    def test_detect_hono(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"hono": "3.12.0"}}')
        assert heuristic_detect(tmp_path) == Framework.HONO

    def test_detect_react_native_via_react_native(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react-native": "0.73.0", "react": "18.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.REACT_NATIVE

    def test_detect_react_native_via_expo(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"expo": "50.0.0", "react": "18.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.REACT_NATIVE

    def test_detect_chrome_extension(self, tmp_path):
        manifest_data = {
            "manifest_version": 3,
            "name": "My Extension",
            "version": "1.0",
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest_data))
        assert heuristic_detect(tmp_path) == Framework.CHROME_EXTENSION

    def test_manifest_json_without_manifest_version_is_not_extension(self, tmp_path):
        """A manifest.json that lacks manifest_version should not be detected as a Chrome Extension."""
        manifest_data = {"name": "something", "version": "1.0"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest_data))
        # No package.json or other files, so should fall through to UNKNOWN
        assert heuristic_detect(tmp_path) == Framework.UNKNOWN

    def test_malformed_manifest_json_ignored(self, tmp_path):
        """Invalid JSON in manifest.json should not crash and should not detect as extension."""
        (tmp_path / "manifest.json").write_text("{not valid json!!}")
        assert heuristic_detect(tmp_path) == Framework.UNKNOWN


# ============================================================
# Priority ordering tests
# ============================================================


class TestHeuristicDetectPriority:
    """Tests that framework priority ordering is correct."""

    def test_nuxt_takes_priority_over_vue(self, tmp_path):
        """Nuxt check comes before Vue check, so a project with both should detect as Nuxt."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"nuxt": "3.9.0", "vue": "3.4.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.NUXT

    def test_remix_takes_priority_over_react(self, tmp_path):
        """Remix includes react, but should detect as Remix, not React."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"@remix-run/react": "2.5.0", "react": "18.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.REMIX

    def test_react_native_takes_priority_over_react(self, tmp_path):
        """React Native projects include react, but should detect as React Native."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react-native": "0.73.0", "react": "18.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.REACT_NATIVE

    def test_expo_takes_priority_over_react(self, tmp_path):
        """Expo projects include react, but should detect as React Native."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"expo": "50.0.0", "react": "18.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.REACT_NATIVE

    def test_nextjs_over_everything_js(self, tmp_path):
        """Next.js should win even with many other dependencies present."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"next": "14.0.0", "react": "18.0.0", "express": "4.0.0"}}'
        )
        assert heuristic_detect(tmp_path) == Framework.NEXTJS

    def test_package_json_takes_priority_over_manifest_json(self, tmp_path):
        """A project with both package.json and manifest.json should detect from package.json first."""
        (tmp_path / "package.json").write_text('{"dependencies": {"react": "18.0.0"}}')
        manifest_data = {"manifest_version": 3, "name": "ext", "version": "1.0"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest_data))
        assert heuristic_detect(tmp_path) == Framework.REACT


# ============================================================
# detect_services tests
# ============================================================


class TestDetectServices:
    """Tests for the detect_services function."""

    def test_detect_supabase(self, tmp_path):
        pkg = {"dependencies": {"@supabase/supabase-js": "^2.39.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["supabase"]

    def test_detect_supabase_ssr(self, tmp_path):
        pkg = {"dependencies": {"@supabase/ssr": "^0.1.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["supabase"]

    def test_detect_clerk_and_stripe_sorted(self, tmp_path):
        pkg = {"dependencies": {"@clerk/nextjs": "^4.29.0", "stripe": "^14.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_services(tmp_path)
        assert result == ["clerk", "stripe"]

    def test_no_services_detected(self, tmp_path):
        pkg = {"dependencies": {"react": "18.0.0", "lodash": "4.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == []

    def test_no_package_json(self, tmp_path):
        assert detect_services(tmp_path) == []

    def test_multiple_services_combined(self, tmp_path):
        pkg = {
            "dependencies": {
                "@supabase/supabase-js": "^2.39.0",
                "@clerk/nextjs": "^4.29.0",
                "stripe": "^14.0.0",
                "@prisma/client": "^5.8.0",
                "resend": "^3.0.0",
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_services(tmp_path)
        assert result == ["clerk", "prisma", "resend", "stripe", "supabase"]

    def test_devdependencies_also_scanned(self, tmp_path):
        pkg = {"devDependencies": {"@prisma/client": "^5.8.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["prisma"]

    def test_dedup_same_service_multiple_packages(self, tmp_path):
        """Two different packages mapping to the same service should only appear once."""
        pkg = {
            "dependencies": {
                "@supabase/supabase-js": "^2.39.0",
                "@supabase/ssr": "^0.1.0",
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["supabase"]

    def test_firebase_and_firebase_admin_dedup(self, tmp_path):
        pkg = {
            "dependencies": {"firebase": "^10.0.0"},
            "devDependencies": {"firebase-admin": "^12.0.0"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["firebase"]

    def test_malformed_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text("{invalid json!!")
        assert detect_services(tmp_path) == []

    def test_package_json_without_dependencies_key(self, tmp_path):
        pkg = {"name": "my-app", "version": "1.0.0"}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == []

    def test_drizzle_and_nextauth(self, tmp_path):
        pkg = {"dependencies": {"drizzle-orm": "^0.29.0", "next-auth": "^4.24.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_services(tmp_path)
        assert result == ["drizzle", "nextauth"]

    def test_convex_detected(self, tmp_path):
        pkg = {"dependencies": {"convex": "^1.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["convex"]

    def test_auth_core_maps_to_nextauth(self, tmp_path):
        pkg = {"dependencies": {"@auth/core": "^0.25.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_services(tmp_path) == ["nextauth"]


# ============================================================
# detect_ui_components tests
# ============================================================


class TestDetectUIComponents:
    """Tests for the detect_ui_components function."""

    def test_shadcn_with_components_dir(self, tmp_path):
        """Project with components.json and src/components/ui/ with .tsx files."""
        (tmp_path / "components.json").write_text('{"style": "default"}')
        ui_dir = tmp_path / "src" / "components" / "ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "button.tsx").write_text("export function Button() {}")
        (ui_dir / "card.tsx").write_text("export function Card() {}")
        (ui_dir / "dialog.tsx").write_text("export function Dialog() {}")

        result = detect_ui_components(tmp_path)
        assert result == ["button", "card", "dialog"]

    def test_shadcn_marker_when_no_ui_dir(self, tmp_path):
        """Project with components.json but no ui directory should return marker."""
        (tmp_path / "components.json").write_text('{"style": "default"}')

        result = detect_ui_components(tmp_path)
        assert result == ["__shadcn_marker__"]

    def test_no_shadcn_at_all(self, tmp_path):
        """Project with no components.json and no ui dir returns empty list."""
        result = detect_ui_components(tmp_path)
        assert result == []

    def test_ui_dir_without_components_json(self, tmp_path):
        """UI directory exists but no components.json — still detects component files."""
        ui_dir = tmp_path / "src" / "components" / "ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "button.tsx").write_text("export function Button() {}")

        result = detect_ui_components(tmp_path)
        assert result == ["button"]

    def test_alternative_components_ui_path(self, tmp_path):
        """Also checks components/ui (without src prefix)."""
        (tmp_path / "components.json").write_text('{"style": "new-york"}')
        ui_dir = tmp_path / "components" / "ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "input.tsx").write_text("export function Input() {}")
        (ui_dir / "label.tsx").write_text("export function Label() {}")

        result = detect_ui_components(tmp_path)
        assert result == ["input", "label"]

    def test_ignores_non_component_files(self, tmp_path):
        """Non-.tsx/.jsx/.ts/.js files in ui/ should be ignored."""
        ui_dir = tmp_path / "src" / "components" / "ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "button.tsx").write_text("export function Button() {}")
        (ui_dir / "README.md").write_text("# UI Components")
        (ui_dir / "styles.css").write_text(".btn { color: red; }")

        result = detect_ui_components(tmp_path)
        assert result == ["button"]

    def test_jsx_and_js_files_also_detected(self, tmp_path):
        """Component files with .jsx, .ts, and .js extensions are detected."""
        ui_dir = tmp_path / "src" / "components" / "ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "alert.jsx").write_text("export function Alert() {}")
        (ui_dir / "badge.ts").write_text("export function Badge() {}")
        (ui_dir / "tooltip.js").write_text("export function Tooltip() {}")

        result = detect_ui_components(tmp_path)
        assert result == ["alert", "badge", "tooltip"]

    def test_components_sorted_alphabetically(self, tmp_path):
        """Components should be returned in sorted order (from sorted iterdir)."""
        ui_dir = tmp_path / "src" / "components" / "ui"
        ui_dir.mkdir(parents=True)
        (ui_dir / "textarea.tsx").write_text("")
        (ui_dir / "avatar.tsx").write_text("")
        (ui_dir / "popover.tsx").write_text("")

        result = detect_ui_components(tmp_path)
        assert result == ["avatar", "popover", "textarea"]

    def test_both_ui_dirs_combined(self, tmp_path):
        """When both src/components/ui and components/ui exist, results combine."""
        ui_dir_src = tmp_path / "src" / "components" / "ui"
        ui_dir_src.mkdir(parents=True)
        (ui_dir_src / "button.tsx").write_text("")

        ui_dir_root = tmp_path / "components" / "ui"
        ui_dir_root.mkdir(parents=True)
        (ui_dir_root / "card.tsx").write_text("")

        result = detect_ui_components(tmp_path)
        assert result == ["button", "card"]


# ============================================================
# detect_deployment tests
# ============================================================


class TestDetectDeployment:
    """Tests for the detect_deployment function."""

    def test_vercel_json(self, tmp_path):
        (tmp_path / "vercel.json").write_text('{"version": 2}')
        assert detect_deployment(tmp_path) == "vercel"

    def test_vercel_directory(self, tmp_path):
        (tmp_path / ".vercel").mkdir()
        assert detect_deployment(tmp_path) == "vercel"

    def test_netlify_toml(self, tmp_path):
        (tmp_path / "netlify.toml").write_text('[build]\ncommand = "npm run build"')
        assert detect_deployment(tmp_path) == "netlify"

    def test_fly_toml(self, tmp_path):
        (tmp_path / "fly.toml").write_text('app = "my-app"')
        assert detect_deployment(tmp_path) == "fly"

    def test_railway_json(self, tmp_path):
        (tmp_path / "railway.json").write_text("{}")
        assert detect_deployment(tmp_path) == "railway"

    def test_railway_toml(self, tmp_path):
        (tmp_path / "railway.toml").write_text("")
        assert detect_deployment(tmp_path) == "railway"

    def test_render_yaml(self, tmp_path):
        (tmp_path / "render.yaml").write_text("services:\n  - type: web")
        assert detect_deployment(tmp_path) == "render"

    def test_dockerfile(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM node:20-alpine")
        assert detect_deployment(tmp_path) == "docker"

    def test_no_deployment_files(self, tmp_path):
        assert detect_deployment(tmp_path) is None

    def test_vercel_takes_priority_over_docker(self, tmp_path):
        """Vercel is checked first, so if both exist, vercel wins."""
        (tmp_path / "vercel.json").write_text('{"version": 2}')
        (tmp_path / "Dockerfile").write_text("FROM node:20-alpine")
        assert detect_deployment(tmp_path) == "vercel"

    def test_netlify_takes_priority_over_docker(self, tmp_path):
        (tmp_path / "netlify.toml").write_text('[build]\ncommand = "npm run build"')
        (tmp_path / "Dockerfile").write_text("FROM node:20-alpine")
        assert detect_deployment(tmp_path) == "netlify"

    def test_empty_directory(self, tmp_path):
        """An empty directory should return None."""
        assert detect_deployment(tmp_path) is None
