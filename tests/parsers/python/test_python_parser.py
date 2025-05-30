import pytest
import asyncio
import ast
from pathlib import Path

from plinko.parsers.python_parser import CodeParser as PythonCodeParser
from plinko.parsers.python_parser import Function
from plinko.lsp_adapter import LSPAdapter # Used for mock type


@pytest.fixture
def mock_parent_parser(mocker):
    mp_parser = mocker.Mock()
    mp_parser.project_root = Path("/fake/project")
    mp_parser.entities = ["nailgun", "another_entity"]
    mp_parser.create_on_instance = False
    mp_parser.fixture_handler = mocker.Mock()
    mp_parser.fixture_handler.fixtures = {} 
    return mp_parser

@pytest.fixture
def mock_lsp_adapter(mocker):
    lsp_adapter = mocker.create_autospec(LSPAdapter, instance=True)
    # Methods used by CodeParser and Function that interact with LSPAdapter
    methods_to_mock = [
        'start_server_and_initialize', 
        'shutdown_server', 
        'get_definition', 
        'get_references',
        'open_document' # Though not directly called by CodeParser.parse's top level, 
                        # it's part of LSPAdapter's public API.
                        # Function.async_parse_with_lsp calls get_definition, which then uses multilspy's internal file ops.
    ]
    for method_name in methods_to_mock:
        setattr(lsp_adapter, method_name, mocker.AsyncMock())
    
    # Set default return value for the method called by CodeParser.parse()
    lsp_adapter.start_server_and_initialize.return_value = {"status": "initialized"}
    return lsp_adapter

@pytest.fixture
def mock_lsp_adapter_constructor(mocker, mock_lsp_adapter):
    # This fixture ensures that when PythonCodeParser creates an LSPAdapter, it gets our mock_lsp_adapter.
    # The patch is active for the duration of the test that uses this fixture.
    return mocker.patch('plinko.parsers.python_parser.LSPAdapter', return_value=mock_lsp_adapter)

@pytest.fixture
def mock_code_file_path(mocker):
    m_path = mocker.create_autospec(Path, instance=True)
    m_path.exists.return_value = True
    m_path.absolute.return_value = m_path
    m_path.as_uri.return_value = "file:///fake/project/test_module.py"
    m_path.name = "test_module.py"
    m_path.stem = "test_module"
    return m_path

def _create_parser_helper(code_string, mock_code_file_path_fixture, mock_parent_parser_fixture, mock_lsp_adapter_constructor_fixture):
    # mock_lsp_adapter_constructor_fixture needs to be active when PythonCodeParser is instantiated.
    # This is ensured if it's a dependency of the test function.
    mock_code_file_path_fixture.read_text.return_value = code_string
    parser = PythonCodeParser(mock_code_file_path_fixture, mock_parent_parser_fixture)
    return parser

@pytest.mark.asyncio
async def test_basic_function_parsing_and_lsp_call(mock_parent_parser, mock_lsp_adapter, mock_lsp_adapter_constructor, mock_code_file_path, mocker):
    code = """
def func_one():
    pass

class MyClass:
    def method_a(self):
        pass
"""
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    
    # Mock Function's async_parse_with_lsp to check if it's called
    mock_func_lsp_parse = mocker.patch.object(Function, 'async_parse_with_lsp', new_callable=mocker.AsyncMock)
    
    parser.parse() 

    mock_lsp_adapter.start_server_and_initialize.assert_called_once()
    # mock_lsp_adapter.open_document.assert_called_once_with(mock_code_file_path) # Removed
    
    assert len(parser.methods) == 2
    assert "test_module.py::func_one" in parser.methods
    assert "test_module.py:MyClass:method_a" in parser.methods
    
    assert mock_func_lsp_parse.call_count == 2

@pytest.mark.asyncio
async def test_function_async_parse_call_identification(mock_parent_parser, mock_lsp_adapter, mock_lsp_adapter_constructor, mock_code_file_path):
    code = """
def my_func():
    call_one()
    another_module.call_two()
"""
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    parser._parse_file() 
    
    func_obj = parser.methods.get("test_module.py::my_func")
    assert func_obj is not None

    def mock_get_definition_side_effect(file_path, line, char):
        if line == 1: # AST line 2 for call_one()
            return [{"uri": "file:///fake/project/lib.py", "range": {"start": {"line": 10, "character": 0}}}]
        elif line == 2: # AST line 3 for another_module.call_two()
             return [{"uri": "file:///fake/project/another_module.py", "range": {"start": {"line": 5, "character": 0}}}]
        return None
    mock_lsp_adapter.get_definition.side_effect = mock_get_definition_side_effect
    
    await func_obj.async_parse_with_lsp()

    assert any("lib.call_one" in call for call in func_obj.calls)
    assert any("another_module.call_two" in call for call in func_obj.calls)

@pytest.mark.asyncio
async def test_function_async_parse_coverage_identification(mock_parent_parser, mock_lsp_adapter, mock_lsp_adapter_constructor, mock_code_file_path):
    code = """
def analyze_data():
    nailgun.utils.process()
"""
    mock_parent_parser.entities = ["nailgun"] 
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    parser._parse_file()
    func_obj = parser.methods.get("test_module.py::analyze_data")
    assert func_obj is not None

    mock_lsp_adapter.get_definition.return_value = [
        {"uri": "file:///fake/project/site-packages/nailgun/utils.py", 
         "range": {"start": {"line": 20, "character": 4}}}
    ]
    
    await func_obj.async_parse_with_lsp()
    
    assert "nailgun process" in func_obj.covers

