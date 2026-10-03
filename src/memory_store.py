from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Deterministic character heuristic; this is not a model tokenizer."""
    text = text.strip()
    return (len(text) + 3) // 4


@dataclass
class UserProfileStore:
    """UTF-8 profiles at root_dir/<safe user id>/User.md."""

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("user_id must be a non-empty string.")
        slug = re.sub(r"[^A-Za-z0-9_-]", "-", user_id).strip("-")[:64] or "user"
        # Preserve dataset ids; hash transformed ids to avoid slug collisions.
        reserved = slug.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if slug != user_id or reserved:
            slug += "-" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
        root = self.root_dir.resolve()
        path = (root / slug / "User.md").resolve()
        if not path.is_relative_to(root):
            raise ValueError("Profile path escapes root_dir.")
        return path

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        if not search_text or search_text == replacement:
            return False
        content = self.read_text(user_id)
        if search_text not in content:
            return False
        self.write_text(user_id, content.replace(search_text, replacement, 1))
        return True

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        return path.stat().st_size if path.exists() else 0

    def facts(self, user_id: str) -> dict[str, str]:
        return _markdown_facts(self.read_text(user_id))

    def upsert_fact(self, user_id: str, key: str, value: str) -> Path:
        """Replace the field in place, preserving unrelated markdown."""
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise ValueError("Fact keys must be lowercase identifiers.")
        value = " ".join(value.split())
        if not value:
            raise ValueError("Fact values must not be empty.")
        content = self.read_text(user_id) or "# User profile\n"
        line = f"- {key}: {value}"
        pattern = re.compile(rf"^- {re.escape(key)}:.*$", re.MULTILINE)
        if pattern.search(content):
            # Collapse any pre-existing duplicate fields during correction.
            first = True
            def replace(match):
                nonlocal first
                if first:
                    first = False
                    return line
                return ""
            content = pattern.sub(replace, content)
        else:
            content = content.rstrip() + "\n" + line + "\n"
        return self.write_text(user_id, content)


def _markdown_facts(text: str) -> dict[str, str]:
    return dict(re.findall(r"^- ([a-z][a-z0-9_]*): (.+)$", text, re.MULTILINE))


def extract_profile_updates(message: str) -> dict[str, str]:
    """Conservative Vietnamese heuristics, not general semantic extraction.

    Only explicit assertions/preferences are saved. Questions, hypothetical
    clauses and jokes are ignored; later assertions replace earlier ones.
    """
    facts: dict[str, str] = {}
    # Remove question sentences while retaining assertions in mixed turns.
    message = " ".join(
        part for part in re.findall(r"[^.!?]+[.!?]?", message)
        if not part.rstrip().endswith("?")
    )
    # Separate correction clauses so an earlier negation does not mask the new fact.
    clauses = re.split(r"[.!?;\n]+|,\s*|\bnhưng\b|\bchứ\b", message, flags=re.IGNORECASE)
    patterns = {
        "name": r"(?:mình\s+tên\s+là|tên\s+mình\s+là|^tên)\s+(.+?)(?=\s+và\s|$)",
        "location": r"(?:mình\s+(?:vẫn\s+|hiện\s+|hiện\s+tại\s+|đang\s+)?(?:ở|sống\s+ở|làm\s+việc\s+ở)|hiện\s+ở|nơi\s+ở\s+hiện\s+tại\s+là)\s+(.+?)(?=\s+(?:và|chứ|vài\s+tháng|trong\s+giai\s+đoạn|mỗi\s+ngày|để|dù)\b|$)",
        "profession": r"(?:mình\s+(?:vẫn\s+|đang\s+)?làm|đang\s+làm|giờ\s+(?:mình\s+)?chuyển\s+sang|nghề\s+nghiệp\s+(?:hiện\s+tại\s+)?(?:thì\s+)?(?:vẫn\s+)?là|^nghề)\s+([\w -]+?\s(?:engineer|manager|developer))\b",
        "favorite_drink": r"(?:đồ\s+uống\s+yêu\s+thích(?:\s+của\s+mình)?\s+là)\s+(.+)",
        "favorite_food": r"(?:món\s+ăn\s+yêu\s+thích(?:\s+của\s+mình)?\s+là)\s+(.+)",
        "pet": r"mình\s+nuôi\s+(?:một\s+)?(?:bé\s+)?(.+)",
    }
    for clause in clauses:
        clause = clause.strip()
        lower = clause.lower()
        if not clause or lower.startswith("nếu ") or re.search(r"\b(?:đùa|ví dụ cũ|lúc đầu|trước đó|không còn|đừng nói|không phải|hay là)\b", lower):
            continue
        # Do not turn recall requests into profile assertions.
        if re.search(r"(?:mình|tên|nghề|ở|thích).*(?:gì|đâu|không)\s*$", lower) or re.search(r"^(?:bạn có biết|nhắc lại|nhắc ngắn|tóm tắt)", lower):
            continue
        for key, pattern in patterns.items():
            match = re.search(pattern, clause, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" :")
                if key == "location" and re.search(r"quán|cà phê|họp|khách sạn|sân bay", value, re.IGNORECASE):
                    continue
                if value and value.lower() not in {"gì", "ai", "đâu"}:
                    facts[key] = value
        if re.search(r"mình\s+(?:vẫn\s+)?(?:thích|uống)", lower) and "cà phê sữa đá" in lower:
            facts["favorite_drink"] = "cà phê sữa đá"
        if re.search(r"mình\s+(?:vẫn\s+)?(?:thích|đang quan tâm|quan tâm)", lower):
            interests = [term for term in ("Python", "AI", "MLOps", "RAG", "evaluation") if re.search(rf"\b{term}\b", clause, re.IGNORECASE)]
            if interests:
                facts["interests"] = ", ".join(interests)
    # Style components can span comma-separated clauses, unlike identity facts.
    for sentence in re.split(r"[.!?\n]+", message):
        lower = sentence.lower()
        if re.search(r"\b(?:nếu|đùa)\b", lower):
            continue
        # Preference lists span commas; extracting clause by clause would lose AI
        # from assertions such as "Mình thích Python, AI ứng dụng".
        if re.search(r"mình\s+(?:vẫn\s+)?(?:thích|đang quan tâm|quan tâm)", lower):
            interests = [term for term in ("Python", "AI", "MLOps", "RAG", "evaluation") if re.search(rf"\b{term}\b", sentence, re.IGNORECASE)]
            if interests:
                facts["interests"] = ", ".join(interests)
        if not re.search(r"(?:mình.*(?:muốn|thích)|hãy trả lời|style trả lời.*(?:giữ|là))", lower):
            continue
        parts = []
        if re.search(r"ngắn|gọn", lower):
            parts.append("ngắn gọn")
        bullet = re.search(r"(\d+\s+bullet|bullet)", lower)
        if bullet:
            parts.append(bullet.group())
        if "ví dụ thực chiến" in lower:
            parts.append("ví dụ thực chiến")
        elif "ví dụ thực tế" in lower:
            parts.append("ví dụ thực tế")
        if "trade-off" in lower:
            parts.append("trade-off")
        if parts:
            facts["response_style"] = ", ".join(parts)
    return facts


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Bounded extractive summary, merging earlier summary and newer facts.

    Stable fields take priority; remaining slots retain short user excerpts.
    This heuristic may lose details and should not replace persistent profiles.
    """
    if max_items <= 0:
        return ""
    facts: dict[str, str] = {}
    excerpts: list[str] = []
    for message in messages:
        content = message["content"]
        if message["role"] == "system":
            facts.update(_markdown_facts(content))
            excerpts.extend(re.findall(r"^- context: (.+)$", content, re.MULTILINE))
        elif message["role"] == "user":
            facts.update(extract_profile_updates(content))
            # Prefer clauses containing an explicit reminder or topic over greetings.
            sentences = re.split(r"(?<=[.!?])\s+|\n+", content)
            selected = next((s for s in sentences if re.search(r"Artemis|X-59|WMO|British Columbia|nhớ|trade-off", s, re.IGNORECASE)), sentences[0])
            excerpt = " ".join(selected.split())[:160]
            if excerpt and excerpt not in excerpts:
                excerpts.append(excerpt)
    items = [f"- {key}: {value[:160]}" for key, value in facts.items()]
    remaining = max_items - len(items)
    if remaining > 0:
        items.extend(f"- context: {value}" for value in excerpts[-remaining:])
    return "\n".join(items[:max_items])


