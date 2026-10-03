"""Ablate conflict handling only; datasets and compaction settings stay fixed."""
from dataclasses import replace
from pathlib import Path
import tempfile

from agent_advanced import AdvancedAgent
from benchmark import format_rows, load_conversations, run_agent_benchmark
from config import load_config
from memory_store import UserProfileStore


class FirstFactWinsStore(UserProfileStore):
    """Experimental control: keep each field's first value, ignore corrections."""

    def upsert_fact(self, user_id: str, key: str, value: str) -> Path:
        if key in self.facts(user_id):
            return self.path_for(user_id)
        return super().upsert_fact(user_id, key, value)


def main() -> None:
    config = load_config()
    runs = config.state_dir / "bonus-runs"
    runs.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=runs))
    for filename, title, slug in [
        ("conversations.json", "Standard: conflict handling", "standard"),
        ("advanced_long_context.json", "Stress: conflict handling", "stress"),
    ]:
        conversations = load_conversations(config.data_dir / filename)
        rows = []
        for enabled in (False, True):
            suite_config = replace(config, state_dir=run / slug / ("on" if enabled else "off"))
            agent = AdvancedAgent(suite_config, force_offline=True)
            if not enabled:
                agent.profile_store = FirstFactWinsStore(suite_config.state_dir / "profiles")
            rows.append(run_agent_benchmark(
                "Advanced conflict " + ("on" if enabled else "off"),
                agent, conversations, suite_config,
            ))
        print(f"## {title}\n")
        print(format_rows(rows))
        print()


if __name__ == "__main__":
    main()
