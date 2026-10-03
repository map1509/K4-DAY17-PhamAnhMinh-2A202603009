from __future__ import annotations

import json
import tempfile
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig, load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read the fixed dataset and validate the shape before evaluating."""
    conversations = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(conversations, list):
        raise ValueError(f"{path}: dataset must be a list.")
    ids = set()
    for conversation in conversations:
        if not isinstance(conversation, dict):
            raise ValueError(f"{path}: each conversation must be an object.")
        for key in ("id", "user_id"):
            if not isinstance(conversation.get(key), str) or not conversation[key]:
                raise ValueError(f"{path}: {key} must be a non-empty string.")
        if conversation["id"] in ids:
            raise ValueError(f"{path}: duplicate conversation id {conversation['id']!r}.")
        ids.add(conversation["id"])
        turns = conversation.get("turns")
        if not isinstance(turns, list) or not all(isinstance(turn, str) for turn in turns):
            raise ValueError(f"{path}: turns must be a list of strings.")
        questions = conversation.get("recall_questions")
        if not isinstance(questions, list):
            raise ValueError(f"{path}: recall_questions must be a list.")
        for recall in questions:
            if not isinstance(recall, dict) or not isinstance(recall.get("question"), str):
                raise ValueError(f"{path}: recall question must contain a string question.")
            expected = recall.get("expected_contains")
            if not isinstance(expected, list) or not expected or not all(isinstance(value, str) and value.strip() for value in expected):
                raise ValueError(f"{path}: expected_contains must be a non-empty list of non-empty strings.")
    return conversations


def _fact_coverage(answer: str, expected: list[str]) -> float:
    if not expected:
        return 0.0
    normalized = unicodedata.normalize("NFC", answer).casefold()
    return sum(unicodedata.normalize("NFC", value).casefold() in normalized for value in expected) / len(expected)


def recall_points(answer: str, expected: list[str]) -> float:
    """0 for no match, 0.5 for some facts, 1 for every expected fact."""
    coverage = _fact_coverage(answer, expected)
    return 1.0 if coverage == 1.0 else 0.5 if coverage > 0 else 0.0


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Fact coverage times brevity, in [0, 1]; not an LLM quality judgment."""
    coverage = _fact_coverage(answer, expected)
    brevity = min(1.0, 120 / max(1, len(answer.split())))
    return coverage * brevity


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config: LabConfig) -> BenchmarkRow:
    """Evaluate all learning and recall turns, including their token costs.

    A conversation's recall questions share one fresh recall thread. Recall is
    evaluated immediately after that conversation, before future corrections.
    Memory growth is the final size delta per unique user, not repeated sizes.
    """
    users = {conversation["user_id"] for conversation in conversations}
    memory_size = getattr(agent, "memory_file_size", lambda user_id: 0)
    initial_memory = sum(memory_size(user) for user in users)
    threads = {
        f"benchmark:{kind}:{conversation['id']}"
        for conversation in conversations for kind in ("conversation", "recall")
    }
    initial_output = sum(agent.token_usage(thread) for thread in threads)
    initial_prompt = sum(agent.prompt_token_usage(thread) for thread in threads)
    initial_compactions = sum(agent.compaction_count(thread) for thread in threads)
    recall_scores, quality_scores = [], []
    for conversation in conversations:
        user_id = conversation["user_id"]
        thread_id = f"benchmark:conversation:{conversation['id']}"
        recall_thread_id = f"benchmark:recall:{conversation['id']}"
        for turn in conversation["turns"]:
            agent.reply(user_id, thread_id, turn)
        for recall in conversation["recall_questions"]:
            answer = agent.reply(user_id, recall_thread_id, recall["question"])["response"]
            recall_scores.append(recall_points(answer, recall["expected_contains"]))
            quality_scores.append(heuristic_quality(answer, recall["expected_contains"]))
    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=sum(agent.token_usage(thread) for thread in threads) - initial_output,
        prompt_tokens_processed=sum(agent.prompt_token_usage(thread) for thread in threads) - initial_prompt,
        recall_score=sum(recall_scores) / len(recall_scores) if recall_scores else 0.0,
        response_quality=sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
        memory_growth_bytes=sum(memory_size(user) for user in users) - initial_memory,
        compactions=sum(agent.compaction_count(thread) for thread in threads) - initial_compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Render agent label plus all six required metrics without dependencies."""
    headers = [
        "Agent", "Agent tokens only", "Prompt tokens processed",
        "Cross-session recall", "Response quality", "Memory growth (bytes)", "Compactions",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] + ["---:"] * 6) + " |"]
    for row in rows:
        cells = [
            row.agent_name.replace("|", r"\|").replace("\n", " "),
            str(row.agent_tokens_only), str(row.prompt_tokens_processed),
            f"{row.recall_score:.1%}", f"{row.response_quality:.1%}",
            str(row.memory_growth_bytes), str(row.compactions),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    """Run reproducible offline suites with fresh, retained state per run."""
    config = load_config(Path(__file__).resolve().parent.parent)
    suites = [
        ("Standard Benchmark", "conversations.json", "standard"),
        ("Long-Context Stress Benchmark", "advanced_long_context.json", "stress"),
    ]
    # Load both datasets before creating agents, so input errors fail early.
    datasets = [(title, load_conversations(config.data_dir / filename), slug) for title, filename, slug in suites]
    runs_dir = config.state_dir / "benchmark-runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=runs_dir))
    for title, conversations, slug in datasets:
        suite_config = replace(config, state_dir=run_dir / slug)
        rows = [
            run_agent_benchmark("Baseline", BaselineAgent(suite_config, force_offline=True), conversations, suite_config),
            run_agent_benchmark("Advanced", AdvancedAgent(suite_config, force_offline=True), conversations, suite_config),
        ]
        print(f"## {title}\n")
        print(format_rows(rows))
        print()


if __name__ == "__main__":
    main()
