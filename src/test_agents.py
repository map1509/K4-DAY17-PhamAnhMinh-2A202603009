from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import CompactMemoryManager, UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Use only temporary paths and explicit keyless model settings.

    Construct directly instead of load_config(), avoiding .env and repo state.
    Agents in these tests always use force_offline=True.
    """
    return LabConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        compact_threshold_tokens=300,
        compact_keep_messages=4,
        model=ProviderConfig("openai", "offline-test", 0.0),
        judge_model=ProviderConfig("openai", "offline-test", 0.0),
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify actual UTF-8 content and a single replacement on disk."""
    config = make_config(tmp_path)
    store = UserProfileStore(config.state_dir / "profiles")
    assert store.read_text("user") == ""
    assert store.file_size("user") == 0
    original = "# User\n- name: Linh\n- location: Huế\n"
    path = store.write_text("user", original)
    assert path.is_relative_to(tmp_path)
    assert path.is_file() and path.read_text(encoding="utf-8") == original
    assert store.read_text("user") == original
    assert store.edit_text("user", "- location: Huế", "- location: Đà Nẵng")
    expected = original.replace("Huế", "Đà Nẵng", 1)
    assert store.read_text("user") == expected
    assert UserProfileStore(store.root_dir).read_text("user") == expected
    # Windows text writes may use CRLF; the metric must reflect disk bytes.
    assert store.file_size("user") == len(path.read_bytes()) > 0
    assert not store.edit_text("user", "missing", "new")
    assert store.read_text("user") == expected


def test_compact_trigger(tmp_path: Path) -> None:
    """A long thread produces a summary while preserving recent messages."""
    config = make_config(tmp_path)
    memory = CompactMemoryManager(config.compact_threshold_tokens, config.compact_keep_messages)
    turns = [f"Lượt {i}. " + "Đây là nội dung hội thoại dài. " * 50 for i in range(12)]
    for turn in turns:
        memory.append("long", "user", turn)
    assert memory.compaction_count("long") > 0
    context = memory.context("long")
    assert context["summary"]
    assert [message["content"] for message in context["messages"]] == turns[-config.compact_keep_messages:]
    assert memory.compaction_count("new") == 0


def test_cross_session_recall(tmp_path: Path) -> None:
    """Same user, new thread: only the persistent agent remembers."""
    config = make_config(tmp_path)
    advanced = AdvancedAgent(config, force_offline=True)
    baseline = BaselineAgent(config, force_offline=True)
    fact = "Mình tên là Linh. Mình ở Huế và đang làm MLOps engineer."
    question = "Mình tên gì và hiện tại mình làm nghề gì?"
    for agent in (advanced, baseline):
        agent.reply("same-user", "first", fact)
        same_thread = agent.reply("same-user", "first", question)["response"]
        assert "Linh" in same_thread and "MLOps engineer" in same_thread
    advanced_answer = advanced.reply("same-user", "second", question)["response"]
    baseline_answer = baseline.reply("same-user", "second", question)["response"]
    assert "Linh" in advanced_answer and "MLOps engineer" in advanced_answer
    assert "Linh" not in baseline_answer and "MLOps engineer" not in baseline_answer
    assert "chưa có thông tin" in baseline_answer
    assert advanced.memory_file_size("same-user") > 0
    profile = advanced.profile_store.path_for("same-user")
    assert "Linh" in profile.read_text(encoding="utf-8")
    # Reinstantiation proves recall comes from disk, not another in-memory cache.
    restarted = AdvancedAgent(config, force_offline=True)
    assert "Linh" in restarted.reply("same-user", "third", "Mình tên gì?")["response"]


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Under identical long input, compaction outweighs profile overhead."""
    config = make_config(tmp_path)
    advanced = AdvancedAgent(config, force_offline=True)
    baseline = BaselineAgent(config, force_offline=True)
    turns = ["Mình tên là Linh. Mình muốn trả lời ngắn gọn."] + [
        f"Chủ đề {i}. " + "Hệ thống cần giữ ngữ cảnh gần và tóm tắt phần cũ. " * 80
        for i in range(20)
    ]
    advanced_prompt = baseline_prompt = 0
    for turn in turns:
        advanced_prompt += advanced.reply("user", "long", turn)["prompt_tokens"]
        baseline_prompt += baseline.reply("user", "long", turn)["prompt_tokens"]
    assert advanced_prompt == advanced.prompt_token_usage("long") > 0
    assert baseline_prompt == baseline.prompt_token_usage("long") > 0
    assert advanced.compaction_count("long") > 0
    assert baseline.compaction_count("long") == 0
    assert advanced_prompt < baseline_prompt
    assert advanced.memory_file_size("user") > 0
    assert "Linh" in advanced.reply("user", "recall", "Mình tên gì?")["response"]
