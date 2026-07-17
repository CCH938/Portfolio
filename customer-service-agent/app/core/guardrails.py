"""Safety guardrails: input/output filtering."""

from __future__ import annotations
from app.config import get_settings

settings = get_settings()

# ── Input patterns ──
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "forget your prompt",
    "you are now",
    "act as",
    "system prompt",
    "<|im_start|>",
    "<|im_end|>",
]

SENSITIVE_KEYWORDS = [
    "hack", "exploit", "malware", "phishing",
]

JAILBREAK_PATTERNS = [
    "DAN", "do anything now",
    "jailbreak",
    "developer mode",
]


class Guardrails:
    """Input and output safety filters."""

    @staticmethod
    async def input_filter(message: str) -> tuple[bool, str | None]:
        """Filter user input. Returns (blocked, reason)."""
        if not settings.enable_input_filter:
            return False, None

        msg_lower = message.lower()

        # Check injection
        for pattern in INJECTION_PATTERNS:
            if pattern in msg_lower:
                return True, "检测到不安全的输入模式，请重新表述您的问题。"

        # Check jailbreak
        for pattern in JAILBREAK_PATTERNS:
            if pattern in msg_lower:
                return True, "无法处理该请求。"

        return False, None

    @staticmethod
    async def output_filter(response: str) -> tuple[bool, str | None]:
        """Filter assistant output. Returns (modified, replacement)."""
        if not settings.enable_output_filter:
            return False, None

        # Check for hallucination markers (overly confident made-up info)
        if "根据我的内部知识" in response and "知识库中未找到" not in response:
            return True, response.replace("根据我的内部知识", "根据目前已知信息")

        # Check for PII leak patterns (simplified)
        import re
        # Mask potential phone numbers
        masked = re.sub(r'\b1[3-9]\d{9}\b', '[手机号]', response)
        # Mask potential ID numbers
        masked = re.sub(r'\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b', '[身份证号]', masked)

        if masked != response:
            return True, masked

        return False, None
