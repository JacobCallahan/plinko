from functools import cache
from pathlib import Path

from logzero import logger

from plinko import helpers

FINDERS = {}


class SourcePath:
    """A class to help find source files by module name or import path name."""

    def __new__(cls, base_path=None):
        """Ensure that we aren't creating new instanced for the same base path."""
        base_path = Path(base_path or ".").absolute()
        if base_path not in FINDERS:
            FINDERS[base_path] = super().__new__(cls)
        return FINDERS[base_path]

    def __init__(self, base_path=None):
        self.base_path = (Path(base_path) if base_path else Path.cwd()).absolute()
        self.all_modules = helpers.recurse_down(self.base_path, ".py")

    @cache
    def _find_relative_from_base(self, rel_path):
        """Search for a relative path down from the base path."""
        for module in self.all_modules:
            if module.stem == rel_path:
                return module

    @cache
    def find(self, name, rel_path=None):
        """Find a source file by module name or import path name.

        Examples:
            "my_module"
            "my_module.my_submodule"
            ".my_submodule"
            ".my_submodule.my_subsubmodule"
            "..my_subsubmodule"
        """
        rel_path = Path(rel_path) if rel_path else self.base_path
        if rel_path.is_file():
            rel_path = rel_path.parent
        logger.debug(f"looking for {name} in {rel_path}")
        if name.startswith("."):
            # if path is relative, recurse up until we find the import
            if found := self.find(name[1:], rel_path.parent):
                return found
            elif rel_path != self.base_path:
                # if we can't find it higher, try to find it lower
                if found_path := self._find_relative_from_base(rel_path.name):
                    return self.find(name, found_path)
        as_path = name.replace(".", "/")
        # check if the path exists as a file (module)
        resolved_path = rel_path / f"{as_path}.py"
        if resolved_path.exists():
            logger.debug(f"found module {resolved_path}")
            return resolved_path
        # check if the path exists as a package (__init__.py)
        init_path = rel_path / as_path / "__init__.py"
        if init_path.exists():
            logger.debug(f"found package {init_path}")
            return init_path
        # could be an attribute of its parent module, check there
        if (fpath := resolved_path.parent.with_suffix(".py")).exists():
            return fpath
        # could be an attribute of its parent package, check there
        if (fpath := resolved_path.parent.parent / "__init__.py").exists():
            return fpath
        # if the top level name matches our base path name, strip it and try again
        if name.startswith(self.base_path.name):
            return self.find(name[len(self.base_path.name) + 1 :])

    @classmethod
    def from_module(cls, module_name):
        import sys

        for path in sys.path:
            if "site-packages" not in path:
                continue
            # check if a directory exists with the module name
            if (module_path := Path(path) / module_name).exists():
                return cls(module_path)
        # check if the module is relative to the current directory
        if ((module_path := Path.cwd() / module_name) / "__init__.py").exists():
            return cls(module_path)
        raise ModuleNotFoundError(f"Unable to find module {module_name}")


@cache
def find_file_from_import(import_string, current_path=None):
    """Based on any valid python import string, find the most appropriate source file.

    example imports:
        import my_module
        import my_module.my_submodule
        from my_module import my_submodule
        from my_module.my_submodule import my_subsubmodule
        from .my_module import my_submodule
        from .my_module.my_submodule import my_subsubmodule
        from ..my_subsubmodule import my_subsubmodule
        import my_module as mm
        from my_module import my_submodule as ms
    """
    # print(f"finding file from import: {import_string}")
    if import_string.startswith("import "):
        import_string = import_string[7:]
    elif import_string.startswith("from "):
        import_string = import_string[5:]
    if " as " in import_string:
        import_string = import_string.split(" as ")[0]
    if " import " in import_string:
        import_string = import_string.replace(" import ", ".")
    import_string = import_string.strip()
    # determine if we're a relative import
    if import_string.startswith("."):
        # try to find the import based on the current_path
        if found_path := SourcePath(current_path).find(import_string):
            return found_path
        # if nothing was found and we have a sub import to split off, do so
        if "." in import_string:
            import_string, sub_import = import_string.rsplit(".", 1)
            return find_file_from_import(import_string, current_path)
    # if we're not relative, try an absolute import with the module name
    mod_name = import_string.split(".")[0]
    if found_path := SourcePath.from_module(mod_name).find(import_string):
        return found_path
    # if nothing was found and we have a sub import to split off, do so
    if "." in import_string:
        import_string, sub_import = import_string.rsplit(".", 1)
        return find_file_from_import(import_string)
