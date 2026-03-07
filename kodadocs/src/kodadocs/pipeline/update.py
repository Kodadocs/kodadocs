"""Incremental documentation update pipeline.

Provides functions for diffing routes, pruning stale data, and selectively
re-capturing / re-enriching only the routes that changed.
"""

import os
import json
import re
import base64
import anthropic
from pathlib import Path
from typing import Set, Tuple, List, Optional
from rich.console import Console
from ..models import RunManifest
from .enrichment import SYSTEM_PROMPT, _parse_json_response


def compute_route_diff(
    previous: List[str],
    current: List[str],
    forced: Optional[List[str]] = None,
) -> Tuple[Set[str], Set[str], Set[str]]:
    """Compute added, removed, and forced-changed routes.

    Returns (added, removed, changed) where:
    - added: routes in current but not in previous
    - removed: routes in previous but not in current
    - changed: forced routes that exist in current (for re-capture)
    """
    prev_set = set(previous)
    curr_set = set(current)
    added = curr_set - prev_set
    removed = prev_set - curr_set
    changed = set(forced or []) & curr_set
    return added, removed, changed


def prune_removed_routes(manifest: RunManifest, removed: Set[str]):
    """Remove all manifest data for routes that no longer exist."""
    for route in removed:
        manifest.screenshots.pop(route, None)
        manifest.screenshots.pop(route + "_annotated", None)
        manifest.dom_elements.pop(route, None)
        manifest.annotated_elements.pop(route, None)
        manifest.pii_regions.pop(route, None)
        manifest.page_descriptions.pop(route, None)
        manifest.route_metadata.pop(route, None)


def prune_removed_articles(manifest: RunManifest, removed: Set[str]):
    """Remove articles whose related routes are ALL gone.

    Articles that still have at least one surviving route are kept.
    """
    if not manifest.article_route_map or not removed:
        return

    titles_to_remove = []
    for title, routes in manifest.article_route_map.items():
        if not routes:
            continue
        surviving = [r for r in routes if r not in removed]
        if not surviving:
            titles_to_remove.append(title)

    for title in titles_to_remove:
        manifest.articles = [a for a in manifest.articles if a.get("title") != title]
        manifest.confidence_scores.pop(title, None)
        manifest.article_route_map.pop(title, None)


def selective_capture_step(manifest: RunManifest, routes_to_capture: Set[str]):
    """Run capture_step for only the specified routes."""
    from .capture import capture_step

    original_routes = manifest.discovered_routes
    manifest.discovered_routes = sorted(routes_to_capture)
    try:
        capture_step(manifest)
    finally:
        manifest.discovered_routes = original_routes


def selective_annotation_step(manifest: RunManifest, routes_to_annotate: Set[str]):
    """Run annotation for only the specified routes."""
    from .annotation import extract_elements, blur_pii_regions, annotate_screenshot

    console = Console()
    project_path = manifest.config.project_path
    brand_color = manifest.config.brand_color or "#3e8fb0"
    annotated_dir = project_path / ".kodadocs" / "screenshots" / "annotated"
    annotated_dir.mkdir(exist_ok=True, parents=True)

    # PII blur pass for targeted routes
    if manifest.config.blur_pii and manifest.pii_regions:
        for route in routes_to_annotate:
            regions = manifest.pii_regions.get(route)
            screenshot_rel = manifest.screenshots.get(route)
            if not screenshot_rel or not regions:
                continue
            src_path = project_path / screenshot_rel
            if src_path.exists():
                console.print(
                    f"  Blurring PII in [cyan]{route}[/cyan] ({len(regions)} regions)..."
                )
                blur_pii_regions(src_path, regions, src_path)

    for route in routes_to_annotate:
        screenshot_rel = manifest.screenshots.get(route)
        if not screenshot_rel:
            continue
        dom_data = manifest.dom_elements.get(route)
        if not dom_data:
            continue

        elements = extract_elements(dom_data)
        if not elements:
            continue

        src_path = project_path / screenshot_rel
        safe_route = route.strip("/").replace("/", "-") or "index"
        dest_path = annotated_dir / f"{safe_route}.png"

        console.print(f"  Annotating [cyan]{route}[/cyan]...")
        placed_elements = annotate_screenshot(
            src_path, elements, dest_path, brand_color
        )

        if placed_elements:
            manifest.screenshots[route + "_annotated"] = str(
                dest_path.relative_to(project_path)
            )
            manifest.annotated_elements[route] = placed_elements


