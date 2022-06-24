import os
from pathlib import Path

from dynaconf import Dynaconf
from xdg_base_dirs import xdg_config_home, xdg_data_home


class ConfigurationError(Exception):
    pass

BANNED_DIRS = [".git", "__pycache__"]

PLINKO_CONFIG_DIR = Path(
    os.environ.get("PLINKO_CONFIG_DIR", xdg_config_home() / "plinko")
)
if not PLINKO_CONFIG_DIR.joinpath("plinko_settings.yaml").exists():
    raise ConfigurationError(f"Unable to find plinko config in: {PLINKO_CONFIG_DIR}")

PLINKO_DATA_DIR = Path(os.environ.get("PLINKO_DATA_DIR", xdg_data_home() / "plinko"))
PLINKO_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings = Dynaconf(
    settings_file=str(PLINKO_CONFIG_DIR.joinpath("plinko_settings.yaml").absolute()),
    ENVVAR_PREFIX_FOR_DYNACONF="PLINKO",
)
