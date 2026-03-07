import os
import json
import re
import base64
import anthropic
from pathlib import Path
from ..models import RunManifest
from rich.console import Console

# Token limits for AI calls
STRUCTURE_MAX_TOKENS = 2500
CONTENT_MAX_TOKENS = 6000

SYSTEM_PROMPT = """You are DocuCraft, an expert technical documentation writer and product marketer.

You write help center articles for software products that are:
- Task-oriented: every article helps the user accomplish something specific
- Scannable: short paragraphs, clear headings, numbered steps for procedures
- Precise: reference exact UI elements by name, never use vague language
- Confident: authoritative tone without being condescending

Your output quality standards:
- H1 for the article title (one per article)
- H2 for major sections, H3 for subsections
- Every procedure uses numbered steps (1. 2. 3.)
- Screenshots are embedded right before or after the step they illustrate
- When annotated screenshots have numbered callouts, reference them: "Click **Save** [3]"
- Include a brief overview paragraph (2-3 sentences) after the H1 explaining what this article covers and why it matters
- End complex articles with a "Next Steps" section linking to related articles

NEVER use these vague phrases — always replace with specific UI element names:
- "Click the button" → "Click **Save Changes**"
- "Fill in the field" → "Enter your email in the **Email** field"
- "Navigate to the page" → "Open **Settings > Billing**"
- "Simply click" / "Just click" → state what to click
- "As shown in the image" → describe what the image shows
- "Enter your information" → name the specific fields
- "Go to the settings" → "Open **Settings** from the sidebar"
- "Follow the steps" → list the actual steps
- "Select the appropriate" → name the specific option
- "Complete the form" → list the fields to fill
- "Here you can" / "This page allows you to" → state what the user will do
- "Users can" → "You can" (direct address)

When you detect services (Stripe, Clerk, Supabase, etc.), incorporate product-specific guidance that helps users understand how those integrations work in this app."""

BANNED_PHRASES = [
    "click the button",
    "fill in the field",
    "navigate to the page",
    "simply click",
    "just click",
    "as shown in the image",
    "enter your information",
    "go to the settings",
    "follow the steps",
    "select the appropriate",
    "complete the form",
    "here you can",
    "this page allows you to",
    "users can then",
    "the system will",
    "you will see a",
    "as you can see",
    "it should be noted",
    "it is important to",
    "please note that",
]


def _check_banned_phrases(text: str) -> list:
    return [phrase for phrase in BANNED_PHRASES if phrase.lower() in text.lower()]


