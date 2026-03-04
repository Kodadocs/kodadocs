from pathlib import Path
from typing import List, Dict, Optional
import json
import os
import anthropic
from ..models import Framework


# --- Service / BaaS Detection (A1) ---

SERVICE_PACKAGE_MAP = {
    "@supabase/supabase-js": "supabase",
    "@supabase/ssr": "supabase",
    "@clerk/nextjs": "clerk",
    "@clerk/clerk-react": "clerk",
    "stripe": "stripe",
    "@stripe/stripe-js": "stripe",
    "firebase": "firebase",
    "firebase-admin": "firebase",
    "@prisma/client": "prisma",
    "drizzle-orm": "drizzle",
    "next-auth": "nextauth",
    "@auth/core": "nextauth",
    "resend": "resend",
    "convex": "convex",
    "@upstash/redis": "upstash",
    "@upstash/ratelimit": "upstash",
    "@neondatabase/serverless": "neon",
    "@sanity/client": "sanity",
    "next-sanity": "sanity",
    "better-auth": "betterauth",
    "@trpc/client": "trpc",
    "@trpc/server": "trpc",
    "@sentry/nextjs": "sentry",
    "@sentry/node": "sentry",
    "@sentry/react": "sentry",
    "posthog-js": "posthog",
    "@planetscale/database": "planetscale",
    "payload": "payload",
    "uploadthing": "uploadthing",
    "@aws-amplify/core": "amplify",
    "aws-amplify": "amplify",
}


