import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import estimate_tokens


def config_for(tmp_path, threshold=2000):
    return replace(LabConfig(), state_dir=tmp_path, compact_threshold_tokens=threshold)


def test_recall_survives_new_thread_and_new_agent(tmp_path):
    config = config_for(tmp_path)
    agent = AdvancedAgent(config, force_offline=True)
    agent.reply("user", "first", "Mình tên là Linh. Mình ở Huế và đang làm MLOps engineer.")
    assert agent.memory_file_size("user") > 0
    before = agent.profile_store.read_text("user")
    answer = agent.reply("user", "new", "Mình tên gì và hiện tại mình làm nghề gì?")["response"]
    assert "Linh" in answer and "MLOps engineer" in answer
    restarted = AdvancedAgent(config, force_offline=True)
    assert "Linh" in restarted.reply("user", "restart", "Mình tên gì?")["response"]
    assert restarted.profile_store.read_text("user") == before
    assert "Linh" not in agent.reply("other", "other_thread", "Mình tên gì?")["response"]
    assert agent.memory_file_size("other") == 0
    with pytest.raises(ValueError):
        agent.reply("other", "first", "Mình tên là Wrong.")
    assert agent.memory_file_size("other") == 0


def test_correction_replaces_disk_fact_and_old_summary(tmp_path):
    agent = AdvancedAgent(config_for(tmp_path, 100), force_offline=True)
    agent.reply("user", "old", "Mình ở Huế. " + "Nội dung dài. " * 100)
    for _ in range(4):
        agent.reply("user", "old", "Nội dung dài. " * 100)
    assert agent.compaction_count("old") > 0
    agent.reply("user", "new", "Mình đang ở Đà Nẵng.")
    answer = agent.reply("user", "old", "Hiện tại mình đang ở đâu?")["response"]
    assert "Đà Nẵng" in answer and "Huế" not in answer
    profile = agent.profile_store.read_text("user")
    assert profile.count("- location:") == 1 and "Huế" not in profile


def test_partial_style_updates_preserve_brevity_and_replace_bullet_count(tmp_path):
    agent = AdvancedAgent(config_for(tmp_path), force_offline=True)
    agent.reply("user", "one", "Mình muốn trả lời ngắn gọn theo 2 bullet.")
    agent.reply("user", "two", "Mình thích cách trình bày có ví dụ thực chiến.")
    agent.reply("user", "three", "Mình muốn trả lời theo 3 bullet.")
    answer = agent.reply("user", "recall", "Nhắc lại style trả lời mình thích.")["response"]
    assert "ngắn gọn" in answer and "ví dụ thực chiến" in answer
    assert "3 bullet" in answer and "2 bullet" not in answer
    assert len(answer.splitlines()) == 3


def test_prompt_counts_profile_summary_recent_before_response(tmp_path):
    agent = AdvancedAgent(config_for(tmp_path, 100), force_offline=True)
    expected_prompt = expected_output = 0
    original_finish = agent._finish_turn
    observed_summary = False
    def check_finish(thread, response, prompt_tokens):
        nonlocal observed_summary
        context = agent.compact_memory.context(thread)
        observed_summary |= bool(context["summary"])
        expected = (
            estimate_tokens(agent.profile_store.read_text("user"))
            + estimate_tokens(context["summary"])
            + sum(estimate_tokens(m["content"]) for m in context["messages"])
        )
        assert prompt_tokens == expected
        return original_finish(thread, response, prompt_tokens)
    with patch.object(agent, "_finish_turn", side_effect=check_finish):
        for text in ["Mình tên là Linh."] + ["Một đoạn dài. " * 100] * 5:
            result = agent.reply("user", "thread", text)
            expected_prompt += result["prompt_tokens"]
            expected_output += estimate_tokens(result["response"])
            assert agent.prompt_token_usage("thread") == expected_prompt
            assert agent.token_usage("thread") == expected_output
    assert observed_summary
    assert agent.token_usage("absent") == agent.prompt_token_usage("absent") == 0


@pytest.mark.parametrize("filename", ["conversations.json", "advanced_long_context.json"])
def test_all_dataset_recall_questions_in_fresh_threads(tmp_path, filename):
    root = Path(__file__).resolve().parent.parent
    conversations = json.loads((root / "data" / filename).read_text(encoding="utf-8"))
    config = config_for(tmp_path)
    advanced = AdvancedAgent(config, force_offline=True)
    baseline = BaselineAgent(config, force_offline=True)
    for conversation in conversations:
        user, thread = conversation["user_id"], conversation["id"]
        for turn in conversation["turns"]:
            advanced.reply(user, thread, turn)
            baseline.reply(user, thread, turn)
        profile_before = advanced.profile_store.read_text(user)
        for i, recall in enumerate(conversation["recall_questions"]):
            answer = advanced.reply(user, f"{thread}-recall-{i}", recall["question"])["response"]
            assert all(fact.lower() in answer.lower() for fact in recall["expected_contains"]), answer
            assert advanced.profile_store.read_text(user) == profile_before
            if filename == "advanced_long_context.json":
                assert len(answer.splitlines()) == 3 and all(line.startswith("- ") for line in answer.splitlines())
        assert advanced.memory_file_size(user) > 0
    if filename == "advanced_long_context.json":
        assert advanced.compaction_count(thread) > 0
        assert advanced.prompt_token_usage(thread) < baseline.prompt_token_usage(thread)


def test_offline_skips_sdk_and_live_uses_three_context_components(tmp_path):
    config = config_for(tmp_path)
    with patch("agent_advanced.build_chat_model", side_effect=AssertionError("must not build")):
        agent = AdvancedAgent(config, force_offline=True)
    agent.profile_store.upsert_fact("user", "name", "Linh")
    agent.compact_memory.state["thread"] = {
        "summary": "Previous discussion", "messages": [], "compactions": 1,
    }
    live = Mock()
    live.invoke.return_value = SimpleNamespace(content="Live answer")
    agent.langchain_agent = live
    result = agent.reply("user", "thread", "Question")
    sent = live.invoke.call_args.args[0]
    assert [m["role"] for m in sent] == ["system", "system", "user"]
    assert "Linh" in sent[0]["content"] and sent[1]["content"] == "Previous discussion"
    assert result["prompt_tokens"] == sum(estimate_tokens(m["content"]) for m in sent)
    assert agent.token_usage("thread") == estimate_tokens("Live answer")
