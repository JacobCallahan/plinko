"""This module exercises the python_importer's ImportManager class"""
from plinko.parsers.python_importer import ImportManager


def test_positive_register():
    ImportManager.register("test_func", "test_mod", "real_func")
    assert ImportManager._find_import("test_func")


def test_positive_import_first_party():
    assert ImportManager.get_file("plinko.parsers.python_parser")
    assert ImportManager.get_ast("plinko.parsers.python_parser")


def test_positive_import_third_party():
    assert ImportManager.get_file("click.command")
    assert ImportManager.get_ast("click.command")
