"""Zoo eval gate: every scenario must pass, or the pipeline regressed.

The zoo is BugTrail's benchmark corpus (see tests/zoo.py). Each scenario runs
the full deterministic pipeline against a materialized real git repository and
asserts the outcome: the correct root cause ranks in the top N, or low
confidence is reported honestly.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.zoo import SCENARIOS, run_scenario


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_zoo_scenario(scenario, tmp_path: Path):
    result = run_scenario(scenario, tmp_path / "repo")
    assert result.passed, result.detail
