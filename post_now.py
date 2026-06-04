"""Entry point called by Windows Task Scheduler — posts one Bitsol Marketing update."""

import argparse
import io
import os
import sys
from pathlib import Path

# Force UTF-8 output so emojis in GPT responses don't crash the Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Make hermas importable when run directly by the scheduler
sys.path.insert(0, str(Path(__file__).parent))

from hermas.content_engine import ContentEngine, PILLARS
from hermas.image_gen import OpenAIImageClient, PollinationsImageClient
from hermas.linkedin import LinkedInClient


def _load_env(key: str) -> str | None:
    # GitHub Actions (and any shell) passes secrets as real env vars — check first
    if val := os.environ.get(key):
        return val
    # Fall back to ~/.hermes/.env for local runs
    env = Path.home() / ".hermes" / ".env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pillar", default=None, help="Content pillar ID")
    parser.add_argument("--topic", default=None, help="Optional topic override")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    gemini_key = _load_env("GEMINI_API_KEY")
    openai_key = _load_env("OPENAI_API_KEY")
    anthropic_key = _load_env("ANTHROPIC_API_KEY")
    linkedin_token = _load_env("LINKEDIN_ACCESS_TOKEN")

    if not gemini_key and not openai_key and not anthropic_key:
        print("ERROR: Set GEMINI_API_KEY (free) or OPENAI_API_KEY / ANTHROPIC_API_KEY")
        sys.exit(1)
    if not linkedin_token and not args.dry_run:
        print("ERROR: LINKEDIN_ACCESS_TOKEN not set in ~/.hermes/.env")
        sys.exit(1)

    engine = ContentEngine(
        api_key=openai_key or "",
        anthropic_key=anthropic_key,
        gemini_key=gemini_key,
    )

    # Select pillar
    if args.pillar:
        selected = next((p for p in PILLARS if p["id"] == args.pillar), None)
        if not selected:
            print(f"ERROR: Unknown pillar '{args.pillar}'")
            sys.exit(1)
    else:
        selected = engine.next_pillar()

    print(f"[{selected['name']}] Generating post…")
    text = engine.generate_text(selected, topic=args.topic)
    print(f"Copy ({len(text)} chars):\n{text}\n")

    print("Generating image…")
    if openai_key:
        img_client = OpenAIImageClient(openai_key)
    else:
        img_client = PollinationsImageClient()
        print("  → using Pollinations.ai (free, no key needed)")
    image_path = img_client.generate(
        f"Bitsol Marketing LinkedIn post: {selected['image_prompt']}",
        size_preset="post",
    )
    print(f"Image: {image_path.resolve()}")

    if args.dry_run:
        print("Dry run — not posted.")
        return

    org_id = _load_env("LINKEDIN_ORG_ID")

    print("Posting to LinkedIn…")
    li = LinkedInClient(linkedin_token, org_id=org_id)
    urn = li.post_with_image(text, image_path)
    engine.log_post(selected["id"], urn, text, str(image_path))

    stats = engine.get_stats()
    print(f"Done. URN: {urn} | Today: {stats['today']}/5 | Total: {stats['total']}")


if __name__ == "__main__":
    main()