@pytest.mark.asyncio
async def test_function_async_parse_coverage_create_on_instance(mock_parent_parser, mock_lsp_adapter, mock_lsp_adapter_constructor, mock_code_file_path):
    code = """
def create_client():
    client = nailgun.Client(config="test")
"""
    mock_parent_parser.entities = ["nailgun"]
    mock_parent_parser.create_on_instance = True 
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    parser._parse_file()
    func_obj = parser.methods.get("test_module.py::create_client")
    assert func_obj is not None

    mock_lsp_adapter.get_definition.return_value = [
        {"uri": "file:///fake/project/site-packages/nailgun/__init__.py", 
         "range": {"start": {"line": 5, "character": 0}}}
    ]
    
    await func_obj.async_parse_with_lsp()
    
    assert "nailgun Client" in func_obj.covers 
    assert "nailgun create" in func_obj.covers

@pytest.mark.asyncio
async def test_function_async_parse_unresolved_calls(mock_parent_parser, mock_lsp_adapter, mock_lsp_adapter_constructor, mock_code_file_path):
    code = """
def try_something():
    non_existent_call()
"""
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    parser._parse_file()
    func_obj = parser.methods.get("test_module.py::try_something")
    assert func_obj is not None

    mock_lsp_adapter.get_definition.return_value = None 
    
    await func_obj.async_parse_with_lsp()
    assert "UNRESOLVED:non_existent_call()" in func_obj.calls

    func_obj.calls.clear() 
    mock_lsp_adapter.get_definition.side_effect = Exception("LSP exploded")
    await func_obj.async_parse_with_lsp()
    assert "ERROR_RESOLVING:non_existent_call()" in func_obj.calls

def test_function_decorator_and_fixture_identification(mock_parent_parser, mock_lsp_adapter_constructor, mock_code_file_path): # No async needed
    code = """
import pytest

@pytest.fixture
def my_fixture():
    return 1

def test_something(my_fixture):
    assert my_fixture == 1
    
@another_decorator
def decorated_func():
    pass
"""
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    parser._parse_file() 

    fixture_func = parser.methods.get("test_module.py::my_fixture")
    test_func = parser.methods.get("test_module.py::test_something")
    decorated_f = parser.methods.get("test_module.py::decorated_func")

    assert fixture_func is not None
    assert fixture_func.is_fixture is True
    assert fixture_func.is_test is False
    assert "@pytest.fixture" in fixture_func.decs 

    assert test_func is not None
    assert test_func.is_test is True
    assert test_func.is_fixture is False
    
    assert decorated_f is not None
    assert "@another_decorator" in decorated_f.decs

@pytest.mark.asyncio
async def test_code_parser_match_fixtures(mock_parent_parser, mock_lsp_adapter, mock_lsp_adapter_constructor, mock_code_file_path, mocker):
    code = """
import pytest

@pytest.fixture
def setup_fixture():
    return {"config": "data"}

def test_with_fixture(setup_fixture):
    assert setup_fixture["config"] == "data"
"""
    parser = _create_parser_helper(code, mock_code_file_path, mock_parent_parser, mock_lsp_adapter_constructor)
    
    mock_lsp_adapter.get_definition.return_value = None 

    mock_external_fixture = mocker.Mock()
    mock_external_fixture.name = "external_fix"
    mock_external_fixture.covers = {"external_coverage"}
    mock_parent_parser.fixture_handler.fixtures = {"external_fix": mock_external_fixture}
    
    # Mock Function's async_parse_with_lsp because parse() will call it.
    # We want to control its side effects for this test or ensure it runs without error.
    async_parse_mock = mocker.patch.object(Function, 'async_parse_with_lsp', new_callable=mocker.AsyncMock)

    parser.parse() 

    fixture_func = parser.methods.get("test_module.py::setup_fixture")
    test_func = parser.methods.get("test_module.py::test_with_fixture")

    assert fixture_func is not None
    assert test_func is not None
    
    # Manually set covers as if LSP parsing (via async_parse_mock) had found something for the fixture.
    # This needs to be done *before* _match_fixtures is called by parser.parse().
    # To do this robustly, we'd need async_parse_mock to modify its instance's 'covers'.
    # For simplicity here, we'll add to covers *after* parse and then re-run _match_fixtures.
    # This is a common pattern when testing a specific method in isolation after a larger setup.
    
    fixture_func.covers.add("entity_x_from_fixture_setup")
    fixture_func.is_fixture = True # Ensure this is set if not already by _parse_file
    
    # _match_fixtures is called at the end of parser.parse().
    # If we modify fixture_func.covers *after* parser.parse() has completed,
    # we need to call _match_fixtures again to see the effect of the change.
    parser._match_fixtures()

    assert "entity_x_from_fixture_setup" in test_func.covers
    assert fixture_func in test_func.fixtures

    # Ensure async_parse_lsp was called as expected during the main parse()
    assert async_parse_mock.call_count == len(parser.methods)
