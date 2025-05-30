import asyncio
from pathlib import Path
import pytest

from plinko.lsp_adapter import LSPAdapter
# Assuming multilspy types might be needed for mock responses, or specific structures.
from multilspy import LanguageServer as MultilspyLanguageServer 
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
# from multilspy import multilspy_types # If specific response types are needed for mocks

@pytest.fixture
def project_root():
    return Path("/fake/project")

@pytest.fixture
def mock_multilspy_logger(mocker):
    # Create a basic mock for MultilspyLogger if its methods are called by LSPAdapter
    # For now, LSPAdapter just instantiates it.
    return mocker.Mock(spec=MultilspyLogger)

@pytest.fixture
def mock_multilspy_config(mocker):
    # Create a basic mock for MultilspyConfig
    return mocker.Mock(spec=MultilspyConfig)

@pytest.fixture
def mock_language_server_instance(mocker):
    """Mocks an instance of multilspy.LanguageServer."""
    client_mock = mocker.AsyncMock(spec=MultilspyLanguageServer)
    
    # Mock the async context manager for client.start_server()
    mock_server_context = mocker.AsyncMock()
    # __aenter__ should return the context itself or a relevant object if LSPAdapter uses it
    mock_server_context.__aenter__.return_value = None # Or mock specific object if needed
    client_mock.start_server.return_value = mock_server_context
    
    # Mock the async context manager for client.open_file()
    mock_file_context = mocker.AsyncMock()
    mock_file_context.__aenter__.return_value = None # Or mock specific object
    client_mock.open_file.return_value = mock_file_context
    
    client_mock.request_definition = mocker.AsyncMock()
    client_mock.request_references = mocker.AsyncMock()
    
    return client_mock

@pytest.fixture
def patch_multilspy_creators(mocker, mock_language_server_instance, mock_multilspy_logger, mock_multilspy_config):
    """
    Patches MultilspyLogger, MultilspyConfig.from_dict, and LanguageServer.create 
    to return controlled mocks.
    """
    mocker.patch('plinko.lsp_adapter.MultilspyLogger', return_value=mock_multilspy_logger)
    mocker.patch('plinko.lsp_adapter.MultilspyConfig.from_dict', return_value=mock_multilspy_config)
    mocker.patch('plinko.lsp_adapter.LanguageServer.create', return_value=mock_language_server_instance)

@pytest.fixture
async def adapter_fixture(project_root, patch_multilspy_creators, mock_language_server_instance):
    """
    Provides an LSPAdapter instance with multilspy dependencies mocked.
    Includes teardown for shutdown_server.
    """
    # patch_multilspy_creators ensures that when LSPAdapter is created,
    # it uses the mocked LanguageServer.create etc.
    adapter_instance = LSPAdapter(project_root=project_root)
    adapter_instance.client = mock_language_server_instance # Ensure the instance uses our mock client
    
    yield adapter_instance
    
    # Teardown: Attempt to shutdown server if it was marked active
    if adapter_instance._is_server_active:
        await adapter_instance.shutdown_server()

@pytest.mark.asyncio
async def test_init_creates_multilspy_client(adapter_fixture, project_root, mock_language_server_instance):
    # The patch_multilspy_creators fixture (used by adapter_fixture) handles this.
    # We can assert that LanguageServer.create was called (it's implicitly tested by adapter_fixture setup)
    # And that adapter_fixture.client is our mock_language_server_instance
    from plinko.lsp_adapter import LanguageServer # Get the one that was patched
    LanguageServer.create.assert_called_once()
    assert adapter_fixture.client == mock_language_server_instance
    assert adapter_fixture.project_root == project_root
    # Check if config was called with "python"
    from plinko.lsp_adapter import MultilspyConfig
    MultilspyConfig.from_dict.assert_called_with({"code_language": "python", "trace_lsp_communication": False})


@pytest.mark.asyncio
async def test_start_server_and_initialize(adapter_fixture, mock_language_server_instance):
    response = await adapter_fixture.start_server_and_initialize()
    
    # Check that multilspy client's start_server context manager was entered
    mock_language_server_instance.start_server.assert_called_once()
    mock_language_server_instance.start_server.return_value.__aenter__.assert_called_once()
    
    assert adapter_fixture._is_server_active is True
    assert response == {"status": "initialized"}

    # Test starting again (should be idempotent based on LSPAdapter logic)
    await adapter_fixture.start_server_and_initialize()
    mock_language_server_instance.start_server.assert_called_once() # Should not be called again

