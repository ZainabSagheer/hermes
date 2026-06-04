import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hermas.client import HermesClient
from hermas.config import config
from hermas.goals import get_template, list_templates, render

app = typer.Typer(
    name="hermas",
    help="Hermas — Python automation layer for Hermes Agent.",
    no_args_is_help=True,
)
goal_app = typer.Typer(help="Goal execution commands.", no_args_is_help=True)
image_app = typer.Typer(help="AI image generation (DALL-E 3 / gpt-image-1).", no_args_is_help=True)
linkedin_app = typer.Typer(help="LinkedIn post management.", no_args_is_help=True)
content_app = typer.Typer(help="Bitsol Marketing automated content engine.", no_args_is_help=True)
app.add_typer(goal_app, name="goal")
app.add_typer(image_app, name="image")
app.add_typer(linkedin_app, name="linkedin")
app.add_typer(content_app, name="content")

console = Console()
client = HermesClient()


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

@app.command()
def setup():
    """Install Hermes Agent (skips if already installed)."""
    try:
        result = subprocess.run(
            ["hermes", "--version"] if sys.platform != "win32" else ["hermes.cmd", "--version"],
            capture_output=True,
        )
        already_installed = result.returncode == 0
    except FileNotFoundError:
        already_installed = False

    if already_installed:
        console.print("[green]Hermes Agent is already installed.[/green]")
        return

    console.print("[bold]Installing Hermes Agent...[/bold]")
    try:
        if sys.platform == "win32":
            subprocess.run(
                [
                    "powershell", "-Command",
                    "iex (irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1)",
                ],
                check=True,
            )
        else:
            subprocess.run(
                [
                    "bash", "-c",
                    "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash",
                ],
                check=True,
            )
        console.print("[green]Done.[/green] Run [bold]hermes[/bold] to complete initial setup.")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Install failed.[/red] {e}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status():
    """Show whether Hermes Agent is reachable and the current goal status."""
    reachable = client.is_running()
    icon = "[green]online[/green]" if reachable else "[red]offline[/red]"
    console.print(f"Hermes Agent ({config.hermes_url}): {icon}")

    if reachable:
        result = client.goal_status()
        _print_result(result)


# ---------------------------------------------------------------------------
# goal subcommands
# ---------------------------------------------------------------------------

@goal_app.command("list")
def goal_list():
    """List all available goal templates."""
    table = Table(title="Goal Templates", show_lines=False)
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Variables", style="dim")
    table.add_column("Description")

    for entry in list_templates():
        table.add_row(
            entry.category,
            entry.name,
            ", ".join(f"{{{v}}}" for v in entry.vars),
            entry.description,
        )

    console.print(table)


@goal_app.command("run")
def goal_run(
    category: str = typer.Argument(..., help="Template category (research / content / dev / ops)"),
    name: str = typer.Argument(..., help="Template name"),
):
    """Fill a goal template interactively and send it to Hermes Agent."""
    try:
        spec = get_template(category, name)
    except KeyError as e:
        console.print(f"[red]{e}[/red]  Run [bold]hermas goal list[/bold] to browse templates.")
        raise typer.Exit(1)

    console.print(Panel(f"[bold]{category} / {name}[/bold]\n{spec['description']}"))
    filled: dict[str, str] = {}
    for var in spec["vars"]:
        filled[var] = typer.prompt(f"  {var}")

    goal_text = render(category, name, filled)
    console.print(Panel(goal_text, title="Goal", border_style="dim"))

    confirmed = typer.confirm("Send this goal to Hermes Agent?", default=True)
    if not confirmed:
        raise typer.Exit()

    result = client.run_goal(goal_text)
    _print_result(result)


@goal_app.command("send")
def goal_send(goal: str = typer.Argument(..., help="Free-form goal text")):
    """Send a free-form goal directly to Hermes Agent."""
    result = client.run_goal(goal)
    _print_result(result)


@goal_app.command("status")
def goal_status():
    """Check the status of the currently running goal."""
    result = client.goal_status()
    _print_result(result)


@goal_app.command("pause")
def goal_pause():
    """Pause the current goal without losing context."""
    _print_result(client.goal_pause())


