# Ensures `app` is importable in tests without installing the project.
import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True, scope="session")
def _deterministic_pipeline() -> None:
    # Don't auto-run the AI pipeline on complaint create during tests — AI tests call
    # run_pipeline() explicitly so behaviour is deterministic, and console/complaint
    # tests can rely on freshly-created complaints staying in the triage queue.
    get_settings().pipeline_inline = False
