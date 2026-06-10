"""GPT-4o content engine for Bitsol Marketing LinkedIn posts."""

import json
import time
from datetime import date, datetime
from pathlib import Path

import httpx

BRAND = {
    "name": "Bitsol Marketing",
    "tagline": "Performance-driven digital marketing agency",
    "services": [
        "SEO & Search Marketing",
        "Social Media Marketing",
        "Content Marketing & Copywriting",
        "Pay-Per-Click (PPC) Advertising",
        "Brand Strategy & Identity",
        "Email Marketing & Automation",
        "Influencer Marketing",
        "Analytics & Performance Reporting",
    ],
    "usp": "We don't just run campaigns — we engineer growth systems that compound over time.",
    "cta": "DM us or visit bitsol.marketing to see how we do it.",
}

# 5 content pillars — one per post per day
PILLARS = [
    {
        "id": "tip",
        "name": "Marketing Tip",
        "prompt": (
            "Write a LinkedIn post sharing ONE powerful, immediately actionable marketing tip. "
            "Be hyper-specific and tactical — give a real technique, not generic advice. "
            "Include a concrete example, benchmark, or stat if possible."
        ),
        "image_prompt": (
            "professional LinkedIn post graphic for Bitsol Marketing, bold white typography on dark navy background, "
            "orange gold accent color, marketing tip theme, clean minimalist layout, no stock photos, "
            "modern sans-serif font, subtle geometric shapes"
        ),
    },
    {
        "id": "insight",
        "name": "Industry Insight",
        "prompt": (
            "Write a LinkedIn post revealing a surprising marketing statistic, trend, or industry shift "
            "that most business owners don't know yet. Make it feel like insider knowledge. "
            "Break down what it means for their business."
        ),
        "image_prompt": (
            "infographic style LinkedIn post for Bitsol Marketing, marketing data visualization, "
            "clean blue and white professional design, bold percentage or stat as focal point, "
            "modern chart aesthetic, no clipart, crisp typography"
        ),
    },
    {
        "id": "case_study",
        "name": "Success Story",
        "prompt": (
            "Write a LinkedIn post in problem > strategy > result format. "
            "Tell a realistic marketing success story (can be composite/illustrative). "
            "Include specific numbers: traffic %, lead growth, ROAS, or revenue impact. "
            "Make the reader think 'I want those results.'"
        ),
        "image_prompt": (
            "before and after results graphic for Bitsol Marketing LinkedIn post, "
            "success metrics dashboard style, green accent on dark background, "
            "clean data visualization with upward trend, professional agency aesthetic"
        ),
    },
    {
        "id": "strategy",
        "name": "Strategy Framework",
        "prompt": (
            "Write a LinkedIn post breaking down one underrated or misunderstood marketing strategy. "
            "Give it a clear structure — a 3-step framework, a checklist, or a numbered breakdown. "
            "Make it feel like a mini-masterclass the reader can screenshot and save."
        ),
        "image_prompt": (
            "marketing strategy framework graphic for Bitsol Marketing, LinkedIn post format, "
            "numbered steps or process flow, professional blue tones with white text, "
            "clean modern layout, no stock photos, agency brand feel"
        ),
    },
    {
        "id": "engagement",
        "name": "Hot Take / Debate",
        "prompt": (
            "Write a LinkedIn post with a bold, slightly controversial marketing opinion that sparks genuine debate. "
            "Take a clear stance. Challenge a common belief marketers hold. "
            "End with a direct question that makes people HAVE to comment. "
            "Aim for 'I disagree' OR 'Finally someone said it' reactions."
        ),
        "image_prompt": (
            "bold opinion graphic for Bitsol Marketing LinkedIn post, high contrast design, "
            "large provocative typography, vibrant gradient background, thought leadership aesthetic, "
            "no stock photos, eye-catching and scroll-stopping"
        ),
    },
]

SYSTEM_PROMPT = """You are the LinkedIn content strategist for Bitsol Marketing — a performance-driven digital marketing agency known for bold, results-focused content.

Services: {services}
Brand USP: {usp}

Write LinkedIn posts that:
- Open with a SCROLL-STOPPING first line — no greetings, no "I", no clichés
- Use short punchy paragraphs (1-2 sentences max), heavy line breaks — mobile readers only skim
- Place 3-5 emojis naturally mid-sentence, never at the start of a line
- Build momentum toward a sharp CTA or question at the end
- Stay under 1200 characters total
- Close with exactly 4 hashtags: #BitsolMarketing plus 3 hyper-relevant ones
- Sound like a confident expert, not a content farm robot

BANNED: "In today's digital landscape", "leverage", "synergies", "game-changer",
"revolutionize", "cutting-edge", "dive in", "at the end of the day"

The first sentence must be impossible to scroll past.
""".format(
    services=", ".join(BRAND["services"]),
    usp=BRAND["usp"],
)