def detect_services(path: Path) -> List[str]:
    """Scan package.json for known BaaS/service dependencies."""
    package_json = path / "package.json"
    if not package_json.exists():
        return []

    try:
        data = json.loads(package_json.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    all_deps: Dict[str, str] = {}
    for key in ("dependencies", "devDependencies"):
        all_deps.update(data.get(key, {}))

    detected = set()
    for pkg, service in SERVICE_PACKAGE_MAP.items():
        if pkg in all_deps:
            detected.add(service)

    return sorted(detected)


# --- shadcn/ui Component Inventory (A2) ---


def detect_ui_components(path: Path) -> List[str]:
    """Detect shadcn/ui components by checking components.json and scanning ui/ dirs."""
    # Check for shadcn/ui marker file
    components_json = path / "components.json"
    has_shadcn = components_json.exists()

    # Scan common component directories
    ui_dirs = [
        path / "src" / "components" / "ui",
        path / "components" / "ui",
    ]

    components: List[str] = []
    for ui_dir in ui_dirs:
        if ui_dir.is_dir():
            for f in sorted(ui_dir.iterdir()):
                if f.suffix in (".tsx", ".jsx", ".ts", ".js"):
                    components.append(f.stem)

    if has_shadcn and not components:
        # components.json exists but no ui dir found yet — still signal shadcn presence
        components.append("__shadcn_marker__")

    return components


# --- Deployment Platform Detection (A5) ---


def detect_deployment(path: Path) -> Optional[str]:
    """Detect deployment platform from config files."""
    if (path / "vercel.json").exists() or (path / ".vercel").is_dir():
        return "vercel"
    if (path / "netlify.toml").exists():
        return "netlify"
    if (path / "fly.toml").exists():
        return "fly"
    if (path / "railway.json").exists() or (path / "railway.toml").exists():
        return "railway"
    if (path / "render.yaml").exists():
        return "render"
    if (path / "wrangler.toml").exists() or (path / "wrangler.json").exists():
        return "cloudflare"
    if (path / "sst.config.ts").exists() or (path / "sst.config.mjs").exists():
        return "sst"
    if (path / "Dockerfile").exists():
        return "docker"
    return None


# --- Framework Detection (expanded A3) ---


def heuristic_detect(path: Path) -> Framework:
    package_json = path / "package.json"
    if package_json.exists():
        with open(package_json, "r") as f:
            content = f.read()
            # Next.js must come before React (Next projects also have react)
            if '"next"' in content:
                return Framework.NEXTJS
            # Nuxt must come before Vue (Nuxt projects also have vue)
            if '"nuxt"' in content:
                return Framework.NUXT
            if '"@remix-run/react"' in content:
                return Framework.REMIX
            if '"astro"' in content:
                return Framework.ASTRO
            if '"hono"' in content:
                return Framework.HONO
            if '"solid-js"' in content:
                return Framework.SOLID
            if '"react-native"' in content or '"expo"' in content:
                return Framework.REACT_NATIVE
            if '"react"' in content:
                return Framework.REACT
            if '"vue"' in content:
                return Framework.VUE
            if '"@angular/core"' in content:
                return Framework.ANGULAR
            if '"@sveltejs/kit"' in content:
                return Framework.SVELTEKIT
            if '"express"' in content:
                return Framework.EXPRESS
        return Framework.JAVASCRIPT

    pyproject_toml = path / "pyproject.toml"
    if pyproject_toml.exists():
        with open(pyproject_toml, "r") as f:
            content = f.read()
            if "fastapi" in content:
                return Framework.FASTAPI
            if "django" in content:
                return Framework.DJANGO
        return Framework.PYTHON

    requirements_txt = path / "requirements.txt"
    if requirements_txt.exists():
        with open(requirements_txt, "r") as f:
            content = f.read()
            if "fastapi" in content:
                return Framework.FASTAPI
            if "django" in content:
                return Framework.DJANGO
        return Framework.PYTHON

    # Check for Ruby (Rails)
    gemfile = path / "Gemfile"
    if gemfile.exists():
        with open(gemfile, "r") as f:
            content = f.read()
            if "rails" in content.lower():
                return Framework.RAILS

    # Check for PHP (Laravel)
    composer_json = path / "composer.json"
    if composer_json.exists():
        with open(composer_json, "r") as f:
            content = f.read()
            if '"laravel/framework"' in content:
                return Framework.LARAVEL

    # Check for PHP (WordPress)
    php_files = list(path.glob("**/*.php"))
    if php_files:
        wp_patterns = [
            "plugin_name",
            "Plugin Name:",
            "wp_content",
            "register_activation_hook",
        ]
        for fpath in php_files[:5]:  # Check first 5 files for WP headers
            content = fpath.read_text(errors="ignore")
            if any(p in content for p in wp_patterns):
                return Framework.WORDPRESS

    # Check for Chrome Extension
    manifest = path / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text())
            if "manifest_version" in data:
                return Framework.CHROME_EXTENSION
        except (json.JSONDecodeError, OSError):
            pass

    return Framework.UNKNOWN


def detect_frameworks(
    path: Path, skip_ai: bool = False, model: str = "claude-sonnet-4-6"
) -> Framework:
    framework = heuristic_detect(path)
    if framework != Framework.UNKNOWN:
        return framework

    # AI Fallback
    if skip_ai:
        return Framework.UNKNOWN

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return Framework.UNKNOWN

    print("Heuristics failed. Using AI to detect framework...")
    try:
        # Collect some context: filenames and package.json if exists
        context = "Files in root: " + ", ".join(
            [f.name for f in list(path.iterdir())[:20]]
        )
        package_json = path / "package.json"
        if package_json.exists():
            context += "\npackage.json content:\n" + package_json.read_text()[:1000]

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": f"Identify the web framework or type of application for this project. Return ONLY the name from this list: Next.js, Nuxt, React, Vue, Angular, SvelteKit, Remix, Astro, Hono, Django, Rails, Express, FastAPI, Laravel, WordPress. If you cannot identify it, return Unknown.\n\nPROJECT CONTEXT:\n{context}",
                }
            ],
        )
        detected = response.content[0].text.strip()
        for f in Framework:
            if f.value.lower() == detected.lower():
                return f
    except Exception as e:
        print(f"AI detection failed: {e}")

    return Framework.UNKNOWN
