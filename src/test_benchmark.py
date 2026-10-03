import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from benchmark import (
    BenchmarkRow, format_rows, heuristic_quality, load_conversations,
    main, recall_points, run_agent_benchmark,
)
from config import LabConfig


def test_scoring_partial_match_unicode_and_quality_bounds():
    assert recall_points("không có thông tin", ["Linh", "Huế"]) == 0
    assert recall_points("Linh", ["Linh", "Huế"]) == 0.5
    assert recall_points("LINH ở Huế", ["Linh", "Huế"]) == 1
    assert recall_points("Hue\u0302\u0301", ["Huế"]) == 1
    assert recall_points("anything", []) == 0
    assert heuristic_quality("Linh", ["Linh", "Huế"]) == 0.5
    assert heuristic_quality("Linh " + "word " * 240, ["Linh"]) < 1
    assert heuristic_quality("", ["Linh"]) == 0


def test_loader_rejects_bad_input_and_does_not_modify_file(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps([{
        "id": "one", "user_id": "user", "turns": ["hello"],
        "recall_questions": [{"question": "name?", "expected_contains": ["Linh"]}],
    }]), encoding="utf-8")
    before = path.read_bytes()
    assert load_conversations(path)[0]["id"] == "one"
    assert path.read_bytes() == before
    path.write_text('[{"id": "one"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="user_id"):
        load_conversations(path)


def test_fair_turn_order_fresh_recall_costs_and_unique_user_growth(tmp_path):
    config = replace(LabConfig(), state_dir=tmp_path)
    conversations = [
        {"id": "one", "user_id": "user", "turns": ["Mình tên là Linh. Mình ở Huế."],
         "recall_questions": [{"question": "Mình tên gì?", "expected_contains": ["Linh"]}]},
        {"id": "two", "user_id": "user", "turns": ["Mình đang ở Đà Nẵng."],
         "recall_questions": [{"question": "Mình đang ở đâu?", "expected_contains": ["Đà Nẵng"]}]},
    ]
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    traces = []
    for name, agent in [("Baseline", baseline), ("Advanced", advanced)]:
        trace = []
        actual_reply = agent.reply
        def record(user, thread, message):
            trace.append((user, thread, message))
            return actual_reply(user, thread, message)
        with patch.object(agent, "reply", side_effect=record):
            row = run_agent_benchmark(name, agent, conversations, config)
        traces.append(trace)
        threads = {thread for _, thread, _ in trace}
        assert row.agent_tokens_only == sum(agent.token_usage(thread) for thread in threads)
        assert row.prompt_tokens_processed == sum(agent.prompt_token_usage(thread) for thread in threads)
        assert row.recall_score == (1 if name == "Advanced" else 0)
        assert row.memory_growth_bytes == (advanced.memory_file_size("user") if name == "Advanced" else 0)
    assert traces[0] == traces[1]
    assert traces[0][0][1] != traces[0][1][1]
    assert traces[0][2][1] != traces[0][3][1]


def test_cli_prints_two_complete_tables_and_repeated_run_is_identical(tmp_path, capsys):
    config = replace(LabConfig(), state_dir=tmp_path)
    # Dirty profiles outside benchmark-runs must not contaminate the run.
    dirty = AdvancedAgent(config, force_offline=True)
    dirty.profile_store.upsert_fact("dungct", "name", "WrongName")
    with patch("benchmark.load_config", return_value=config):
        main()
        first = capsys.readouterr().out
        main()
        second = capsys.readouterr().out
    assert first == second
    assert first.count("## Standard Benchmark") == 1
    assert first.count("## Long-Context Stress Benchmark") == 1
    assert first.count("| Baseline |") == first.count("| Advanced |") == 2
    assert first.count("Prompt tokens processed") == 2
    assert len(list((tmp_path / "benchmark-runs").glob("run-*"))) == 2
    assert dirty.profile_store.facts("dungct")["name"] == "WrongName"


def test_formatter_keeps_all_six_metric_columns():
    table = format_rows([BenchmarkRow("Baseline", 1, 2, 0.5, 0.75, 3, 4)])
    assert "| Baseline | 1 | 2 | 50.0% | 75.0% | 3 | 4 |" in table