_OPENAI_CHAT = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_MESSAGES = "https://api.anthropic.com/v1/messages"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
# Free OpenAI-compatible endpoints — no API key required
_POLLINATIONS_CHAT = "https://text.pollinations.ai/openai"
# Groq free tier — key from console.groq.com (no credit card)
_GROQ_CHAT = "https://api.groq.com/openai/v1/chat/completions"
_LOG_PATH = Path.home() / ".hermes" / "bitsol_posts.json"


class ContentEngine:
    def __init__(
        self,
        api_key: str = "",
        anthropic_key: str | None = None,
        gemini_key: str | None = None,
        groq_key: str | None = None,
    ) -> None:
        self._openai_key = api_key
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )
        self._anthropic_key = anthropic_key
        self._gemini_key = gemini_key
        self._groq_key = groq_key
        self._log = self._load_log()

    def _load_log(self) -> list:
        if _LOG_PATH.exists():
            return json.loads(_LOG_PATH.read_text())
        return []

    def _save_log(self) -> None:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_PATH.write_text(json.dumps(self._log, indent=2, default=str))

    def today_count(self) -> int:
        today = date.today().isoformat()
        return sum(1 for p in self._log if p.get("date") == today)

    def next_pillar(self) -> dict:
        """Return the next unused pillar for today, cycling through all 5."""
        today = date.today().isoformat()
        used_today = [p["pillar"] for p in self._log if p.get("date") == today]
        for pillar in PILLARS:
            if pillar["id"] not in used_today:
                return pillar
        return PILLARS[len(self._log) % len(PILLARS)]

    def _build_user_msg(self, pillar: dict, topic: str | None) -> str:
        today_str = datetime.now().strftime("%B %d, %Y")
        msg = pillar["prompt"]
        if topic:
            msg += f"\n\nSpecific angle to focus on: {topic}"
        msg += f"\n\nDate: {today_str}. Make the content feel current and timely."
        return msg

    def _generate_with_openai(self, user_msg: str) -> str:
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 600,
            "temperature": 0.88,
        }
        for attempt in range(3):
            r = self._http.post(_OPENAI_CHAT, json=payload)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 2 ** attempt * 5))
                print(f"OpenAI rate limited — waiting {wait}s (attempt {attempt + 1}/3)…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        raise RuntimeError("OpenAI rate limit: exhausted 3 retries")

    def _generate_with_claude(self, user_msg: str) -> str:
        if not self._anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set — cannot fall back to Claude")
        print("Falling back to Claude (Anthropic)…")
        r = httpx.post(
            _ANTHROPIC_MESSAGES,
            headers={
                "x-api-key": self._anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 600,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _generate_with_gemini(self, user_msg: str) -> str:
        r = httpx.post(
            _GEMINI_URL,
            params={"key": self._gemini_key},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": user_msg}]}],
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.88},
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _generate_with_groq(self, user_msg: str) -> str:
        r = httpx.post(
            _GROQ_CHAT,
            headers={"Authorization": f"Bearer {self._groq_key}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 600,
                "temperature": 0.88,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _generate_with_pollinations(self, user_msg: str) -> str:
        """Completely free — no API key, OpenAI-compatible proxy."""
        r = httpx.post(
            _POLLINATIONS_CHAT,
            json={
                "model": "openai",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 600,
                "temperature": 0.88,
                "private": True,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def generate_text(self, pillar: dict, topic: str | None = None) -> str:
        user_msg = self._build_user_msg(pillar, topic)
        if self._groq_key:
            print("Using Groq / Llama 3.1 70B (free)…")
            return self._generate_with_groq(user_msg)
        if self._gemini_key:
            print("Using Gemini 2.0 Flash (free)…")
            return self._generate_with_gemini(user_msg)
        if self._openai_key:
            try:
                return self._generate_with_openai(user_msg)
            except RuntimeError:
                if self._anthropic_key:
                    return self._generate_with_claude(user_msg)
                raise
        print("Using Pollinations.ai text (free, no key needed)…")
        return self._generate_with_pollinations(user_msg)

    def log_post(self, pillar_id: str, urn: str, text: str, image: str | None) -> None:
        self._log.append({
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "pillar": pillar_id,
            "urn": urn,
            "preview": text[:120],
            "image": image,
        })
        self._save_log()

    def get_stats(self) -> dict:
        today = date.today().isoformat()
        return {
            "today": sum(1 for p in self._log if p.get("date") == today),
            "total": len(self._log),
            "last_post": self._log[-1] if self._log else None,
        }