def incremental_enrichment_step(
    manifest: RunManifest,
    new_routes: Set[str],
    changed_routes: Set[str],
):
    """Generate articles only for new/changed routes, merging into existing articles."""
    console = Console()

    if manifest.config.skip_ai:
        console.print("[yellow]Skipping AI enrichment (skip_ai=True).[/yellow]")
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
        if "IncrementalEnrichment" in manifest.steps:
            manifest.steps["IncrementalEnrichment"].cost_estimate += in_cost + out_cost

    existing_titles = [a.get("title") for a in manifest.articles]

    # 1. Structure call — ask AI what articles to create/update
    structure_prompt = f"""
    You are a technical writer updating documentation for a software product.

    Product Summary: {manifest.product_summary}

    NEW routes added to the app: {", ".join(sorted(new_routes)) if new_routes else "None"}
    CHANGED routes (re-captured): {", ".join(sorted(changed_routes)) if changed_routes else "None"}

    Existing article titles: {json.dumps(existing_titles)}
    Existing article-route mapping: {json.dumps(manifest.article_route_map)}

    All current routes: {", ".join(manifest.discovered_routes)}
    Screenshots available: {", ".join(manifest.screenshots.keys())}

    Based on the new/changed routes, decide:
    1. Which NEW articles should be created (for routes that don't fit existing articles)?
    2. Which EXISTING articles should be UPDATED to incorporate new routes?

    Return a JSON object with:
    - "new_articles": list of {{"title": str, "description": str, "related_routes": [str], "complexity": "Simple"|"Complex"}}
    - "updated_articles": list of {{"title": str, "additional_routes": [str]}}

    Rules:
    - Only create new articles if the new routes don't fit naturally into existing articles.
    - If a new route fits an existing article's scope, add it to updated_articles instead.
    - For changed routes, if the article already covers that route, include it in updated_articles to refresh content.

    Response format: JSON only. No markdown formatting.
    """

    try:
        response = client.messages.create(
            model=understanding_model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": structure_prompt}],
        )
        update_cost(response.usage, understanding_model)
        content_text = response.content[0].text.strip()

        parsed = _parse_json_response(content_text)
        if parsed:
            plan = parsed
        else:
            console.print(
                "[yellow]Could not parse AI structure response. Creating default articles.[/yellow]"
            )
            plan = {
                "new_articles": [
                    {
                        "title": "New Features",
                        "description": "Documentation for newly added pages",
                        "related_routes": sorted(new_routes),
                        "complexity": "Simple",
                    }
                ]
                if new_routes
                else [],
                "updated_articles": [],
            }
    except Exception as e:
        console.print(f"[red]Structure generation failed: {e}[/red]")
        plan = {
            "new_articles": [
                {
                    "title": "New Features",
                    "description": "Documentation for newly added pages",
                    "related_routes": sorted(new_routes),
                    "complexity": "Simple",
                }
            ]
            if new_routes
            else [],
            "updated_articles": [],
        }

    new_article_plans = plan.get("new_articles", [])
    updated_article_plans = plan.get("updated_articles", [])

    screenshots_map = manifest.screenshots
    annotated_elements = manifest.annotated_elements
    project_path = Path(manifest.config.project_path)

    def _generate_article_content(title, description, related_routes, complexity):
        """Generate content for a single article using Haiku."""
        relevant_screenshots = {}
        relevant_elements = {}

        for route in related_routes:
            annotated_key = route + "_annotated"
            if annotated_key in screenshots_map:
                relevant_screenshots[route] = screenshots_map[annotated_key]
                if route in annotated_elements:
                    relevant_elements[route] = annotated_elements[route]
            elif route in screenshots_map:
                relevant_screenshots[route] = screenshots_map[route]

        complexity_instruction = (
            "Use simple, direct language."
            if complexity == "Simple"
            else "Use detailed, technical language appropriate for power users."
        )

        article_prompt = f"""
        Write the documentation article: "{title}".
        Description: {description}
        Tone Instruction: {complexity_instruction}

        Context:
        - Product Summary: {manifest.product_summary}
        - Relevant Routes: {", ".join(related_routes)}
        - Available Screenshots: {json.dumps(relevant_screenshots)}
        - Numbered Callout Legend:
        {json.dumps(relevant_elements, indent=2)}

        Return a JSON object with:
        - "content": Full Markdown content. Use H1 for title. Embed screenshots with `![Alt](path)`.
        - "confidence_score": Float 0.0-1.0.

        Response format: JSON only.
        """

        content_blocks = []
        for route, screenshot_path in relevant_screenshots.items():
            full_path = project_path / screenshot_path
            if full_path.exists():
                try:
                    with open(full_path, "rb") as img_file:
                        img_data = base64.standard_b64encode(img_file.read()).decode(
                            "utf-8"
                        )
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
                            {"type": "text", "text": f"Screenshot for route: {route}"}
                        )
                except Exception:
                    pass
        content_blocks.append({"type": "text", "text": article_prompt})

        art_response = client.messages.create(
            model=generation_model,
            max_tokens=3000,
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
            content = art_text

        return content, score

    # 2. Generate new articles
    for article_plan in new_article_plans:
        title = article_plan.get("title", "New Article")
        console.print(f"  Generating new article: '[cyan]{title}[/cyan]'...")
        try:
            content, score = _generate_article_content(
                title,
                article_plan.get("description", ""),
                article_plan.get("related_routes", []),
                article_plan.get("complexity", "Simple"),
            )
            manifest.articles.append(
                {
                    "title": title,
                    "content": content,
                    "confidence_score": score,
                }
            )
            manifest.confidence_scores[title] = score
            manifest.article_route_map[title] = article_plan.get("related_routes", [])
        except Exception as e:
            console.print(f"[red]Failed to generate article '{title}': {e}[/red]")

    # 3. Regenerate updated articles
    for update_plan in updated_article_plans:
        title = update_plan.get("title")
        if not title:
            continue

        existing = next((a for a in manifest.articles if a.get("title") == title), None)
        if not existing:
            console.print(
                f"  [yellow]Article '{title}' not found for update, skipping.[/yellow]"
            )
            continue

        additional_routes = update_plan.get("additional_routes", [])
        existing_routes = manifest.article_route_map.get(title, [])
        all_routes = sorted(set(existing_routes) | set(additional_routes))

        console.print(
            f"  Regenerating article: '[cyan]{title}[/cyan]' (adding routes: {additional_routes})..."
        )
        try:
            content, score = _generate_article_content(
                title,
                f"Updated article covering routes: {', '.join(all_routes)}",
                all_routes,
                "Simple",
            )
            existing["content"] = content
            existing["confidence_score"] = score
            manifest.confidence_scores[title] = score
            manifest.article_route_map[title] = all_routes
        except Exception as e:
            console.print(f"[red]Failed to update article '{title}': {e}[/red]")

    console.print("Incremental enrichment completed.")
