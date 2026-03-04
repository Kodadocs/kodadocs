from kodadocs.orchestrator import PipelineOrchestrator
from kodadocs.models import SessionConfig, StepStatus


def test_orchestrator_initialization(tmp_path):
    project_path = tmp_path / "test_project"
    project_path.mkdir()

    orchestrator = PipelineOrchestrator(project_path)
    assert orchestrator.project_path == project_path
    assert (
        orchestrator.manifest_path == project_path / ".kodadocs" / "run_manifest.json"
    )
    assert len(orchestrator.steps) == 0


def test_register_step(tmp_path):
    orchestrator = PipelineOrchestrator(tmp_path)

    def mock_step(manifest):
        manifest.product_summary = "test done"

    orchestrator.register_step("TestStep", mock_step)
    assert len(orchestrator.steps) == 1
    assert orchestrator.steps[0].name == "TestStep"


def test_register_step_with_force_rerun(tmp_path):
    orchestrator = PipelineOrchestrator(tmp_path)

    def mock_step(manifest):
        pass

    orchestrator.register_step("Output", mock_step, force_rerun=True)
    assert orchestrator.steps[0].force_rerun is True


def test_orchestrator_run_basic(tmp_path):
    project_path = tmp_path
    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=project_path,
        output_path=project_path / "docs",
    )

    orchestrator = PipelineOrchestrator(project_path)

    def mock_step(manifest):
        manifest.product_summary = "Test Summary"

    orchestrator.register_step("MockStep", mock_step)
    manifest = orchestrator.run(config)

    assert manifest.product_summary == "Test Summary"
    assert "MockStep" in manifest.steps
    assert manifest.steps["MockStep"].status == StepStatus.COMPLETED


def test_orchestrator_config_hash_invalidation(tmp_path):
    config1 = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        output_path=tmp_path / "docs",
    )
    config2 = SessionConfig(
        app_url="http://localhost:4000",
        project_path=tmp_path,
        output_path=tmp_path / "docs",
    )

    orchestrator = PipelineOrchestrator(tmp_path)

    def mock_step(manifest):
        manifest.product_summary = "First run"

    orchestrator.register_step("Step1", mock_step)
    manifest1 = orchestrator.run(config1)
    assert manifest1.product_summary == "First run"

    # Second run with different config should start fresh
    orchestrator2 = PipelineOrchestrator(tmp_path)

    def mock_step2(manifest):
        manifest.product_summary = "Second run"

    orchestrator2.register_step("Step1", mock_step2)
    manifest2 = orchestrator2.run(config2)
    assert manifest2.product_summary == "Second run"


def test_orchestrator_checkpoint_resume(tmp_path):
    config = SessionConfig(
        app_url="http://localhost:3000",
        project_path=tmp_path,
        output_path=tmp_path / "docs",
    )

    orchestrator = PipelineOrchestrator(tmp_path)
    call_count = {"step1": 0, "step2": 0}

    def step1(manifest):
        call_count["step1"] += 1
        manifest.product_summary = "step1 done"

    def step2(manifest):
        call_count["step2"] += 1
        raise Exception("step2 fails")

    orchestrator.register_step("Step1", step1)
    orchestrator.register_step("Step2", step2)
    orchestrator.run(config)

    assert call_count["step1"] == 1
    assert call_count["step2"] == 1

    # Resume: Step1 should be skipped, Step2 retried
    orchestrator2 = PipelineOrchestrator(tmp_path)
    call_count2 = {"step1": 0, "step2": 0}

    def step1_v2(manifest):
        call_count2["step1"] += 1

    def step2_v2(manifest):
        call_count2["step2"] += 1

    orchestrator2.register_step("Step1", step1_v2)
    orchestrator2.register_step("Step2", step2_v2)
    orchestrator2.run(config)

    assert call_count2["step1"] == 0  # Skipped (already completed)
    assert call_count2["step2"] == 1  # Retried
