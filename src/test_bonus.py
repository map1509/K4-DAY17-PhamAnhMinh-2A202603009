from dataclasses import replace

import pytest

from agent_advanced import AdvancedAgent
from benchmark import load_conversations, run_agent_benchmark
from bonus_benchmark import FirstFactWinsStore
from config import LabConfig


def test_conflict_handling_improves_stress_recall_against_first_fact_wins(tmp_path):
    config = LabConfig()
    conversations = load_conversations(config.data_dir / "advanced_long_context.json")
    rows = []
    for enabled in (False, True):
        suite_config = replace(config, state_dir=tmp_path / ("on" if enabled else "off"))
        agent = AdvancedAgent(suite_config, force_offline=True)
        if not enabled:
            agent.profile_store = FirstFactWinsStore(suite_config.state_dir / "profiles")
        rows.append(run_agent_benchmark(str(enabled), agent, conversations, suite_config))
        profile = agent.profile_store.read_text("dungct_stress")
        assert profile.count("- location:") == 1
        assert agent.profile_store.facts("dungct_stress")["location"] == ("Đà Nẵng" if enabled else "Huế")
    off, on = rows
    assert off.recall_score == pytest.approx(2 / 3)
    assert on.recall_score == 1
    assert on.response_quality > off.response_quality
    assert on.compactions == off.compactions == 1
