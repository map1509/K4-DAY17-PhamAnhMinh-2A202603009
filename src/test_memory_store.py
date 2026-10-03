"""Unit checks for memory before agent integration is implemented."""
import json
from pathlib import Path

import pytest

from memory_store import (
    CompactMemoryManager, UserProfileStore, estimate_tokens,
    extract_profile_updates, summarize_messages,
)


def test_estimator_is_deterministic_and_monotonic():
    assert estimate_tokens("") == estimate_tokens(" \n ") == 0
    assert estimate_tokens("Tiếng Việt") == estimate_tokens("Tiếng Việt")
    assert estimate_tokens("a" * 100) >= estimate_tokens("a" * 10) > 0


def test_profile_edit_correction_and_bytes(tmp_path):
    store = UserProfileStore(tmp_path)
    assert store.read_text("dungct") == ""
    assert store.file_size("dungct") == 0
    path = store.write_text("dungct", "# User\nHuế Huế\n")
    assert path == tmp_path / "dungct" / "User.md"
    assert store.file_size("dungct") == len(path.read_bytes())
    assert store.edit_text("dungct", "Huế", "Đà Nẵng")
    assert store.read_text("dungct") == "# User\nĐà Nẵng Huế\n"
    assert not store.edit_text("dungct", "absent", "new")
    assert not store.edit_text("dungct", "", "new")
    assert not store.edit_text("dungct", "Huế", "Huế")
    store.upsert_fact("dungct", "location", "Huế")
    store.upsert_fact("dungct", "location", "Đà Nẵng")
    assert store.facts("dungct") == {"location": "Đà Nẵng"}
    assert store.read_text("dungct").count("- location:") == 1
    assert UserProfileStore(tmp_path).facts("dungct")["location"] == "Đà Nẵng"


@pytest.mark.parametrize("user_id", ["../../outside", r"..\outside", "CON", "a/b", "a?b", "."])
def test_profile_paths_remain_inside_root(tmp_path, user_id):
    store = UserProfileStore(tmp_path)
    path = store.write_text(user_id, "safe")
    assert path.resolve().is_relative_to(tmp_path.resolve())
    assert store.path_for("a/b") != store.path_for("a?b")


def test_extraction_corrections_noise_and_questions():
    assert extract_profile_updates("Mình tên là Linh. Mình ở Huế và đang làm backend engineer.") == {
        "name": "Linh", "location": "Huế", "profession": "backend engineer",
    }
    assert extract_profile_updates("Mình không còn làm backend engineer nữa, giờ chuyển sang MLOps engineer.")["profession"] == "MLOps engineer"
    assert extract_profile_updates("Mình đang ở Huế, nhưng giờ mình đang ở Đà Nẵng.")["location"] == "Đà Nẵng"
    assert extract_profile_updates("Mình đùa rằng hay là chuyển sang product manager. Hà Nội chỉ là nơi đi họp.") == {}
    assert extract_profile_updates("Mình tên gì? Hiện tại mình ở đâu? Nhắc lại style trả lời mình thích.") == {}
    pet = extract_profile_updates("Mình nuôi một bé corgi tên Bơ.")
    assert "name" not in pet and pet["pet"] == "corgi tên Bơ"
    assert extract_profile_updates("Nếu mình ở Hà Nội thì sao?") == {}
    assert extract_profile_updates("Mình ở Huế?") == {}
    assert extract_profile_updates("Mình tên là Linh? Mình đang ở Đà Nẵng.") == {"location": "Đà Nẵng"}
    assert extract_profile_updates("Mình thích Python, AI ứng dụng.")["interests"] == "Python, AI"


def test_dataset_final_facts_and_recall_do_not_write():
    root = Path(__file__).resolve().parent.parent
    for file, location, name in [
        ("conversations.json", "Huế", "DũngCT"),
        ("advanced_long_context.json", "Đà Nẵng", "DũngCT Stress"),
    ]:
        facts = {}
        conversations = json.loads((root / "data" / file).read_text(encoding="utf-8"))
        for conversation in conversations:
            for turn in conversation["turns"]:
                facts.update(extract_profile_updates(turn))
            for recall in conversation["recall_questions"]:
                assert extract_profile_updates(recall["question"]) == {}
        assert facts["name"] == name
        assert facts["location"] == location
        assert facts["profession"] == "MLOps engineer"
        if file == "conversations.json":
            assert facts["favorite_food"] == "mì Quảng"
            assert facts["favorite_drink"] == "cà phê sữa đá"
            assert "corgi" in facts["pet"]
        else:
            assert "3 bullet" in facts["response_style"]


def test_repeated_compaction_retains_recent_and_previous_summary():
    manager = CompactMemoryManager(300, 2)
    first = "Mình tên là Linh. " + "Nội dung dài. " * 150
    manager.append("thread", "user", first)
    full_history = [first]
    for i in range(12):
        content = f"Tin mới {i}. " + "Nội dung dài. " * 150
        full_history.append(content)
        manager.append("thread", "user", content)
    context = manager.context("thread")
    assert manager.compaction_count("thread") > 1
    assert [m["content"] for m in context["messages"]] == full_history[-2:]
    assert "Linh" in context["summary"]
    assert estimate_tokens(context["summary"]) <= 150
    compact_tokens = estimate_tokens(context["summary"]) + sum(estimate_tokens(m["content"]) for m in context["messages"])
    assert compact_tokens < sum(estimate_tokens(m) for m in full_history)
    assert manager.context("new") == {"messages": [], "summary": "", "compactions": 0}
    context["messages"].clear()
    assert len(manager.context("thread")["messages"]) == 2


def test_summary_updates_old_fact_and_ignores_assistant_inventions():
    summary = summarize_messages([
        {"role": "system", "content": "- location: Huế\n- name: Linh"},
        {"role": "assistant", "content": "Mình tên là Fake."},
        {"role": "user", "content": "Mình đang ở Đà Nẵng."},
    ])
    assert "Linh" in summary and "Fake" not in summary
    assert "- location: Đà Nẵng" in summary and "- location: Huế" not in summary
