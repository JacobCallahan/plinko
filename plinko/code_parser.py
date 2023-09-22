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

from logzero import logger

from plinko import helpers
from plinko.config import settings
from plinko.parsers import python_parser
from plinko.parsers.pytest_tools import FixtureHandler

PARSED_FILES = []  # This global will help to reduce multiplication of effort


class CodeParser:
    imports = {}

    def __init__(self, **kwargs):
        self.ent_meth_dict = kwargs.get("entity_methods")
        helpers.write_to_file(
            self.ent_meth_dict, "ent_meth_dict.txt", "entity method dict"
        )
        logger.debug(f"Got ent_meth_dict: {self.ent_meth_dict}")
        self.tracked_items = {}
        self.project_root = Path(kwargs.get("project_root", settings.project_root))
        self.create_on_instance = kwargs.get(
            "create_on_instance", settings.create_on_instance
        )
        self.max_depth = kwargs.get("max_depth", settings.max_depth)
        self.PyParser = python_parser.CodeParser
        self.fixture_handler = FixtureHandler
        self.fixture_handler._main_parser = self
        # additional setup
        # keep this map to track old and newly formatted entity names
        self.entity_map = {
            helpers.normalize_text(ent, settings.class_name_style): ent
            for ent in self.ent_meth_dict
        }
        self.entities = list(self.entity_map.keys())
        logger.debug(f"Known entities: {self.entities}")
        self.cov_tests = {}  # {test_name: [coverage]}
        self.miss_tests = []  # [test_name]
        self.all_methods = {}  # {file: {methods}}

    def _parse_file(self, file_path, original_path=None):
        if file_path.suffix == ".py":

            parser = self.PyParser(code_file=file_path, parent_parser=self)
        else:
            return
        parser.parse()
        # rel_path = file_path.relative_to(original_path)
        # put all the tests into one large list
        # put all the methods into one large dict
        parser._match_fixtures()
        for func_path, func_obj in parser.methods.items():
            if func_obj.is_test:
                if "module_org" in func_obj.args:
                    import IPython; IPython.embed()
                if func_obj.covers:
                    self.cov_tests[func_path] = func_obj.covers
                else:
                    self.miss_tests.append(func_path)

    def parse_directory(self, dir_path, original_path=None):
        dir_path = Path(dir_path)
        if not original_path:
            original_path = dir_path
            # todo: This assumes python and pytest
            self.fixture_handler.find_fixture_files(dir_path)  # uses root dir path
            logger.debug(f"Found fixture files: {self.fixture_handler._pending_files.keys()}")
            self.fixture_handler.parse_pending()
            logger.debug(f"Found fixtures: {self.fixture_handler.fixtures}")
        if dir_path.is_dir():
            for item in helpers.recurse_down(dir_path, ".py"):
                self._parse_file(item, original_path)
        else:
            self._parse_file(dir_path, original_path)

    def get_missing_coverage(self):
        """Parse through all known coverage and determine what is missing.

        todo: write what is needed to get the missing coverage
        """
        pass
