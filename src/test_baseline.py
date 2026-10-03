from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import UserProfileStore, estimate_tokens


def config_for(tmp_path):
    return replace(LabConfig(), state_dir=tmp_path)


def test_remembers_in_thread_forgets_new_thread_and_ignores_profile(tmp_path):
    store = UserProfileStore(tmp_path / "profiles")
    store.upsert_fact("same_user", "name", "SecretProfileName")
    before = store.read_text("same_user")
    agent = BaselineAgent(config_for(tmp_path), force_offline=True)
    agent.reply("same_user", "first", "Mình tên là Linh.")
    assert "Linh" in agent.reply("same_user", "first", "Mình tên gì?")["response"]
    fresh = agent.reply("same_user", "second", "Mình tên gì?")["response"]
    assert "Linh" not in fresh and "SecretProfileName" not in fresh
    assert "chưa có thông tin" in fresh
    agent.reply("same_user", "second", "Mình tên là Mai.")
    assert "Mai" in agent.reply("same_user", "second", "Mình tên gì?")["response"]
    assert "Linh" in agent.reply("same_user", "first", "Mình tên gì?")["response"]
    assert store.read_text("same_user") == before
    assert agent.compaction_count("first") == agent.compaction_count("second") == 0


def test_counters_accumulate_full_history_each_turn(tmp_path):
    agent = BaselineAgent(config_for(tmp_path), force_offline=True)
    history = []
    expected_prompt = expected_output = 0
    for message in ["Mình tên là Linh.", "Mình ở Huế.", "Mình tên gì và đang ở đâu?"]:
        history.append(message)
        expected_turn_prompt = sum(estimate_tokens(text) for text in history)
        result = agent.reply("user", "thread", message)
        assert result["prompt_tokens"] == expected_turn_prompt
        assert result["agent_tokens"] == estimate_tokens(result["response"])
        expected_prompt += expected_turn_prompt
        expected_output += result["agent_tokens"]
        history.append(result["response"])
        assert agent.prompt_token_usage("thread") == expected_prompt
        assert agent.token_usage("thread") == expected_output
    assert len(agent.sessions["thread"].messages) == 6
    assert agent.prompt_token_usage("absent") == agent.token_usage("absent") == 0
    assert "absent" not in agent.sessions


def test_offline_is_deterministic_and_does_not_build_sdk(tmp_path):
    with patch("agent_baseline.build_chat_model", side_effect=AssertionError("must not build")):
        a = BaselineAgent(config_for(tmp_path), force_offline=True)
        b = BaselineAgent(config_for(tmp_path), force_offline=True)
    for text in ["Mình tên là Linh.", "Mình đang ở Huế.", "Mình đang ở Đà Nẵng.", "Mình tên gì và đang ở đâu?"]:
        assert a.reply("user", "thread", text) == b.reply("user", "thread", text)
    response = a.sessions["thread"].messages[-1]["content"]
    assert "Đà Nẵng" in response and "Huế" not in response


def test_live_route_sends_only_selected_thread_and_accounts_tokens(tmp_path):
    agent = BaselineAgent(config_for(tmp_path), force_offline=True)
    live = Mock()
    live.invoke.return_value = SimpleNamespace(content="Live response")
    agent.langchain_agent = live
    first = agent.reply("user", "first", "Secret first thread")
    second = agent.reply("user", "second", "New thread")
    assert live.invoke.call_args.args[0] == [{"role": "user", "content": "New thread"}]
    assert first["prompt_tokens"] == estimate_tokens("Secret first thread")
    assert second["prompt_tokens"] == estimate_tokens("New thread")
    assert agent.token_usage("second") == estimate_tokens("Live response")