@pytest.mark.asyncio
async def test_open_document(adapter_fixture, project_root, mock_language_server_instance, mocker):
    await adapter_fixture.start_server_and_initialize() # Server must be active

    test_file = project_root / "module" / "file.py"
    expected_relative_path = "module/file.py" # Path.relative_to gives POSIX paths

    # For Windows compatibility in test assertion if Path objects are used directly
    # expected_relative_path_obj = Path("module") / "file.py"


    await adapter_fixture.open_document(test_file)
    
    # Check that multilspy client's open_file context manager was called with correct relative path
    # The actual call in LSPAdapter is `async with self.client.open_file(str(relative_file_path))`.
    # So, we check if `open_file` was called, and then if its `__aenter__` was called.
    mock_language_server_instance.open_file.assert_called_once_with(str(expected_relative_path))
    mock_language_server_instance.open_file.return_value.__aenter__.assert_called_once()
    mock_language_server_instance.open_file.return_value.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_get_definition(adapter_fixture, project_root, mock_language_server_instance):
    await adapter_fixture.start_server_and_initialize()

    test_file = project_root / "src/code.py"
    expected_relative_path = "src/code.py"
    line, char = 5, 10
    
    mock_response = [{"uri": "file:///fake/project/src/definition.py", "range": {"start": {"line": 1, "character": 1}}}]
    mock_language_server_instance.request_definition.return_value = mock_response
    
    response = await adapter_fixture.get_definition(test_file, line, char)
    
    mock_language_server_instance.request_definition.assert_called_once_with(str(expected_relative_path), line, char)
    assert response == mock_response

    # Test error handling
    mock_language_server_instance.request_definition.side_effect = Exception("Multilspy definition error")
    with pytest.raises(RuntimeError, match="LSP Error from multilspy: Multilspy definition error"):
        await adapter_fixture.get_definition(test_file, line, char)

@pytest.mark.asyncio
async def test_get_references(adapter_fixture, project_root, mock_language_server_instance):
    await adapter_fixture.start_server_and_initialize()

    test_file = project_root / "another.py"
    expected_relative_path = "another.py"
    line, char = 3, 8
    
    mock_response = [{"uri": test_file.as_uri(), "range": {"start": {"line": 2, "character": 2}}}]
    mock_language_server_instance.request_references.return_value = mock_response
        
    response = await adapter_fixture.get_references(test_file, line, char, include_declaration=False) # Test with include_declaration=False first
    
    mock_language_server_instance.request_references.assert_called_once_with(str(expected_relative_path), line, char)
    assert response == mock_response
    
    # Test include_declaration=True (should print warning but still call)
    mock_language_server_instance.request_references.reset_mock() # Reset for next call
    await adapter_fixture.get_references(test_file, line, char, include_declaration=True)
    mock_language_server_instance.request_references.assert_called_once_with(str(expected_relative_path), line, char)


@pytest.mark.asyncio
async def test_shutdown_server(adapter_fixture, mock_language_server_instance):
    # Start the server first
    await adapter_fixture.start_server_and_initialize()
    assert adapter_fixture._is_server_active is True
    assert adapter_fixture._server_context is not None
    
    # Get the mock for the context manager returned by start_server()
    server_context_mock = mock_language_server_instance.start_server.return_value

    await adapter_fixture.shutdown_server()
    
    server_context_mock.__aexit__.assert_called_once()
    assert adapter_fixture._is_server_active is False
    assert adapter_fixture._server_context is None

    # Test shutting down when not active
    server_context_mock.__aexit__.reset_mock()
    await adapter_fixture.shutdown_server() # Should do nothing and not error
    server_context_mock.__aexit__.assert_not_called()


@pytest.mark.asyncio
async def test_file_not_relative_to_project_root(adapter_fixture):
    await adapter_fixture.start_server_and_initialize()
    
    # Path outside the mocked project_root
    non_relative_file = Path("/other/place/file.py")

    with pytest.raises(ValueError, match=f"File path {non_relative_file} must be relative to project root {adapter_fixture.project_root} for multilspy."):
        await adapter_fixture.open_document(non_relative_file)
    
    with pytest.raises(ValueError, match=f"File path {non_relative_file} must be relative to project root {adapter_fixture.project_root} for multilspy."):
        await adapter_fixture.get_definition(non_relative_file, 0, 0)

    with pytest.raises(ValueError, match=f"File path {non_relative_file} must be relative to project root {adapter_fixture.project_root} for multilspy."):
        await adapter_fixture.get_references(non_relative_file, 0, 0)

# Removed tests:
# - test_request_error_handling (covered by specific request tests)
# - test_malformed_response_json (multilspy handles this layer)
# - test_malformed_response_header (multilspy handles this layer)
# - test_shutdown_timeout_and_terminate (multilspy handles process management)
# - test_server_already_running (LSPAdapter.start_server_and_initialize has basic check, 
#   and multilspy might have its own idempotency for start_server call)
# The old `adapter` fixture's teardown and the complex subprocess mocking fixtures are also gone.
# The new `adapter_fixture` handles teardown via `shutdown_server`.