@goal_app.command("resume")
def goal_resume():
    """Resume a paused goal."""
    _print_result(client.goal_resume())


@goal_app.command("clear")
def goal_clear():
    """End the current goal."""
    confirmed = typer.confirm("Clear the active goal?", default=False)
    if confirmed:
        _print_result(client.goal_clear())


# ---------------------------------------------------------------------------
# image subcommands
# ---------------------------------------------------------------------------

def _image_client(model: str = "dall-e-3"):
    from hermas.image_gen import OpenAIImageClient
    key = os.environ.get("OPENAI_API_KEY") or _load_env_key("OPENAI_API_KEY")
    if not key:
        console.print("[red]OPENAI_API_KEY not set.[/red] Add it to ~/.hermes/.env")
        raise typer.Exit(1)
    return OpenAIImageClient(key, model=model)


@image_app.command("generate")
def image_generate(
    prompt: str = typer.Argument(..., help="Image description / prompt"),
    size: str = typer.Option("post", help="Preset: post | banner | cover | card"),
    model: str = typer.Option("dall-e-3", help="OpenAI model: dall-e-3 | gpt-image-1"),
    output: Optional[Path] = typer.Option(None, help="Output file path"),
):
    """Generate an image with DALL-E 3 / gpt-image-1 via OpenAI."""
    from hermas.image_gen import SIZES
    if size not in SIZES:
        console.print(f"[red]Unknown size '{size}'.[/red] Choose: {', '.join(SIZES)}")
        raise typer.Exit(1)
    client = _image_client(model=model)
    console.print(f"Generating [bold]{size}[/bold] image ({SIZES[size]}) with [bold]{model}[/bold]…")
    path = client.generate(prompt, size_preset=size, output_path=output)
    console.print(f"[green]Saved:[/green] {path.resolve()}")


@image_app.command("sizes")
def image_sizes():
    """List available LinkedIn image size presets."""
    from hermas.image_gen import SIZES
    t = Table(title="LinkedIn Image Sizes")
    t.add_column("Preset")
    t.add_column("Dimensions")
    t.add_column("Use for")
    meta = {
        "post":   "Feed post / carousel slide",
        "banner": "Profile banner (personal)",
        "cover":  "Company page cover photo",
        "card":   "Article / link preview card",
    }
    for k, v in SIZES.items():
        t.add_row(k, v, meta.get(k, ""))
    console.print(t)


# ---------------------------------------------------------------------------
# linkedin subcommands
# ---------------------------------------------------------------------------

def _linkedin_client():
    from hermas.linkedin import LinkedInClient
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN") or _load_env_key("LINKEDIN_ACCESS_TOKEN")
    if not token:
        console.print(
            "[red]LINKEDIN_ACCESS_TOKEN not set.[/red]\n"
            "Run [bold]hermas linkedin auth[/bold] to get one."
        )
        raise typer.Exit(1)
    org_id = os.environ.get("LINKEDIN_ORG_ID") or _load_env_key("LINKEDIN_ORG_ID")
    return LinkedInClient(token, org_id=org_id)


@linkedin_app.command("auth")
def linkedin_auth():
    """OAuth flow: opens browser, captures token, saves it automatically."""
    from hermas.linkedin import get_access_token

    client_id = os.environ.get("LINKEDIN_CLIENT_ID") or _load_env_key("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET") or _load_env_key("LINKEDIN_CLIENT_SECRET")

    if not client_id or not client_secret:
        console.print(
            "[red]LINKEDIN_CLIENT_ID or LINKEDIN_CLIENT_SECRET not set.[/red]\n"
            "Add them to [bold]~/.hermes/.env[/bold] and re-run."
        )
        raise typer.Exit(1)

    console.print("Opening LinkedIn in your browser — authorise the app then return here…")

    try:
        token = get_access_token(client_id, client_secret)
    except Exception as e:
        console.print(f"[red]Auth failed:[/red] {e}")
        raise typer.Exit(1)

    # Write token into ~/.hermes/.env
    env_path = Path.home() / ".hermes" / ".env"
    text = env_path.read_text()
    if "LINKEDIN_ACCESS_TOKEN=" in text:
        lines = []
        for line in text.splitlines():
            if line.startswith("LINKEDIN_ACCESS_TOKEN="):
                lines.append(f"LINKEDIN_ACCESS_TOKEN={token}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n")
    else:
        env_path.write_text(text + f"\nLINKEDIN_ACCESS_TOKEN={token}\n")

    console.print("[green]Access token saved to ~/.hermes/.env[/green]")
    console.print("You're ready to post. Try: [bold]hermas linkedin post \"Hello LinkedIn!\"[/bold]")


