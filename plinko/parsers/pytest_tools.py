import ast
import inspect
from pathlib import Path

from logzero import logger

from plinko.helpers import recurse_up

# parametrized fixtures
# mark.usefixtures
# function arguments

# TODO: Recursively resolve fixture coverage - pull from parent fixtures

class FixtureHandler:
    # TODO: Resolve parametrized fixture use
    def __init__(self, base_path=None):
        self.base_path = Path(base_path or ".")
        self._pending_files = {}  # {file_path: PyParser}
        self._main_parser = None  # deferred to avoid circular imports
        self.fixtures = {}  # {Function.name: fixture Function}

    @property
    def pyparser(self):
        if not self._main_parser:
            raise Exception("FixtureHandler._main_parser not set")
        return self._main_parser.PyParser

    def find_fixture_files(self, haystack=None):
        """Check root dirs for conftest.py."""
        haystack = haystack or self.base_path
        logger.debug(f"Checking for fixture files in {haystack}")
        if isinstance(haystack, Path) and haystack.exists():
            for file in recurse_up(
                haystack, self._main_parser.project_root, ".py", "test_"
            ):
                if file.name == "conftest.py":
                    logger.debug(f"Found conftest.py in {file.absolute()}")
                    self._parse_conftest(file)
        if inspect.ismodule(haystack):
            """check for pytest_plugins = []"""
            for name, obj in haystack.__dict__.items():
                if self._is_fixture(obj):
                    breakpoint()
                    # how'd you get here, jake?
                    self.fixtures[f"{haystack.__name__}:{name}"] = obj

    def parse_pending(self):
        """Parse all pending fixture files."""
        for parser in self._pending_files.values():
            parser.parse()
            for obj in list(parser.methods.values()):  # saw weird behavior with mapping alone
                if obj.is_fixture and obj.name not in self.fixtures:
                    self.fixtures[obj.name] = obj
        self._pending_files = {}

    def _file_has_fixtures(self, file_path):
        with file_path.open() as file_stream:
            for line in file_stream:
                if "from pytest import fixture" in line:
                    return True
                if "pytest.fixture" in line:
                    return True

    def _is_fixture(obj):
        """Determine if a function is a fixture."""
        if inspect.isfunction(obj):
            return getattr(obj, "_pytestfixturefunction", False)
        else:
            logger.error(f"{obj} is a {type(obj)}, not a function")

    def _parse_conftest(self, file_path):
        """Parse a conftest.py file to find interests."""
        if self._file_lists_plugins(file_path):
            self._pull_plugins(file_path)
        if self._file_has_fixtures(file_path):
            self._pending_files[file_path] = self.pyparser(file_path, self._main_parser)

    def _file_lists_plugins(self, file_path):
        with file_path.open() as file_stream:
            for line in file_stream:
                if "pytest_plugins = [" in line:
                    return True

    def _pull_plugins(self, file_path):
        """Parse through a conftest ast and pull a list of plugin files."""
        for node in ast.walk(ast.parse(file_path.read_text())):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.List):
                    for item in node.value.elts:
                        if isinstance(item, ast.Str | ast.Constant):
                            f_path = Path(f"{item.s.replace('.','/')}.py")
                            f_path = self._main_parser.project_root / f_path
                            # import IPython; IPython.embed()
                            if self._file_has_fixtures(f_path):
                                self._pending_files[f_path] = self.pyparser(
                                    f_path, self._main_parser
                                )


# Force singleton behavior
FixtureHandler = FixtureHandler()

"""
com.brave.Browser
com.discordapp.Discord
com.mojang.Minecraft
com.obsproject.Studio
com.obsproject.Studio.Plugin.StreamFX
com.uploadedlobster.peek
io.github.Hexchat
io.github.Pithos
io.podman_desktop.PodmanDesktop
org.gabmus.hydrapaper
org.gnome.DejaDup
org.gnome.GHex
org.inkscape.Inkscape
org.kde.krita
org.olivevideoeditor.Olive
org.stellarium.Stellarium
org.videolan.VLC
org.wireshark.Wireshark
"""