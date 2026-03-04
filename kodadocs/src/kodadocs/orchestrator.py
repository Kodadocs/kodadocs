import hashlib
import json
from pathlib import Path
from typing import List, Optional, Callable, Any
from datetime import datetime
from .models import RunManifest, SessionConfig, StepResult, StepStatus

from rich.console import Console


class PipelineStep:
    def __init__(
        self,
        name: str,
        run_fn: Callable[[RunManifest], Any],
        critical: bool = True,
        force_rerun: bool = False,
    ):
        self.name = name
        self.run_fn = run_fn
        self.critical = critical
        self.force_rerun = force_rerun


class PipelineOrchestrator:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.manifest_path = project_path / ".kodadocs" / "run_manifest.json"
        self.steps: List[PipelineStep] = []
        self.manifest: Optional[RunManifest] = None
        self.console = Console()

    def register_step(
        self,
        name: str,
        run_fn: Callable[[RunManifest], Any],
        critical: bool = True,
        force_rerun: bool = False,
    ):
        self.steps.append(PipelineStep(name, run_fn, critical, force_rerun))

    def load_manifest(self) -> Optional[RunManifest]:
        if self.manifest_path.exists():
            with open(self.manifest_path, "r") as f:
                data = json.load(f)
                # Migrate legacy manifests missing required fields
                if "session_id" not in data:
                    data["session_id"] = "legacy_" + datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )
                if "config" not in data:
                    data["config"] = {
                        "app_url": "http://localhost:3000",
                        "project_path": str(self.project_path),
                    }
                return RunManifest.model_validate(data)
        return None

    def save_manifest(self):
        self.manifest_path.parent.mkdir(exist_ok=True, parents=True)
        with open(self.manifest_path, "w") as f:
            f.write(self.manifest.model_dump_json(indent=2))

    def _config_hash(self, config: SessionConfig) -> str:
        return hashlib.md5(config.model_dump_json().encode()).hexdigest()

    def run(self, config: SessionConfig):
        # Load or create manifest
        self.manifest = self.load_manifest()
        config_hash = self._config_hash(config)

        if self.manifest and self.manifest.config_hash != config_hash:
            self.console.print(
                "[yellow]Config changed since last run. Starting fresh.[/yellow]"
            )
            self.manifest = None

        if not self.manifest:
            self.manifest = RunManifest(
                session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
                config=config,
                config_hash=config_hash,
            )
            self.save_manifest()

        # Sync config if resume
        self.manifest.config = config
        self.manifest.config_hash = config_hash

        for step in self.steps:
            # Check if step is already completed
            step_res = self.manifest.steps.get(step.name)
            if (
                step_res
                and step_res.status == StepStatus.COMPLETED
                and not step.force_rerun
            ):
                self.console.print(f"Skipping completed step: [cyan]{step.name}[/cyan]")
                continue

            # Initialize step result
            if not step_res:
                step_res = StepResult(name=step.name)
                self.manifest.steps[step.name] = step_res

            step_res.status = StepStatus.RUNNING
            step_res.started_at = datetime.now().isoformat()
            self.manifest.current_step = step.name
            self.save_manifest()

            self.console.print(f"Running step: [bold blue]{step.name}[/bold blue]...")
            try:
                # Execute step function
                step.run_fn(self.manifest)

                step_res.status = StepStatus.COMPLETED
                step_res.finished_at = datetime.now().isoformat()
                self.save_manifest()
                self.console.print(
                    f"Step [bold green]{step.name}[/bold green] completed."
                )
            except Exception as e:
                step_res.status = StepStatus.FAILED
                step_res.error = str(e)
                step_res.finished_at = datetime.now().isoformat()
                self.save_manifest()
                self.console.print(f"Step [bold red]{step.name}[/bold red] failed: {e}")

                if step.critical:
                    self.console.print(
                        "[bold red]Critical step failed. Aborting.[/bold red]"
                    )
                    break
                else:
                    self.console.print(
                        "[yellow]Non-critical step failed. Continuing.[/yellow]"
                    )

        # Final reporting
        total_cost = sum(s.cost_estimate for s in self.manifest.steps.values())
        self.console.print(
            f"[bold green]Pipeline execution finished.[/bold green] Total Estimated Cost: [bold cyan]${total_cost:.4f}[/bold cyan]"
        )
        return self.manifest

    def run_step_directly(self, name: str, fn, *args, **kwargs):
        """Run a single step with tracking outside the normal loop."""
        step_res = StepResult(name=name)
        self.manifest.steps[name] = step_res
        step_res.status = StepStatus.RUNNING
        step_res.started_at = datetime.now().isoformat()
        self.save_manifest()
        try:
            fn(self.manifest, *args, **kwargs)
            step_res.status = StepStatus.COMPLETED
            step_res.finished_at = datetime.now().isoformat()
        except Exception as e:
            step_res.status = StepStatus.FAILED
            step_res.error = str(e)
            step_res.finished_at = datetime.now().isoformat()
            raise
        finally:
            self.save_manifest()