@linkedin_app.command("post")
def linkedin_post(
    text: str = typer.Argument(..., help="Post text / caption"),
    image: Optional[Path] = typer.Option(None, "--image", "-i", help="Image file to attach"),
    visibility: str = typer.Option("PUBLIC", help="PUBLIC or CONNECTIONS"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without posting"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Post to LinkedIn, optionally with an image."""
    if dry_run:
        console.print(Panel(text, title="[dim]Draft (not posted)[/dim]"))
        if image:
            console.print(f"Image: {image}")
        return

    if not yes:
        confirmed = typer.confirm("Post to LinkedIn?", default=True)
        if not confirmed:
            raise typer.Exit()

    li = _linkedin_client()
    if image:
        if not image.exists():
            console.print(f"[red]Image not found:[/red] {image}")
            raise typer.Exit(1)
        console.print("Uploading image…")
        urn = li.post_with_image(text, image, visibility=visibility)
    else:
        urn = li.post_text(text, visibility=visibility)

    console.print(f"[green]Posted![/green] URN: {urn}")


@linkedin_app.command("generate-and-post")
def linkedin_generate_and_post(
    text: str = typer.Argument(..., help="Post caption / text"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Image generation prompt"),
    size: str = typer.Option("post", help="Image size preset: post | banner | cover | card"),
    visibility: str = typer.Option("PUBLIC", help="PUBLIC or CONNECTIONS"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate image but don't post"),
):
    """Generate an image with FLUX then post it to LinkedIn in one step."""
    fal = _image_client()
    console.print(f"Generating image…")
    path = fal.generate(prompt, size_preset=size)
    console.print(f"[green]Image ready:[/green] {path.resolve()}")

    console.print(Panel(text, title="Post preview"))

    if dry_run:
        console.print("[dim]Dry run — not posted.[/dim]")
        return

    confirmed = typer.confirm("Post to LinkedIn?", default=True)
    if not confirmed:
        raise typer.Exit()

    li = _linkedin_client()
    urn = li.post_with_image(text, path, visibility=visibility)
    console.print(f"[green]Posted![/green] URN: {urn}")


# ---------------------------------------------------------------------------
# content subcommands  (Bitsol Marketing automated engine)
# ---------------------------------------------------------------------------

def _openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY") or _load_env_key("OPENAI_API_KEY")
    if not key:
        console.print("[red]OPENAI_API_KEY not set.[/red]")
        raise typer.Exit(1)
    return key

def _linkedin_token() -> str:
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN") or _load_env_key("LINKEDIN_ACCESS_TOKEN")
    if not token:
        console.print("[red]LINKEDIN_ACCESS_TOKEN not set.[/red] Run: hermas linkedin auth")
        raise typer.Exit(1)
    return token


@content_app.command("post")
def content_post(
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Optional topic or angle override"),
    pillar: Optional[str] = typer.Option(None, "--pillar", "-p", help="Pillar ID: tip|insight|case_study|strategy|engagement"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate content but don't post"),
    visibility: str = typer.Option("PUBLIC", help="PUBLIC or CONNECTIONS"),
):
    """Generate one Bitsol Marketing post (text + image) and publish to LinkedIn."""
    from hermas.content_engine import ContentEngine, PILLARS
    from hermas.image_gen import OpenAIImageClient
    from hermas.linkedin import LinkedInClient

    key = _openai_key()
    engine = ContentEngine(key)

    # Select pillar
    if pillar:
        selected = next((p for p in PILLARS if p["id"] == pillar), None)
        if not selected:
            ids = ", ".join(p["id"] for p in PILLARS)
            console.print(f"[red]Unknown pillar '{pillar}'.[/red] Choose: {ids}")
            raise typer.Exit(1)
    else:
        selected = engine.next_pillar()

    console.print(f"\nPillar: [bold cyan]{selected['name']}[/bold cyan]  |  Today: {engine.today_count()}/5 posted\n")

    # Generate text
    with console.status("Generating post copy with GPT-4o…"):
        text = engine.generate_text(selected, topic=topic)
    console.print(Panel(text, title=f"[bold]{selected['name']}[/bold]", border_style="cyan"))

    # Generate image
    with console.status("Generating image with DALL-E 3…"):
        img_client = OpenAIImageClient(_openai_key())
        image_path = img_client.generate(
            prompt=f"Bitsol Marketing LinkedIn post: {selected['image_prompt']}",
            size_preset="post",
        )
    console.print(f"[green]Image saved:[/green] {image_path.resolve()}")

    if dry_run:
        console.print("\n[dim]Dry run — not posted.[/dim]")
        return

    confirmed = typer.confirm("\nPost to LinkedIn?", default=True)
    if not confirmed:
        raise typer.Exit()

    with console.status("Uploading and posting…"):
        li = LinkedInClient(_linkedin_token())
        urn = li.post_with_image(text, image_path, visibility=visibility)

    engine.log_post(selected["id"], urn, text, str(image_path))
    stats = engine.get_stats()
    console.print(f"\n[bold green]Posted![/bold green] URN: {urn}")
    console.print(f"Today: {stats['today']}/5  |  All time: {stats['total']} posts")


@content_app.command("preview")
def content_preview(
    pillar: Optional[str] = typer.Option(None, "--pillar", "-p", help="Pillar ID (optional)"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Topic or angle"),
):
    """Generate and preview content WITHOUT posting."""
    from hermas.content_engine import ContentEngine, PILLARS
    from hermas.image_gen import OpenAIImageClient

    key = _openai_key()
    engine = ContentEngine(key)

    selected = (
        next((p for p in PILLARS if p["id"] == pillar), None)
        if pillar else engine.next_pillar()
    )
    if pillar and not selected:
        console.print(f"[red]Unknown pillar '{pillar}'.[/red]")
        raise typer.Exit(1)

    with console.status(f"Generating {selected['name']} post…"):
        text = engine.generate_text(selected, topic=topic)

    console.print(Panel(text, title=f"[bold]{selected['name']}[/bold] (preview)", border_style="dim"))

    if typer.confirm("Generate image too?", default=False):
        with console.status("Generating image…"):
            img = OpenAIImageClient(_openai_key())
            path = img.generate(
                f"Bitsol Marketing LinkedIn post: {selected['image_prompt']}",
                size_preset="post",
            )
        console.print(f"[green]Image:[/green] {path.resolve()}")


@content_app.command("stats")
def content_stats():
    """Show posting stats for Bitsol Marketing."""
    from hermas.content_engine import ContentEngine, _LOG_PATH
    import json

    key = _openai_key()
    engine = ContentEngine(key)
    stats = engine.get_stats()

    console.print(f"\n[bold]Bitsol Marketing — LinkedIn Post Stats[/bold]")
    console.print(f"  Today:      {stats['today']}/5 posts")
    console.print(f"  All time:   {stats['total']} posts")
    if stats["last_post"]:
        lp = stats["last_post"]
        console.print(f"  Last post:  {lp['timestamp'][:16]} — {lp['pillar']}")
        console.print(f"  Preview:    {lp['preview'][:80]}…")


@content_app.command("pillars")
def content_pillars():
    """List the 5 content pillars used for daily posts."""
    from hermas.content_engine import PILLARS
    t = Table(title="Bitsol Marketing Content Pillars")
    t.add_column("ID", style="cyan")
    t.add_column("Name", style="bold")
    t.add_column("What it does")
    for p in PILLARS:
        t.add_row(p["id"], p["name"], p["prompt"][:80] + "…")
    console.print(t)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_env_key(key: str) -> str | None:
    """Read a key from ~/.hermes/.env without requiring dotenv loaded globally."""
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}=") and not line.startswith("#"):
            return line.split("=", 1)[1].strip()
    return None


def _print_result(result: dict) -> None:
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
    if result.get("output"):
        console.print(result["output"])
    if not result.get("error") and not result.get("output"):
        console.print(result)


if __name__ == "__main__":
    app()
