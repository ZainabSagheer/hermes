from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class HermasConfig(BaseSettings):
    hermes_url: str = "http://localhost:9119"
    profile: str = "default"
    goals_dir: Path = Path(__file__).parent.parent / "goals"

    model_config = {"env_file": ".env", "env_prefix": "HERMAS_"}


config = HermasConfig()
