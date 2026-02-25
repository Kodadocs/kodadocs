---
name: kodadocs
description: Generate end-user help documentation for web applications. Captures screenshots, analyzes code, and produces a complete VitePress help center.
---

# KodaDocs — Help Center Generator

You are orchestrating KodaDocs, a tool that generates end-user help documentation for web applications. You will analyze the codebase, capture screenshots via MCP tools, write documentation articles, and assemble a VitePress help center.

## Prerequisites

Before starting, verify:
1. Run `which kodadocs` via Bash to confirm kodadocs is installed
2. Call the `detect_framework` MCP tool with the current project path to verify the MCP server is connected
3. Check for `.kodadocs/session_config.json` — if it exists, load it for app_url, auth, brand settings
4. Check that `ANTHROPIC_API_KEY` is set in the shell environment (if using Claude Code, it's already set)

If kodadocs is not installed, tell the user: "Install kodadocs first: `pip install kodadocs` or `uvx install kodadocs`"

If the MCP server is not connected, tell the user to add this to their `.claude/settings.json`:
```json
{
  "mcpServers": {
    "kodadocs": {
      "command": "uvx",
      "args": ["kodadocs", "mcp"]
    }
  }
}
```

## Configuration

If no session_config.json exists, ask the user for:
- **App URL** (for screenshots): e.g., http://localhost:3000
- **Auth credentials** (if app requires login): username, password, login URL
- **Brand color** (hex): default #3e8fb0
- **Logo path** (optional): path to logo image

## Pipeline Phases

Execute these phases in order. After each phase, call the `save_manifest` MCP tool to persist state.

### Phase 1: Discovery

Analyze the codebase to discover routes and understand the application structure.

1. Call `detect_framework` MCP tool to identify the framework
2. Based on the framework, use Read/Grep/Glob to discover routes:
   - **Next.js**: Glob for `**/app/**/page.tsx` and `**/pages/**/*.tsx`
   - **React**: Grep for `<Route path=` and `createBrowserRouter`
   - **SvelteKit**: Glob for `**/src/routes/**/+page.svelte`
   - **Nuxt**: Glob for `**/pages/**/*.vue`
   - **Django**: Grep for `urlpatterns` and `path(` in urls.py files
   - **Other**: Grep for route definitions in common patterns
3. For each route, note if it's dynamic (contains `[param]` or `:param`)
4. Check for middleware/auth guards to classify routes as public/protected
5. Scan `package.json` or equivalent for known services (Supabase, Stripe, Clerk, etc.)

**Output:** Save discovered_routes, route_metadata, detected_services via `save_manifest`.

### Phase 2: Code Analysis

Read the source code to understand what the application does.

1. For each discovered route, Read the page/component file
2. Produce a `product_summary` (2-3 paragraphs):
   - What the application does, written for end users
   - Key features and capabilities
   - NO code references, NO technical implementation details
3. Produce a `doc_outline` — the help center structure:
   - Getting Started guide
   - Feature guides (one per major feature area)
   - FAQ section
   - Troubleshooting section
4. Extract error patterns: Grep for `throw new Error`, `raise.*Error`, `console.error`, validation messages
5. Detect data models: Read Prisma schema, Drizzle definitions, or equivalent

**Output:** Save product_summary, doc_outline, error_patterns, data_models via `save_manifest`.

### Phase 3: Screenshot Capture

Call MCP tools to capture and annotate screenshots.

1. Call `capture_screenshots` MCP tool with:
   - `routes`: The discovered non-dynamic, non-API routes
   - `app_url`: From config
   - `auth`: From config (or null)
   - `output_dir`: `.kodadocs/screenshots` in the project directory
   - `blur_pii`: `true` (default) — detects and records PII-sensitive regions (email fields, phone fields, profile sections, text matching email/phone patterns)
2. Parse the returned JSON — check for errors, note which routes succeeded. The response includes a `pii_regions` dict mapping routes to detected PII bounding boxes.
3. Call `annotate_screenshots` MCP tool with:
   - `screenshots_dir`: The output directory from step 1
   - `dom_elements`: The dom_elements dict from the capture result
   - `brand_color`: From config
   - `pii_regions`: The `pii_regions` dict from the capture result — the tool will Gaussian-blur these regions on the base screenshots *before* adding numbered callouts, so PII is obscured but annotations remain sharp

**Output:** Save screenshots, dom_elements, and pii_regions via `save_manifest`.

### Phase 4: Doc Generation

Write each documentation article. This is the core value — you ARE the AI writer.

For each article in the doc_outline:

1. **Getting Started guide:**
   - Brief product overview (from product_summary)
   - How to access the app
   - First steps a new user should take
   - Reference screenshots with `![Description](./assets/screenshot.png)`

2. **Feature guides (one per feature):**
   - What the feature does
   - Step-by-step walkthrough
   - Reference annotated screenshots — use callout numbers: "Click the Save button [3]"
   - Tips and best practices

3. **FAQ:**
   - Seed from error_patterns: each error -> a "Why am I seeing X?" entry
   - Common questions based on route structure
   - Service-specific questions (e.g., billing if Stripe detected)

4. **Troubleshooting:**
   - Error messages and their solutions
   - Common issues based on detected services

**Writing rules:**
- Write from the END USER perspective, never the developer perspective
- NO code references, NO technical jargon unless the app itself uses it
- NO banned phrases: "Click the button", "Fill in the field", "Navigate to the page", "Simply click", "Just click"
- Use SPECIFIC UI element names: "Click **Save Changes**" not "Click the button"
- Tone calibration: simple app (< 5 routes) = plain language; complex app (10+ routes) = more detailed
- Each article gets a confidence score (0.0-1.0) based on how much is grounded in actual UI vs inferred
- Flag articles below 0.7 confidence with: "> **Note:** This article may need human review."

**Output:** Collect all articles as a list of `{title, content, confidence_score}` dicts.

### Phase 5: Output Assembly

**Before calling the assembly tool**, ask the user:
- "What tagline would you like for the home page?" — suggest the auto-extracted first sentence of the product summary as default
- "Which features should be highlighted on the home page?" — suggest the top 3 article titles as defaults
- "What should the Get Started button say?" — default is "Get Started"

1. Call `assemble_vitepress` MCP tool with:
   - `articles`: The generated articles list
   - `screenshots_dir`: `.kodadocs/screenshots`
   - `brand_color`: From config
   - `logo_path`: From config (or null)
   - `output_dir`: Project's docs/ directory
   - `project_name`: Project directory name
   - `product_summary`: From Phase 2
   - `discovered_routes`: From Phase 1
   - `hero_tagline`: User's chosen tagline (or omit for auto-extracted default)
   - `hero_cta_text`: User's chosen button text (or omit for "Get Started")
   - `hero_cta_link`: Override link target (or omit — defaults to first article slug)
   - `feature_highlights`: User's chosen features as `[{title, details}]` (or omit for auto-generated from articles)
   - `show_product_summary`: `true` to display product summary on home page body

2. Call `save_manifest` with the complete pipeline state

3. Tell the user:
   - Docs generated at `[output_dir]`
   - To preview locally: `cd [output_dir] && npm install && npm run docs:dev`
   - Number of articles generated and their confidence scores

### Phase 6: Deploy (Optional)

Ask the user: "Would you like to deploy the help center?"

If they want to deploy:

1. **Check for Pro license** — ask: "Do you have a KodaDocs Pro license key? (Pro enables hosted deploy to yourapp.kodadocs.com and badge removal — $12/mo at https://kodadocs.com/pricing)"
   - If they provide a key matching `kd_pro_*`, store it for the deploy call
   - If not, explain: "No problem! Free-tier deploys work great with self-hosted providers. Note: free deploys include a small 'Powered by KodaDocs' badge."
2. **Detect provider** — check if the manifest has a `deployment_platform` from Phase 1 discovery
3. **Ask which provider** — suggest the auto-detected one if available, otherwise list options:
   - **Cloudflare Pages** — requires `CLOUDFLARE_API_TOKEN` env var, install: `npm install -g wrangler`
   - **Vercel** — requires `VERCEL_TOKEN` env var, install: `npm install -g vercel`
   - **Netlify** — requires `NETLIFY_AUTH_TOKEN` + `NETLIFY_SITE_ID` env vars, install: `npm install -g netlify-cli`
   - **GitHub Pages** — no env vars needed (uses git auth), install: `npm install -g gh-pages`
   - **KodaDocs Hosted** (coming soon) — requires Pro license key, deploys to `yourapp.kodadocs.com`
4. **If KodaDocs Hosted chosen:**
   - Require license key (fail with pricing link if missing)
   - Ask for site slug: "What subdomain do you want? (e.g., `myapp` for myapp.kodadocs.com)" — lowercase alphanumeric and hyphens only
   - Pass `license_key` and `site_slug` to `deploy_site` MCP tool with `provider="kodadocs"`
   - Note: This provider is not yet available. Tell the user: "KodaDocs hosted deploy is coming soon. For now, please choose a self-hosted provider."
5. **Call `deploy_site` MCP tool** with:
   - `site_dir`: The docs output directory
   - `project_name`: The project directory name
   - `provider`: The user's chosen provider
   - `detected_platform`: The auto-detected platform (if any)
   - `license_key`: The Pro license key (if provided)
   - `site_slug`: The chosen subdomain (if KodaDocs Hosted)
6. **Share the result** — on success, show the deployed URL; on failure, show the error with fix instructions (missing CLI, missing env var, etc.)

## Quality Checklist

Before completing, verify:
- [ ] All non-dynamic routes have screenshots
- [ ] Every article references at least one screenshot
- [ ] No article contains code snippets or developer jargon
- [ ] No banned phrases in any article
- [ ] Articles below 0.7 confidence are flagged
- [ ] run_manifest.json is saved with complete state
