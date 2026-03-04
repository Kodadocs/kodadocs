import os
import json
import re
import base64
import anthropic
from pathlib import Path
from ..models import RunManifest
from rich.console import Console

# Token limits for AI calls
STRUCTURE_MAX_TOKENS = 1500
CONTENT_MAX_TOKENS = 8000


def enrichment_step(manifest: RunManifest):
    console = Console()
    console.print("Running enrichment step...")

    # Check if AI is disabled
    if manifest.config.skip_ai:
        return

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return

    client = anthropic.Anthropic(api_key=api_key)
    understanding_model = manifest.config.ai_model  # Sonnet for structure/understanding
    generation_model = manifest.config.generation_model  # Haiku for content generation

    # Model pricing (per million tokens)
    MODEL_PRICING = {
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    }

    # 1. Generate Article Structure
    console.print(
        f"Generating documentation structure with [cyan]{understanding_model}[/cyan]..."
    )

    def update_cost(usage, model_id):
        pricing = MODEL_PRICING.get(model_id, {"input": 3.0, "output": 15.0})
        in_cost = usage.input_tokens * (pricing["input"] / 1_000_000)
        out_cost = usage.output_tokens * (pricing["output"] / 1_000_000)
        if "Enrichment" in manifest.steps:
            manifest.steps["Enrichment"].cost_estimate += in_cost + out_cost

    BANNED_PHRASES = [
        "Click the button",
        "Fill in the field",
        "Navigate to the page",
        "Simply click",
        "Just click",
        "As shown in the image",
        "Enter your information",
        "Go to the settings",
        "Follow the steps",
        "Select the appropriate",
        "Complete the form",
    ]

    def _check_banned_phrases(text: str) -> list:
        return [phrase for phrase in BANNED_PHRASES if phrase.lower() in text.lower()]

    routes_list = manifest.discovered_routes
    screenshots_map = manifest.screenshots
    error_patterns = manifest.error_patterns or []

    # Build enriched context from detected services, components, and models
    route_meta = manifest.route_metadata or {}
    public_routes = [
        r for r, m in route_meta.items() if m.get("visibility") == "public"
    ]
    protected_routes = [
        r for r, m in route_meta.items() if m.get("visibility") == "protected"
    ]
    dynamic_routes = [r for r, m in route_meta.items() if m.get("dynamic")]

    service_hints = []
    if (
        "supabase" in manifest.detected_services
        or "clerk" in manifest.detected_services
        or "nextauth" in manifest.detected_services
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

    structure_prompt = f"""
    You are a technical writer for a software product.
    Based on the following product summary and discovered routes, create a documentation plan.

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

    Include at least 3 articles:
    1. Getting Started / Overview
    2. Feature Guides (one or more based on routes and detected services)
    3. Troubleshooting / FAQ (if error patterns exist)

    Response format: JSON only. No markdown formatting.
    """

    articles_plan = []
    try:
        response = client.messages.create(
            model=understanding_model,
            max_tokens=STRUCTURE_MAX_TOKENS,
            messages=[{"role": "user", "content": structure_prompt}],
        )
        update_cost(response.usage, understanding_model)
        content_text = response.content[0].text.strip()

        # Robust JSON extraction
        json_match = re.search(r"\{.*\}", content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            structure = json.loads(json_str)
            articles_plan = structure.get("articles", [])
        else:
            console.print(
                "[yellow]Warning: Could not find JSON in AI response for structure.[/yellow]"
            )
            articles_plan = [
                {
                    "title": "Getting Started",
                    "description": "Overview of the app",
                    "related_routes": ["/"],
                    "complexity": "Simple",
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

        # Prepare context specific to this article
        relevant_screenshots = {}
        relevant_elements = {}

        for route in plan.get("related_routes", []):
            # Prioritize annotated screenshots
            annotated_key = route + "_annotated"
            if annotated_key in screenshots_map:
                relevant_screenshots[route] = screenshots_map[annotated_key]
                if route in annotated_elements:
                    relevant_elements[route] = annotated_elements[route]
            elif route in screenshots_map:
                relevant_screenshots[route] = screenshots_map[route]

        if not relevant_screenshots and "Getting Started" in plan["title"]:
            # Fallback to index if no routes matched
            if "/_annotated" in screenshots_map:
                relevant_screenshots["/"] = screenshots_map["/_annotated"]
                relevant_elements["/"] = annotated_elements.get("/")
            elif "/" in screenshots_map:
                relevant_screenshots["/"] = screenshots_map["/"]

        complexity_instruction = (
            "Use simple, direct language."
            if plan.get("complexity") == "Simple"
            else "Use detailed, technical language appropriate for power users."
        )

        # Build per-article route context
        article_route_meta = {
            r: route_meta.get(r, {})
            for r in plan.get("related_routes", [])
            if r in route_meta
        }

        article_prompt = f"""
        Write the documentation article: "{plan["title"]}".
        Description: {plan["description"]}
        Tone Instruction: {complexity_instruction}

        Context:
        - Product Summary: {manifest.product_summary}
        - Relevant Routes: {", ".join(plan.get("related_routes", []))}
        - Route Details: {json.dumps(article_route_meta)}
        - Available Screenshots (some are annotated with numbered callouts): {json.dumps(relevant_screenshots)}
        - Numbered Callout Legend (for the annotated screenshots):
        {json.dumps(relevant_elements, indent=2)}
        - Error Patterns: {json.dumps(error_patterns[:20])}
        - Detected Services: {", ".join(manifest.detected_services) if manifest.detected_services else "None"}
        - Data Models: {", ".join(manifest.data_models) if manifest.data_models else "None"}

        IMPORTANT:
        1. When referencing UI elements from annotated screenshots, use their callout number in brackets, e.g., "Click the Save button [3]".
        2. Use the "Available Screenshots" paths exactly as provided for image embedding.
        3. If no annotated screenshot exists for a route, describe the UI elements by name.
        4. If services like Supabase, Clerk, or Stripe are detected, incorporate relevant user-facing guidance (e.g., how auth works, how to manage billing).
        5. Reference data models by name when explaining features that manage those entities.

        Return a JSON object with:
        - "content": The full Markdown content. Use H1 for title. Embed matching screenshots with `![Alt](path)`.
        - "confidence_score": Float 0.0-1.0.
        - "reasoning": Brief explanation.

        Response format: JSON only.
        """

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
                messages=[{"role": "user", "content": content_blocks}],
            )
            update_cost(art_response.usage, generation_model)
            art_text = art_response.content[0].text.strip()

            # 1. Try to extract JSON from code blocks first
            content = None
            score = 0.5

            json_code_block = re.search(r"```json\s*(.*?)\s*```", art_text, re.DOTALL)
            json_str = json_code_block.group(1) if json_code_block else None

            if not json_str:
                # 2. Try to find raw { } block
                json_match = re.search(r"\{.*\}", art_text, re.DOTALL)
                json_str = json_match.group(0) if json_match else None

            if json_str:
                try:
                    art_data = json.loads(json_str)
                    content = art_data.get("content")
                    score = art_data.get("confidence_score", 0.5)
                except Exception as json_err:
                    console.print(
                        f"[yellow]Warning: JSON parsing failed for {plan['title']}: {json_err}[/yellow]"
                    )
                    # JSON was invalid, fall through to raw text
                    pass

            # 3. If we couldn't get content from JSON, use the raw text but strip JSON wrappers
            if not content:
                # If the AI ignored the JSON instruction and gave us raw markdown
                content = art_text
                # Remove any JSON-like keys if it accidentally returned a mix
                content = re.sub(r'^{\s*"content":\s*"', "", content)
                content = re.sub(
                    r'"\s*,\s*"confidence_score":.*}$', "", content, flags=re.DOTALL
                )

            # Banned-phrase filter with one retry
            found_banned = _check_banned_phrases(content)
            if found_banned:
                console.print(
                    f"  [yellow]Banned phrases found: {found_banned}. Retrying...[/yellow]"
                )
                retry_prompt = f"Rewrite the following article, replacing these vague phrases with specific UI element names and actions:\nBanned phrases found: {', '.join(found_banned)}\n\nOriginal article:\n{content}"
                try:
                    retry_resp = client.messages.create(
                        model=generation_model,
                        max_tokens=CONTENT_MAX_TOKENS,
                        messages=[{"role": "user", "content": retry_prompt}],
                    )
                    update_cost(retry_resp.usage, generation_model)
                    content = retry_resp.content[0].text.strip()
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
                {"title": plan["title"], "content": content, "confidence_score": score}
            )

        except Exception as e:
            console.print(f"[red]Failed to generate article {plan['title']}: {e}[/red]")
            generated_articles.append(
                {
                    "title": plan["title"],
                    "content": f"# {plan['title']}\n\nContent generation failed due to error: {e}",
                }
            )

    manifest.articles = generated_articles

    # Populate article → route mapping for incremental updates
    manifest.article_route_map = {
        plan["title"]: plan.get("related_routes", []) for plan in articles_plan
    }

    # Populate confidence scores map
    manifest.confidence_scores = {
        a["title"]: a.get("confidence_score", 0.5) for a in generated_articles
    }

    console.print("Enrichment completed.")
