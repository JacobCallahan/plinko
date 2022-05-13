"""Parser controller.

Orchestrates and analyses the results of all parsers.
All language parsers must implement a CodeParser class
This class must provide the following data attributes:
  code_file - To receive a file path
  create_on_instance - To determine if an instance consitutes a create
  max_depth - To control the max external recursion depth
  entities - To accept a list of entities
  tests - To export a list of tests in the file
  methods - To export a list of methods and what they cover and link to
"""
from pathlib import Path
from uuid import uuid4

from logzero import logger
from plinko import helpers
from plinko.parsers import python_parser
from plinko.simple_config import config

PARSED_FILES = []  # This global will help to reduce multiplication of effort

class CodeParser:
    imports = {}

    def __init__(self, **kwargs):
        self.ent_meth_dict = kwargs.get("entity_methods")
        helpers.write_to_file(self.ent_meth_dict, "ent_meth_dict.txt", "entity method dict")
        logger.debug(f"Got ent_meth_dict: {self.ent_meth_dict}")
        self.tracked_items = {}
        self.create_on_instance = kwargs.get("create_on_instance", True)
        self.max_depth = kwargs.get("max_depth")
        self.PyParser = python_parser.CodeParser
        # additional setup
        # keep this map to track old and newly formatted entity names
        self.entity_map = {
            helpers.normalize_text(ent, config.class_name_style): ent
            for ent in self.ent_meth_dict.keys()
        }
        self.entities = list(self.entity_map.keys())
        logger.debug(f"Known entities: {self.entities}")
        self.cov_tests = {}  # {test_name: [coverage]}
        self.miss_tests = []  # [test_name]
        self.all_methods = {}  # {file: {methods}}

    def _parse_file(self, file_path, original_path=None):
        if file_path.name[-3:] == ".py":
            parser = self.PyParser(
                code_file=file_path, max_depth=self.max_depth, entities=self.entities
            )
        else:
            return
        parser.parse()
        rel_path = file_path.relative_to(original_path)
        # put all the tests into one large list
        # put all the methods into one large dict
        for name, covers in parser.methods.items():
            if "test_" in name:
                test_path = f"{rel_path} {parser.tests.get(name, '~')} {name}".replace(
                    "~", ""
                )
                if covers:
                    self.cov_tests[test_path] = covers
                else:
                    self.miss_tests.append(test_path)

    def parse_directory(self, dir_path, original_path=None):
        if isinstance(dir_path, str):
            # convert this to a Path object
            dir_path = Path(dir_path)
        if not original_path:
            original_path = dir_path
        if dir_path.is_dir():
            for item in dir_path.iterdir():
                if item.is_dir():
                    self.parse_directory(item, original_path)
                else:
                    self._parse_file(item, original_path)
        else:
            self._parse_file(dir_path, original_path)

    def get_missing_coverage(self):
        """Parse through all known coverage and determine what is missing

        todo: write what is needed to get the missing coverage
        """
        pass
