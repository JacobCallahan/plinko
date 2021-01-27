"""This module exercises the python_importer's ImportManager class"""
from plinko.deep.parsers.python_importer import ImportManager


def test_positive_register():
    im_inst = ImportManager()
    im_inst.register("test_func", "test_mod", "real_func")
    assert im_inst._find_import("test_func")


def test_positive_import_first_party():
    im_inst = ImportManager()
    assert im_inst.get_file("plinko.deep.parsers.python_parser")
    assert im_inst.get_source("plinko.deep.parsers.python_parser")


def test_positive_import_third_party():
    im_inst = ImportManager()
    assert im_inst.get_file("click.command")
    assert im_inst.get_source("click.command")
