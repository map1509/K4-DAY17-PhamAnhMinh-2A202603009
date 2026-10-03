from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from agent_baseline import BaselineAgent
from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Persistent user facts plus independent per-thread compact history."""

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}
        self.thread_users: dict[str, str] = {}
        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Route offline or optional live model through the same memory pipeline."""
        if self.langchain_agent is None:
            return self._reply_offline(user_id, thread_id, message)
        self._prepare_turn(user_id, thread_id, message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        context = self.compact_memory.context(thread_id)
        messages = []
        profile = self.profile_store.read_text(user_id)
        if profile:
            messages.append({"role": "system", "content": profile})
        if context["summary"]:
            messages.append({"role": "system", "content": context["summary"]})
        messages.extend(context["messages"])
        result = self.langchain_agent.invoke(messages)
        content = result.content
        response = content if isinstance(content, str) else "\n".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in content
        )
        return self._finish_turn(thread_id, response, prompt_tokens)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _prepare_turn(self, user_id: str, thread_id: str, message: str) -> None:
        # Validate before changing profiles or thread history.
        self.profile_store.path_for(user_id)
        owner = self.thread_users.get(thread_id)
        if owner is not None and owner != user_id:
            raise ValueError("A thread_id cannot be shared between different users.")
        self.thread_users[thread_id] = user_id
        for key, value in extract_profile_updates(message).items():
            if key == "response_style":
                # A new example preference augments rather than erases brevity.
                previous = self.profile_store.facts(user_id).get(key, "")
                parts = [part.strip() for part in previous.split(",") if part.strip()]
                for part in value.split(","):
                    part = part.strip()
                    if "bullet" in part:
                        parts = [old for old in parts if "bullet" not in old]
                    elif "ví dụ" in part:
                        parts = [old for old in parts if "ví dụ" not in old]
                    if part not in parts:
                        parts.append(part)
                value = ", ".join(parts)
            self.profile_store.upsert_fact(user_id, key, value)
        self.compact_memory.append(thread_id, "user", message)

    def _finish_turn(self, thread_id: str, response: str, prompt_tokens: int) -> dict[str, Any]:
        agent_tokens = estimate_tokens(response)
        self.compact_memory.append(thread_id, "assistant", response)
        self.thread_tokens[thread_id] = self.token_usage(thread_id) + agent_tokens
        self.thread_prompt_tokens[thread_id] = self.prompt_token_usage(thread_id) + prompt_tokens
        return {"response": response, "agent_tokens": agent_tokens, "prompt_tokens": prompt_tokens}

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Persist facts, compact the prompt, then generate and account a reply."""
        self._prepare_turn(user_id, thread_id, message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        response = self._offline_response(user_id, thread_id, message)
        return self._finish_turn(thread_id, response, prompt_tokens)

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        context = self.compact_memory.context(thread_id)
        return (
            estimate_tokens(self.profile_store.read_text(user_id))
            + estimate_tokens(context["summary"])
            + sum(estimate_tokens(turn["content"]) for turn in context["messages"])
        )

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Use profile facts even when this is a new thread or agent instance."""
        context = self.compact_memory.context(thread_id)
        facts = dict(re.findall(r"^- ([a-z][a-z0-9_]*): (.+)$", context["summary"], re.MULTILINE))
        for turn in context["messages"]:
            if turn["role"] == "user":
                facts.update(extract_profile_updates(turn["content"]))
        # Disk profile is authoritative if an old summary mentions an obsolete fact.
        facts.update(self.profile_store.facts(user_id))
        response = BaselineAgent._offline_response(message, facts)
        response = response.replace("trong thread hiện tại", "trong memory đã lưu")
        response = response.replace("trong thread này", "trong memory đã lưu")
        if response == "Mình đã nhận thông tin và sẽ dùng trong memory đã lưu.":
            response = "Mình đã nhận thông tin và cập nhật memory."
        style = facts.get("response_style", "")
        if "3 bullet" in style:
            lines = [line.removeprefix("- ").strip() for line in response.splitlines() if line.strip()]
            if len(lines) < 3:
                lines.append(f"Phong cách: {style}.")
            if len(lines) < 3:
                lines.append("Bạn có thể bổ sung hoặc đính chính thông tin.")
            # Pack every requested field into exactly three bullets, without dropping facts.
            groups = [
                lines[i * len(lines) // 3:(i + 1) * len(lines) // 3]
                for i in range(3)
            ]
            response = "\n".join("- " + " ".join(group) for group in groups)
        return response

    def _maybe_build_langchain_agent(self):
        """Optional chat-model path; profile and compaction are managed here.

        LangGraph checkpointers/tools/middleware remain a separate extension.
        """
        model = self.config.model
        if model.provider not in {"ollama", "custom"} and not model.api_key:
            return None
        if model.provider == "custom" and not model.base_url:
            return None
        try:
            return build_chat_model(model)
        except ImportError:
            return None
