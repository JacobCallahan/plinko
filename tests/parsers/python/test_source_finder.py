from plinko.parsers.source_finder import SourcePath

def test_find_module():
    source_path = SourcePath()
    path = source_path.find("plinko")
    assert path.name == "__init__.py"

def test_find_submodule():
    source_path = SourcePath()
    path = source_path.find("plinko.helpers")
    assert path.name == "helpers.py"

def test_find_relative_module():
    source_path = SourcePath()
    path = source_path.find(".helpers", rel_path="source_finder")
    assert path.name == "helpers.py"

def test_find_relative_submodule():
    source_path = SourcePath()
    path = source_path.find(".parsers.pytest_tools", rel_path="source_finder")
    assert path.name == "pytest_tools.py"

def test_find_nonexistent_module():
    source_path = SourcePath()
    path = source_path.find("nonexistent_module")
    assert path is None

def test_find_nonexistent_submodule():
    source_path = SourcePath()
    path = source_path.find("source_finder.nonexistent_submodule")
    assert path is None
