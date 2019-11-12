"""Simple Config - Config.... Simplified!"""

import json
import os
import yaml
from pathlib import Path
from logzero import logger


class SimpleConfig:
    def __init__(self, **kwargs):
        self._cfg_file = Path(kwargs.get("cfg_file", "config.yml"))
        cfg_path = Path(os.environ.get("PLINKO_DIRECTORY", "")).absolute()
        print(cfg_path)
        self._cfg_file = cfg_path.joinpath(self._cfg_file)
        self._load_config()
        self._pull_envars()

    def _load_config(self):
        """load items from a config file directly into the config instance"""
        cfg_dict = None
        if self._cfg_file.suffix in [".yaml", ".yml"]:
            with self._cfg_file.open("r+") as yaml_config:
                try:
                    cfg_dict = yaml.load(yaml_config, Loader=yaml.FullLoader)
                except Exception as e:
                    logger.warning(f"Unable to load {self._cfg_file} due to {e}")
        elif self._cfg_file.suffix == ".json":
            with self._cfg_file.open("r+") as json_config:
                try:
                    cfg_dict = json.load(json_config)
                except Exception as e:
                    logger.warning(f"Unable to load {self._cfg_file} due to {e}")
        else:
            logger.warning(f"Unable to load unsupported config file {self._cfg_file}")
            return
        # load each entry into the instance's dictionary
        for key, val in cfg_dict.items():
            self.__dict__[key] = val

    def _pull_envars(self):
        """find environment variables that match the provided prefix and load them"""
        if self.envar_prefix:
            for key, val in os.environ.items():
                if key.startswith(self.envar_prefix):
                    self.__dict__[key] = val


config = SimpleConfig()
