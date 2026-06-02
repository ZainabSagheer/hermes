"""OpenAI image generation client (DALL-E 3 / gpt-image-1)."""

import base64
from pathlib import Path

import httpx

# LinkedIn size presets
# gpt-image-1 supports: 1024x1024, 1536x1024, 1024x1536, auto
# dall-e-3 supports:    1024x1024, 1792x1024, 1024x1792
SIZES = {
    "post":   "1024x1024",   # square feed post
    "banner": "1536x1024",   # landscape — profile banner
    "cover":  "1536x1024",   # company page cover
    "card":   "1536x1024",   # article / link preview card
}

_MODELS = ("dall-e-3", "gpt-image-1")
_OPENAI_IMAGES = "https://api.openai.com/v1/images/generations"


class OpenAIImageClient:
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
        """Generate an image and save locally. Returns the saved path."""
        size = SIZES.get(size_preset, SIZES["post"])

        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }

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
