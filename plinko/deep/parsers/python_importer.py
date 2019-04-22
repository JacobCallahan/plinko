import ast
import builtins
import importlib
import inspect
from astunparse import unparse
from importlib import util  # A python bug makes this necessary
from logzero import logger
from plinko.helpers import get_coverage

BUILTINS = dir(builtins)

class ImportManager:
    known_imports = {}  # {name: {import location:, methods:, ast:}

    def __init__(self):
        pass

    def _find_import(self, import_name):
        """Given an import name, try to find it and return the known key"""
        if import_name in self.known_imports:
            return import_name
        for key, val in self.known_imports.items():
            if import_name in (val.get("module_name"), val.get("real_name")):
                return key

    def register(self, import_name, module_name=None, real_name=None):
        """Add a new import if it isn't already known"""
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
        if not file in ["stdlib", "~bad~"]:
            return file

    def get_source(self, import_name):
        if not self._find_import(import_name):
            self.import_module(import_name)
        return self.known_imports.get(import_name, {}).get("source")

    def add_methods(self, import_name, methods):
        if not self._find_import(import_name):
            self.import_module(import_name)
        self.known_imports[import_name]["methods"] = methods

    def get_methods(self, import_name):
        if not self._find_import(import_name):
            self.import_module(import_name)
        return self.known_imports.get(import_name, {}).get("methods")

    @staticmethod
    def better_getsource(live_object):
        """Uses inspect's getsource, but strips extra indentation"""
        try:
            raw_source = inspect.getsource(live_object)
        except TypeError:
            logger.debug(
                f"Can't get the source from non-supported object: {live_object}"
            )
            return
        whitespace, pos = True, 0
        while whitespace:
            if raw_source[pos] == " ":
                pos += 1
            else:
                whitespace = False
        if pos == 0:
            """no adjustment needed!"""
            return raw_source
        else:
            return "\n".join([line[pos:] for line in raw_source.splitlines()])

    def resolve_import(self, import_name, call_path=None):
        """Attempt to resolve an import, returning the most beneficial information"""
        # First, return if we already know the import contents
        if self.known_imports[import_name].get("coverage") or self.known_imports[
            import_name
        ].get("ast"):
            return
        if self.known_imports[import_name].get("location") == "~bad~":
            # known bad import
            return
        # make sure this isn't an uncaught builtin object
        if import_name in BUILTINS:
            logger.debug(f"{import_name} is a python builtin. Ignoring.")
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
        if real_name not in true_import:
            if call_path:
                # a more complex call path was given importedmodule.sub.method
                call_path = call_path.replace(import_name, real_name)
                real_name = call_path.replace(" ", ".")
            true_import += "." + real_name
        if ".." in true_import:
            logger.warning(
                f"Unable to import {true_import}. Relative imports are not currently supported."
            )
            return
        logger.debug(f"Attempting to import {true_import}")
        try:
            mod_spec = util.find_spec(true_import.replace(" ", "."))
        except ModuleNotFoundError:
            mod_spec = None
        sub_imports = []  # just in case the full path doesn't work
        if not mod_spec:
            # import didn't work, let's try higher levels
            working = False
            while not working and "." in true_import:
                temp_split = true_import.split(".")
                sub_imports.insert(0, temp_split.pop(-1))
                true_import = ".".join(temp_split)
                try:
                    mod_spec = util.find_spec(true_import.replace(" ", "."))
                except ModuleNotFoundError:
                    mod_spec = None
                working = True if mod_spec else False
        if mod_spec is None:
            self.known_imports[import_name]["location"] = "~bad~"
            logger.warning(f"Unable to import {true_import}. Make sure it is installed.")
            return
        if mod_spec.origin and "site-packages" in mod_spec.origin:
            # this is something user-installed
            temp_import = importlib.import_module(true_import)
            if sub_imports:
                # we have to dig down to get the code we want
                for sub in sub_imports:
                    if sub in dir(temp_import):
                        temp_import = temp_import.__dict__.get(sub)
                        self.known_imports[import_name][
                            "source"
                        ] = self.better_getsource(temp_import)
                    else:
                        logger.warning(
                            f"Unable to import {real_name}. Make sure it is installed."
                        )
                        return
            self.known_imports[import_name]["location"] = mod_spec.origin
        else:
            logger.debug(f"{import_name} is part of the python library. skipping")
            self.known_imports[import_name]["location"] = "stdlib"

    def import_module(self, module_name):
        """Import the code from a specific module"""
        self.register(module_name)
        if module_name in self.known_imports:
            return self.resolve_import(module_name)
        for key, val in self.known_imports.items():
            if val.get("real_name") == module_name:
                return self.resolve_import(key)

    def resolve_all(self):
        for key, val in self.known_imports.items():
            if not val.get("location"):
                self.resolve_import(key)