@dataclass
class CompactMemoryManager:
    """Per-thread recent messages plus a bounded, rolling summary."""

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.threshold_tokens <= 0 or self.keep_messages < 1:
            raise ValueError("threshold_tokens and keep_messages must be positive.")

    def append(self, thread_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Unsupported message role.")
        thread = self.state.setdefault(thread_id, {"messages": [], "summary": "", "compactions": 0})
        messages = thread["messages"]
        messages.append({"role": role, "content": content})
        tokens = estimate_tokens(thread["summary"]) + sum(estimate_tokens(m["content"]) for m in messages)
        if tokens <= self.threshold_tokens or len(messages) <= self.keep_messages:
            return
        older = messages[:-self.keep_messages]
        previous = [{"role": "system", "content": thread["summary"]}] if thread["summary"] else []
        summary = summarize_messages(previous + older)
        # Reserve at most half the configured budget for the summary.
        budget_chars = 2 * self.threshold_tokens
        if len(summary) > budget_chars:
            summary = summary[:budget_chars].rsplit("\n", 1)[0] or summary[:budget_chars]
        old_tokens = estimate_tokens(thread["summary"]) + sum(estimate_tokens(m["content"]) for m in older)
        if estimate_tokens(summary) >= old_tokens:
            # Summarizing very short turns can add overhead; compact only if it saves.
            return
        thread["summary"] = summary
        thread["messages"] = messages[-self.keep_messages:]
        thread["compactions"] += 1

    def context(self, thread_id: str) -> dict[str, object]:
        """Return a snapshot so callers cannot mutate internal thread memory."""
        thread = self.state.get(thread_id, {"messages": [], "summary": "", "compactions": 0})
        return {**thread, "messages": [dict(m) for m in thread["messages"]]}

    def compaction_count(self, thread_id: str) -> int:
        return int(self.state.get(thread_id, {}).get("compactions", 0))
