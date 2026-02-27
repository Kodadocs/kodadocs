from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Optional, Any
from enum import Enum
from pathlib import Path

from kodadocs.utils.license import LICENSE_KEY_PATTERN


class Framework(str, Enum):
    NEXTJS = "Next.js"
    NUXT = "Nuxt"
    REACT = "React"
    VUE = "Vue"
    ANGULAR = "Angular"
    SVELTEKIT = "SvelteKit"
    REMIX = "Remix"
    ASTRO = "Astro"
    HONO = "Hono"
    DJANGO = "Django"
    RAILS = "Rails"
    EXPRESS = "Express"
    FASTAPI = "FastAPI"
    LARAVEL = "Laravel"
    WORDPRESS = "WordPress"
    REACT_NATIVE = "React Native"
    SOLID = "SolidJS"
    CHROME_EXTENSION = "Chrome Extension"
    JAVASCRIPT = "JavaScript"
    PYTHON = "Python"
    UNKNOWN = "Unknown"


class AuthConfig(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    cookie_name: Optional[str] = None
    cookie_value: Optional[str] = None
    auth_url: Optional[str] = None


class SessionConfig(BaseModel):
    app_url: str = "http://localhost:3000"
    auth: Optional[AuthConfig] = None
    include_patterns: List[str] = Field(default_factory=lambda: ["**/*"])
    exclude_patterns: List[str] = Field(default_factory=list)
    framework: Framework = Framework.UNKNOWN
    project_path: Path
    output_path: Path = Path("./docs")
    brand_color: Optional[str] = "#3e8fb0"
    theme_name: str = "default"
    logo_path: Optional[Path] = None
    ai_model: str = "claude-sonnet-4-6"
    generation_model: str = "claude-haiku-4-5-20251001"
    skip_ai: bool = False
    blur_pii: bool = True
    license_key: Optional[str] = Field(
        default=None,
        pattern=LICENSE_KEY_PATTERN,
        description="Pro license key (format: kd_pro_*)",
    )
    site_slug: Optional[str] = None


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepResult(BaseModel):
    name: str
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    cost_estimate: float = 0.0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    session_id: str
    config: SessionConfig
    steps: Dict[str, StepResult] = Field(default_factory=dict)
    current_step: Optional[str] = None

    config_hash: Optional[str] = None

    # Global state accumulated across steps
    discovered_routes: List[str] = Field(default_factory=list)
    route_metadata: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )  # route -> {dynamic, type, visibility}
    detected_services: List[str] = Field(default_factory=list)
    ui_components: List[str] = Field(default_factory=list)
    data_models: List[str] = Field(default_factory=list)
    deployment_platform: Optional[str] = None
    product_summary: Optional[str] = None
    doc_outline: Dict[str, Any] = Field(default_factory=dict)
    error_patterns: List[str] = Field(default_factory=list)
    screenshots: Dict[str, str] = Field(default_factory=dict)  # route -> image_path
    dom_elements: Dict[str, Any] = Field(
        default_factory=dict
    )  # route -> list of elements or legacy tree
    annotated_elements: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict
    )  # route -> elements
    page_descriptions: Dict[str, str] = Field(
        default_factory=dict
    )  # route -> description
    pii_regions: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict
    )  # route -> list of {x, y, width, height}
    articles: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_scores: Dict[str, float] = Field(
        default_factory=dict
    )  # article -> score
    article_route_map: Dict[str, List[str]] = Field(
        default_factory=dict
    )  # article title -> related_routes
    previous_routes: List[str] = Field(
        default_factory=list
    )  # routes snapshot from last generate/update
    deploy_url: Optional[str] = None
    deploy_status: Optional[str] = None  # "success" | "failed" | "skipped"
    site_slug: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)