def _parse_json_response(text: str) -> dict | None:
    """Parse JSON from AI response, handling code blocks and raw JSON."""
    # Try code block first
    code_block = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding a JSON object — use a balanced brace approach
    # instead of greedy regex to avoid matching nested issues
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    end = start

    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth == 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def enrichment_step(manifest: RunManifest):
    console = Console()
    console.print("Running enrichment step...")

    if manifest.config.skip_ai:
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return

    client = anthropic.Anthropic(api_key=api_key)
    understanding_model = manifest.config.ai_model
    generation_model = manifest.config.generation_model

    MODEL_PRICING = {
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    }

    def update_cost(usage, model_id):
        pricing = MODEL_PRICING.get(model_id, {"input": 3.0, "output": 15.0})
        in_cost = usage.input_tokens * (pricing["input"] / 1_000_000)
        out_cost = usage.output_tokens * (pricing["output"] / 1_000_000)
        if "Enrichment" in manifest.steps:
            manifest.steps["Enrichment"].cost_estimate += in_cost + out_cost

    # 1. Generate Article Structure
    console.print(
        f"Generating documentation structure with [cyan]{understanding_model}[/cyan]..."
    )

    routes_list = manifest.discovered_routes
    screenshots_map = manifest.screenshots
    error_patterns = manifest.error_patterns or []

    # Build enriched context
    route_meta = manifest.route_metadata or {}
    public_routes = [
        r for r, m in route_meta.items() if m.get("visibility") == "public"
    ]
    protected_routes = [
        r for r, m in route_meta.items() if m.get("visibility") == "protected"
    ]
    dynamic_routes = [r for r, m in route_meta.items() if m.get("dynamic")]

    service_hints = []
    if any(
        s in manifest.detected_services
        for s in ("supabase", "clerk", "nextauth", "betterauth")
    ):
        service_hints.append(
            '- Include an "Account Management" article covering sign-up, login, password reset, and profile settings'
        )
    if "stripe" in manifest.detected_services:
        service_hints.append(
            '- Include a "Billing & Subscription" article covering plans, payment methods, and invoices'
        )
    if manifest.data_models:
        for model_name in manifest.data_models[:5]:
            service_hints.append(
                f'- Consider a feature guide for "{model_name}" management if it represents a user-facing entity'
            )

    service_hints_text = (
        "\n    ".join(service_hints)
        if service_hints
        else "No specific service-based article suggestions."
    )

    structure_prompt = f"""Based on the following product context, create a documentation plan.

Product Summary: {manifest.product_summary}
Routes Discovered: {", ".join(routes_list)}
Screenshots Available for Routes: {", ".join(screenshots_map.keys())}
Error Patterns Detected: {len(error_patterns)}
Detected Services: {", ".join(manifest.detected_services) if manifest.detected_services else "None"}
UI Components: {len(manifest.ui_components)} shadcn/ui components detected
Data Models: {", ".join(manifest.data_models) if manifest.data_models else "None"}
Route Classification: {len(public_routes)} public, {len(protected_routes)} protected, {len(dynamic_routes)} dynamic

Service-Aware Article Suggestions:
{service_hints_text}

Return a JSON object with a single key "articles", which is a list of objects.
Each object must have:
- "title": Title of the article (e.g., "Getting Started", "Dashboard Guide", "Troubleshooting")
- "description": Brief description of what this article covers.
- "related_routes": List of routes relevant to this article.
- "complexity": "Simple" or "Complex" (based on inferred feature depth).
- "group": Category name for sidebar grouping (e.g., "Getting Started", "Features", "Reference").

Include at least 3 articles:
1. Getting Started / Overview
2. Feature Guides (one or more based on routes and detected services)
3. Troubleshooting / FAQ (if error patterns exist)

Response format: JSON only. No markdown formatting."""

    articles_plan = []
    try:
        response = client.messages.create(
            model=understanding_model,
            max_tokens=STRUCTURE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": structure_prompt}],
        )
        update_cost(response.usage, understanding_model)

        parsed = _parse_json_response(response.content[0].text.strip())
        if parsed:
            articles_plan = parsed.get("articles", [])
        else:
            console.print(
                "[yellow]Warning: Could not parse JSON in AI response for structure.[/yellow]"
            )
            articles_plan = [
                {
                    "title": "Getting Started",
                    "description": "Overview of the app",
                    "related_routes": ["/"],
                    "complexity": "Simple",
                    "group": "Getting Started",
                }
            ]
    except Exception as e:
        console.print(f"[red]Structure generation failed: {e}[/red]")
        articles_plan = [
            {
                "title": "Getting Started",
                "description": "Overview of the app",
                "related_routes": ["/"],
                "complexity": "Simple",
                "group": "Getting Started",
            }
        ]

    # 2. Generate Content for each article
    generated_articles = []
    console.print(
        f"Generating content for [bold]{len(articles_plan)}[/bold] articles..."
    )

    annotated_elements = manifest.annotated_elements

    for plan in articles_plan:
        console.print(f"  - Writing '[cyan]{plan['title']}[/cyan]'...")

        relevant_screenshots = {}
        relevant_elements = {}

        for route in plan.get("related_routes", []):
            annotated_key = route + "_annotated"
            if annotated_key in screenshots_map:
                relevant_screenshots[route] = screenshots_map[annotated_key]
                if route in annotated_elements:
                    relevant_elements[route] = annotated_elements[route]
            elif route in screenshots_map:
                relevant_screenshots[route] = screenshots_map[route]

        if not relevant_screenshots and "Getting Started" in plan["title"]:
            if "/_annotated" in screenshots_map:
                relevant_screenshots["/"] = screenshots_map["/_annotated"]
                relevant_elements["/"] = annotated_elements.get("/")
            elif "/" in screenshots_map:
                relevant_screenshots["/"] = screenshots_map["/"]

        complexity_instruction = (
            "Use simple, direct language. Keep steps concise."
            if plan.get("complexity") == "Simple"
            else "Use detailed, technical language appropriate for power users. Include edge cases and advanced options."
        )

        article_route_meta = {
            r: route_meta.get(r, {})
            for r in plan.get("related_routes", [])
            if r in route_meta
        }

        article_prompt = f"""Write the documentation article: "{plan["title"]}".
Description: {plan["description"]}
Tone: {complexity_instruction}

Context:
- Product Summary: {manifest.product_summary}
- Relevant Routes: {", ".join(plan.get("related_routes", []))}
- Route Details: {json.dumps(article_route_meta)}
- Available Screenshots: {json.dumps(relevant_screenshots)}
- Numbered Callout Legend (for annotated screenshots):
{json.dumps(relevant_elements, indent=2)}
- Error Patterns: {json.dumps(error_patterns[:20])}
- Detected Services: {", ".join(manifest.detected_services) if manifest.detected_services else "None"}
- Data Models: {", ".join(manifest.data_models) if manifest.data_models else "None"}

Article structure requirements:
1. H1 title, then 2-3 sentence overview paragraph
2. H2 sections for each major topic
3. Numbered steps for any procedure
4. Embed screenshots using exact paths from "Available Screenshots": `![Description](path)`
5. Reference annotated callout numbers in brackets: "Click **Save** [3]"
6. If services are detected, explain how they work in this app
7. End with "Next Steps" if there are related topics

Return a JSON object with:
- "content": The full Markdown article content.
- "confidence_score": Float 0.0-1.0 indicating your confidence in the article quality.

Response format: JSON only."""

        try:
            # Build content blocks with screenshot images for Vision
            content_blocks = []
            project_path = Path(manifest.config.project_path)
            for route, screenshot_path in relevant_screenshots.items():
                full_path = project_path / screenshot_path
                if full_path.exists():
                    try:
                        with open(full_path, "rb") as img_file:
                            img_data = base64.standard_b64encode(
                                img_file.read()
                            ).decode("utf-8")
                            content_blocks.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": img_data,
                                    },
                                }
                            )
                            content_blocks.append(
                                {
                                    "type": "text",
                                    "text": f"Screenshot for route: {route}",
                                }
                            )
                    except Exception as img_err:
                        console.print(
                            f"  [yellow]Could not load image {full_path}: {img_err}[/yellow]"
                        )
            content_blocks.append({"type": "text", "text": article_prompt})

            art_response = client.messages.create(
                model=generation_model,
                max_tokens=CONTENT_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content_blocks}],
            )
            update_cost(art_response.usage, generation_model)
            art_text = art_response.content[0].text.strip()

            content = None
            score = 0.5

            parsed = _parse_json_response(art_text)
            if parsed:
                content = parsed.get("content")
                score = parsed.get("confidence_score", 0.5)

            if not content:
                # AI returned raw markdown instead of JSON — use it directly
                content = art_text
                content = re.sub(r'^{\s*"content":\s*"', "", content)
                content = re.sub(
                    r'"\s*,\s*"confidence_score":.*}$', "", content, flags=re.DOTALL
                )

            # Banned-phrase filter with one retry (retry includes images)
            found_banned = _check_banned_phrases(content)
            if found_banned:
                console.print(
                    f"  [yellow]Banned phrases found: {found_banned}. Retrying...[/yellow]"
                )
                retry_blocks = list(content_blocks[:-1])  # Keep images
                retry_blocks.append({
                    "type": "text",
                    "text": (
                        f"Rewrite the following article. Replace these vague phrases "
                        f"with specific UI element names and actions from the screenshots:\n"
                        f"Banned phrases found: {', '.join(found_banned)}\n\n"
                        f"Original article:\n{content}"
                    ),
                })
                try:
                    retry_resp = client.messages.create(
                        model=generation_model,
                        max_tokens=CONTENT_MAX_TOKENS,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": retry_blocks}],
                    )
                    update_cost(retry_resp.usage, generation_model)
                    retry_text = retry_resp.content[0].text.strip()
                    # Try to parse as JSON first
                    retry_parsed = _parse_json_response(retry_text)
                    if retry_parsed and retry_parsed.get("content"):
                        content = retry_parsed["content"]
                    else:
                        content = retry_text
                    still_banned = _check_banned_phrases(content)
                    if still_banned:
                        console.print(
                            f"  [yellow]Warning: Banned phrases persist after retry: {still_banned}[/yellow]"
                        )
                except Exception as retry_err:
                    console.print(f"  [yellow]Retry failed: {retry_err}[/yellow]")

            # Append score warning if low
            if score < 0.7:
                content += f"\n\n::: tip Confidence Score: {score}\nThis article was generated with lower confidence and may require human review.\n:::\n"

            generated_articles.append(
                {
                    "title": plan["title"],
                    "content": content,
                    "confidence_score": score,
                    "group": plan.get("group"),
                }
            )

        except Exception as e:
            console.print(f"[red]Failed to generate article {plan['title']}: {e}[/red]")
            generated_articles.append(
                {
                    "title": plan["title"],
                    "content": f"# {plan['title']}\n\nContent generation failed due to error: {e}",
                    "group": plan.get("group"),
                }
            )

    manifest.articles = generated_articles

    # Populate article -> route mapping for incremental updates
    manifest.article_route_map = {
        plan["title"]: plan.get("related_routes", []) for plan in articles_plan
    }

    # Populate confidence scores map
    manifest.confidence_scores = {
        a["title"]: a.get("confidence_score", 0.5) for a in generated_articles
    }

    console.print("Enrichment completed.")
