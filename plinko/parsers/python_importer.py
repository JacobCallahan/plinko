import ast
import builtins
import collections
import sys

from logzero import logger

from plinko.parsers.source_finder import find_file_from_import

BUILTINS = dir(builtins)


class ImportManager:
    known_imports = {}  # {name: {import location:, methods:, ast:}

    def __init__(self):
        # nothing in the stdlib provides coverage
        for name in sys.stdlib_module_names:
            self.known_imports[name] = {
                "location": "stdlib",
                "coverage": None,
                "methods": None,
            }

    def _find_import(self, import_name):
        """Given an import name, try to find it and return the known key."""
        if import_name in self.known_imports:
            return import_name
        for key, val in self.known_imports.items():
            if import_name in (val.get("module_name"), val.get("real_name")):
                return key

    def register(self, import_name, module_name=None, real_name=None):
        """Add a new import if it isn't already known."""
        if import_name not in self.known_imports:
            self.known_imports[import_name] = {
                "module_name": module_name,
                "real_name": real_name,
            }

    def get_file(self, import_name):
        if not self._find_import(import_name):
            self.import_module(import_name)
        elif not self.known_imports.get(import_name, {}).get("location"):
            self.import_module(import_name)
        file = self.known_imports.get(import_name, {}).get("location")
        if file not in ("stdlib", "~bad~"):
            return file

    def get_ast(self, import_name):
        if not self._find_import(import_name):
            self.import_module(import_name)
        return self.known_imports.get(import_name, {}).get("ast")

    def add_methods(self, import_name, methods):
        if not self._find_import(import_name):
            self.import_module(import_name)
        if methods:
            if isinstance(methods, collections.abc.Iterable):
                self.known_imports[import_name].setdefault("methods", set()).update(methods)
            else:
                self.known_imports[import_name].setdefault("methods", set()).add(methods)

    def get_methods(self, import_name):
        if not self._find_import(import_name):
            self.import_module(import_name)
        return self.known_imports.get(import_name, {}).get("methods")

    def resolve_import(self, import_name, call_path=None):
        """Attempt to resolve an import, returning the most beneficial information."""
        # First, return if we already know the import contents
        if self.known_imports[import_name].get("coverage") or self.known_imports[
            import_name
        ].get("ast"):
            return
        if self.known_imports[import_name].get("location") == "~bad~":
            return  # known bad import
        # make sure this isn't an uncaught builtin object
        if import_name in BUILTINS:
            logger.debug(f"{import_name} is a python builtin; ignoring.")
            self.known_imports[import_name] = {
                "location": "~bad~",
                "coverage": None,
                "methods": None,
            }
            return
        # Next, attempt to perform the import
        self.known_imports[import_name]["location"] = self.known_imports[
            import_name
        ].get("location")
        logger.debug(f"Trying to import module {import_name}")
        real_name = (
            self.known_imports[import_name].get("real_name") or import_name
        )  # import x as y
        true_import = self.known_imports[import_name].get("module_name") or real_name
        # logger.debug(f"true import 1 {true_import}")
        if real_name not in true_import:
            if call_path:
                # a more complex call path was given importedmodule.sub.method
                call_path = call_path.replace(import_name, real_name)
                real_name = call_path.replace(" ", ".")
            true_import += "." + real_name
        # logger.debug(f"true import 2 {true_import}")
        try:
            source_file = find_file_from_import(true_import.replace(" ", "."))
        except ModuleNotFoundError:
            source_file = None
        logger.debug(source_file or true_import)
        if source_file is None:
            self.known_imports[import_name]["location"] = "~bad~"
            logger.warning(
                f"Unable to import {true_import}. Make sure it is installed.\n"
                f"{true_import=}, {call_path=}"
            )
            return
        self.known_imports[import_name]["location"] = source_file
        self.known_imports[import_name]["ast"] = ast.parse(source_file.read_text())

    def import_module(self, module_name):
        """Import the code from a specific module."""
        self.register(module_name)
        if module_name in self.known_imports:
            return self.resolve_import(module_name)
        for key, val in self.known_imports.items():
            if val.get("real_name") == module_name:
                return self.resolve_import(key)

    def resolve_all(self):
        for key in list(self.known_imports.keys()):
            if not self.known_imports[key].get("location"):
                self.resolve_import(key)


# Force singleton behavior
ImportManager = ImportManager()
