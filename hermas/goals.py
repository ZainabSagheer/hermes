from pathlib import Path
from typing import NamedTuple

import yaml

from hermas.config import config


class TemplateEntry(NamedTuple):
    category: str
    name: str
    description: str
    vars: list[str]


def _load() -> dict:
    path = config.goals_dir / "templates.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def list_templates() -> list[TemplateEntry]:
    data = _load()
    out: list[TemplateEntry] = []
    for category, items in data.items():
        for name, spec in items.items():
            out.append(TemplateEntry(category, name, spec["description"], spec["vars"]))
    return out


def get_template(category: str, name: str) -> dict:
    data = _load()
    try:
        return data[category][name]
    except KeyError:
        raise KeyError(f"Template '{category}/{name}' not found.")


def render(category: str, name: str, vars: dict[str, str]) -> str:
    spec = get_template(category, name)
    missing = [v for v in spec["vars"] if v not in vars]
    if missing:
        raise ValueError(f"Missing template variables: {', '.join(missing)}")
    return spec["template"].format(**vars).strip()
