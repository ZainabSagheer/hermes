"""Image generation clients — Pollinations (free) and OpenAI (paid fallback)."""

import base64
import urllib.parse
from pathlib import Path

import httpx

# LinkedIn size presets
SIZES = {
    "post":   (1024, 1024),   # square feed post
    "banner": (1536, 1024),   # landscape — profile banner
    "cover":  (1536, 1024),   # company page cover
    "card":   (1536, 1024),   # article / link preview card
}

# Legacy string map kept for OpenAIImageClient
_SIZES_STR = {k: f"{w}x{h}" for k, (w, h) in SIZES.items()}


class PollinationsImageClient:
    """Completely free image generation via Pollinations.ai (FLUX model). No API key needed."""

    _BASE = "https://image.pollinations.ai/prompt"

    def generate(
        self,
        prompt: str,
        size_preset: str = "post",
        output_path: Path | None = None,
    ) -> Path:
        w, h = SIZES.get(size_preset, SIZES["post"])
        url = (
            f"{self._BASE}/{urllib.parse.quote(prompt)}"
            f"?width={w}&height={h}&model=flux&nologo=true&enhance=true"
        )
        r = httpx.get(url, timeout=120, follow_redirects=True)
        if not r.is_success:
            raise RuntimeError(f"Pollinations error {r.status_code}: {r.text[:200]}")
        if output_path is None:
            slug = prompt[:40].replace(" ", "_").replace("/", "-")
            output_path = Path(f"{slug}_{size_preset}.jpg")
        output_path.write_bytes(r.content)
        return output_path

_MODELS = ("dall-e-3", "gpt-image-1")
_OPENAI_IMAGES = "https://api.openai.com/v1/images/generations"


class OpenAIImageClient:
    """Paid fallback — uses DALL-E 3 / gpt-image-1."""

    def __init__(self, api_key: str, model: str = "gpt-image-1") -> None:
        if model not in _MODELS:
            raise ValueError(f"model must be one of {_MODELS}")
        self._model = model
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120,
        )

    def generate(
        self,
        prompt: str,
        size_preset: str = "post",
        output_path: Path | None = None,
    ) -> Path:
        size = _SIZES_STR.get(size_preset, _SIZES_STR["post"])
        payload: dict = {"model": self._model, "prompt": prompt, "n": 1, "size": size}
        r = self._http.post(_OPENAI_IMAGES, json=payload)
        if not r.is_success:
            raise RuntimeError(f"OpenAI image API {r.status_code}: {r.text}")
        data = r.json()["data"][0]
        if output_path is None:
            slug = prompt[:30].replace(" ", "_").replace("/", "-")
            output_path = Path(f"{slug}_{size_preset}.jpg")
        if "url" in data:
            img = httpx.get(data["url"], timeout=60)
            img.raise_for_status()
            output_path.write_bytes(img.content)
        else:
            output_path.write_bytes(base64.b64decode(data["b64_json"]))
        return output_path
