from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy", reason="sqlalchemy not in core requirements")

from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from runtime.core import FlowCoreRuntime  # noqa: E402


@pytest.mark.asyncio
async def test_runtime_registers_canonical_observer_ingestion_job(tmp_path: Path):
    script = tmp_path / "scripts" / "ingest_observers.py"
    script.parent.mkdir()
    script.write_text("print('ingest')\n")

    with patch.dict("os.environ", {"FLOWCORE_OBSERVER_SCHEDULE": "*/15 * * * *"}, clear=False):
        with patch("runtime.job_scheduler.JobScheduler.add_job", return_value=True) as add_job:
            runtime = FlowCoreRuntime(tmp_path)
            await runtime.start()

    add_job.assert_called_once_with(
        "observer_ingest",
        str(script),
        "*/15 * * * *",
    )
    assert runtime.is_running is True
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_can_disable_observer_ingestion_registration(tmp_path: Path):
    with patch.dict("os.environ", {"FLOWCORE_AUTO_INGEST": "0"}, clear=False):
        with patch("runtime.job_scheduler.JobScheduler.add_job") as add_job:
            runtime = FlowCoreRuntime(tmp_path)
            await runtime.start()

    add_job.assert_not_called()
    await runtime.stop()
