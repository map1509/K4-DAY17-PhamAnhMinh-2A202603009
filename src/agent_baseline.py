from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Full history per thread, with no persistent or compact memory."""

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}

        self.langchain_agent = None if force_offline else self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return response and per-turn estimated output/prompt tokens.

        user_id deliberately does not select history or provide profile facts.
        Callers must use a distinct thread_id for each independent conversation.
        """
        if self.langchain_agent is None:
            return self._reply_offline(thread_id, message)
        session = self.sessions.setdefault(thread_id, SessionState())
        messages = session.messages + [{"role": "user", "content": message}]
        result = self.langchain_agent.invoke(messages)
        content = result.content
        if isinstance(content, str):
            response = content
        else:
            response = "\n".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in content
            )
        # Commit history only after a successful live response.
        session.messages = [dict(turn) for turn in messages]
        return self._record_response(session, response)

    def token_usage(self, thread_id: str) -> int:
        session = self.sessions.get(thread_id)
        return session.token_usage if session else 0

    def prompt_token_usage(self, thread_id: str) -> int:
        session = self.sessions.get(thread_id)
        return session.prompt_tokens_processed if session else 0

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Reconstruct facts solely from user turns in this thread."""
        session = self.sessions.setdefault(thread_id, SessionState())
        session.messages.append({"role": "user", "content": message})
        facts: dict[str, str] = {}
        for turn in session.messages:
            if turn["role"] == "user":
                facts.update(extract_profile_updates(turn["content"]))
        response = self._offline_response(message, facts)
        return self._record_response(session, response)

    @staticmethod
    def _offline_response(message: str, facts: dict[str, str]) -> str:
        lower = message.lower()
        recall = "?" in message or bool(re.search(r"nhắc lại|nhớ lại|tóm tắt|mô tả", lower))
        if not recall:
            return "Mình đã nhận thông tin và sẽ dùng trong thread này."
        fields = {
            "name": (r"tên|là ai|biết.*không", "Tên"),
            "location": (r"ở đâu|nơi ở|đang ở|còn ở", "Nơi ở"),
            "profession": (r"nghề|công việc", "Nghề nghiệp"),
            "favorite_drink": (r"đồ uống|uống", "Đồ uống yêu thích"),
            "favorite_food": (r"món ăn", "Món ăn yêu thích"),
            "pet": (r"nuôi|thú cưng|con gì", "Thú cưng"),
            "response_style": (r"style|kiểu trả lời|trả lời.*thế nào", "Phong cách trả lời"),
            "interests": (r"quan tâm|sở thích|kỹ thuật chính", "Mối quan tâm"),
        }
        requested = [key for key, (pattern, _) in fields.items() if re.search(pattern, lower)]
        if not requested and re.search(r"tóm tắt|mô tả.*mình", lower):
            requested = list(fields)
        if not requested:
            return "Mình đã nhận câu hỏi; chế độ offline chỉ hỗ trợ nhắc lại thông tin trong thread."
        if not any(key in facts for key in requested):
            return "Mình chưa có thông tin này trong thread hiện tại."
        return "\n".join(
            f"- {fields[key][1]}: {facts.get(key, 'chưa có thông tin trong thread này')}."
            for key in requested
        )

    @staticmethod
    def _record_response(session: SessionState, response: str) -> dict[str, Any]:
        # Count the whole prompt on EVERY turn, before adding the new response.
        prompt_tokens = sum(estimate_tokens(turn["content"]) for turn in session.messages)
        agent_tokens = estimate_tokens(response)
        session.prompt_tokens_processed += prompt_tokens
        session.token_usage += agent_tokens
        session.messages.append({"role": "assistant", "content": response})
        return {"response": response, "agent_tokens": agent_tokens, "prompt_tokens": prompt_tokens}

    def _maybe_build_langchain_agent(self):
        """Optional stateless chat model; all thread history remains here.

        Missing credentials or integration packages keep the agent offline.
        Ollama and custom endpoints can run without a provider API key.
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
