import asyncio
import json
import subprocess
from pathlib import Path
import io
import pytest

# Assuming lsp_adapter.py is in plinko directory and plinko is in PYTHONPATH
from plinko.lsp_adapter import LSPAdapter

# Helper to create LSP responses
def create_lsp_response(id, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": id}
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    response_json = json.dumps(response).encode('utf-8')
    header = f"Content-Length: {len(response_json)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n".encode('utf-8')
    return header + response_json

def create_lsp_notification(method, params):
    notification = {"jsonrpc": "2.0", "method": method, "params": params}
    notification_json = json.dumps(notification).encode('utf-8')
    header = f"Content-Length: {len(notification_json)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n".encode('utf-8')
    return header + notification_json

@pytest.fixture
def project_root():
    return Path("/fake/project")

@pytest.fixture
def stdin_buffer():
    return io.BytesIO()

@pytest.fixture
def stdout_buffer():
    return io.BytesIO()

@pytest.fixture
def mock_proc(mocker, stdin_buffer, stdout_buffer):
    proc = mocker.Mock(spec=subprocess.Popen)
    
    # Configure stdin
    async def stdin_write(data):
        stdin_buffer.write(data)
        return len(data)
    async def stdin_drain():
        pass
    proc.stdin = mocker.AsyncMock(spec=asyncio.StreamWriter)
    proc.stdin.write = stdin_write
    proc.stdin.drain = stdin_drain

    # Configure stdout
    async def stdout_readline():
        stdout_buffer.seek(0)
        line = stdout_buffer.readline()
        remaining_content = stdout_buffer.read()
        stdout_buffer.seek(0)
        stdout_buffer.write(remaining_content)
        stdout_buffer.truncate()
        stdout_buffer.seek(0)
        return line
    async def stdout_read(n):
        stdout_buffer.seek(0)
        content = stdout_buffer.read(n)
        remaining_content = stdout_buffer.read()
        stdout_buffer.seek(0)
        stdout_buffer.write(remaining_content)
        stdout_buffer.truncate()
        stdout_buffer.seek(0)
        return content
    proc.stdout = mocker.AsyncMock(spec=asyncio.StreamReader)
    proc.stdout.readline = stdout_readline
    proc.stdout.read = stdout_read
    
    proc.stderr = mocker.AsyncMock(spec=asyncio.StreamReader) # Keep stderr simple for now
    proc.stderr.read.return_value = b"" # Default empty stderr
    proc.poll = mocker.Mock(return_value=None) # Simulate running
    proc.pid = 12345
    return proc

@pytest.fixture
def mock_popen_constructor(mocker, mock_proc):
    return mocker.patch('subprocess.Popen', return_value=mock_proc)

@pytest.fixture
async def adapter(project_root, mock_popen_constructor, stdout_buffer): # Include stdout_buffer for teardown
    # mock_popen_constructor ensures Popen is patched before adapter is created
    adapter_instance = LSPAdapter(project_root=project_root)
    yield adapter_instance
    
    # Teardown
    if adapter_instance and adapter_instance.client:
        try:
            # Simulate server responding to shutdown if necessary
            # This helps adapter.shutdown() complete without hanging if it expects a response
            # Use a plausible ID; _message_id_counter might be tricky to get here if not set yet
            # or if the test failed before any messages were sent.
            # A more robust way might be to have the mock_proc handle this.
            # For simplicity, assume if client exists, a message might have been sent.
            if adapter_instance._message_id_counter > 0 :
                 stdout_buffer.write(create_lsp_response(adapter_instance._message_id_counter +1, {}))
            else: # if no messages sent, maybe ID 1 if shutdown is the first request
                 stdout_buffer.write(create_lsp_response(1, {}))

            await adapter_instance.shutdown()
        except Exception:
            pass 
    if adapter_instance and adapter_instance.process:
         await adapter_instance.close()


def get_written_json_requests(stdin_buffer_fixture):
    stdin_buffer_fixture.seek(0)
    content = stdin_buffer_fixture.read().decode('utf-8')
    requests = []
    # Split by the double CRLF that separates header and body, and then filter out empty parts
    raw_messages = filter(None, content.split("Content-Length:"))
    for raw_msg in raw_messages:
        # Each raw_msg will start with "<length>\r\nContent-Type: ...\r\n\r\n<json_body>"
        # We need to find the JSON part.
        try:
            # Find the start of the JSON body
            json_start_index = raw_msg.index("\r\n\r\n") + 4
            json_part = raw_msg[json_start_index:]
            if json_part:
                requests.append(json.loads(json_part))
        except (ValueError, json.JSONDecodeError):
            # If "\r\n\r\n" is not found or JSON is malformed, skip this part.
            # This can happen if the buffer contains incomplete messages or just headers.
            pass
    return requests

@pytest.mark.asyncio
async def test_start_server_and_initialize(adapter, mock_popen_constructor, project_root, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    mock_popen_constructor.assert_called_once_with(
        adapter.language_server_command.split(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert adapter.process is not None
    assert adapter.client is not None

    init_response_payload = {"capabilities": {"hoverProvider": True}}
    stdout_buffer.write(create_lsp_response(1, init_response_payload)) 
    
    response = await adapter.initialize()
    assert response == init_response_payload

    requests = get_written_json_requests(stdin_buffer)
    assert len(requests) == 2
    assert requests[0]['method'] == "initialize"
    assert requests[0]['params']['rootUri'] == project_root.as_uri()
    assert requests[1]['method'] == "initialized"
    assert requests[1]['params'] == {}

@pytest.mark.asyncio
async def test_open_document(adapter, project_root, stdout_buffer, stdin_buffer, mocker):
    mocker.patch('pathlib.Path.read_text', return_value="def hello(): pass")
    
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # Init response
    await adapter.initialize()

    test_file = project_root / "test_file.py"
    await adapter.open_document(test_file)
    
    Path.read_text.assert_called_once() # Check if the mock for read_text was called
    requests = get_written_json_requests(stdin_buffer)
    # requests[0] is initialize, requests[1] is initialized notification
    did_open_notification = requests[2] 
    assert did_open_notification['method'] == "textDocument/didOpen"
    assert did_open_notification['params']['textDocument']['uri'] == test_file.as_uri()
    assert did_open_notification['params']['textDocument']['text'] == "def hello(): pass"

@pytest.mark.asyncio
async def test_get_definition(adapter, project_root, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    test_file = project_root / "test_file.py"
    line, char = 5, 10

    def_response_payload = {"uri": test_file.as_uri(), "range": {"start": {"line": 1, "character": 1}}}
    # ID for initialize is 1, initialized is notification, next request ID is 2 (from adapter._message_id_counter)
    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, def_response_payload))
    
    response = await adapter.get_definition(test_file, line, char)
    assert response == def_response_payload
    
    requests = get_written_json_requests(stdin_buffer)
    definition_request = requests[-1] 
    assert definition_request['method'] == "textDocument/definition"
    assert definition_request['params']['textDocument']['uri'] == test_file.as_uri()
    assert definition_request['params']['position'] == {"line": line, "character": char}

    # Test empty response
    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, [])) 
    response_empty = await adapter.get_definition(test_file, line, char)
    assert response_empty == []

    # Test error response
    error_payload = {"code": -32000, "message": "Definition error"}
    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, error=error_payload))
    with pytest.raises(RuntimeError, match="LSP Error:.*Definition error"):
        await adapter.get_definition(test_file, line, char)

@pytest.mark.asyncio
async def test_get_references(adapter, project_root, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    test_file = project_root / "test_file.py"
    line, char = 3, 8

    ref_response_payload = [{"uri": test_file.as_uri(), "range": {"start": {"line": 2, "character": 2}}}]
    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, ref_response_payload))
    
    response = await adapter.get_references(test_file, line, char)
    assert response == ref_response_payload

    requests = get_written_json_requests(stdin_buffer)
    references_request = requests[-1]
    assert references_request['method'] == "textDocument/references"
    assert references_request['params']['textDocument']['uri'] == test_file.as_uri()
    assert references_request['params']['position'] == {"line": line, "character": char}
    assert references_request['params']['context']['includeDeclaration'] is True

@pytest.mark.asyncio
async def test_shutdown_and_close(adapter, mock_proc, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, {})) # shutdown response
    await adapter.shutdown()

    requests = get_written_json_requests(stdin_buffer)
    shutdown_request = requests[-1]
    assert shutdown_request['method'] == "shutdown"
    
    mock_proc.terminate.assert_not_called() 
    mock_proc.poll.return_value = 0 # Simulate process exited after shutdown
    
    await adapter.close() 
    mock_proc.terminate.assert_not_called()
    assert adapter.process is None

@pytest.mark.asyncio
async def test_shutdown_timeout_and_terminate(adapter, mock_proc, stdout_buffer, stdin_buffer, mocker):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, {})) # shutdown response
    
    # Patch Popen.wait on the specific mock_proc instance
    mocker.patch.object(mock_proc, 'wait', side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=0.1))
    
    await adapter.shutdown() 

    mock_proc.wait.assert_called_once()
    mock_proc.terminate.assert_called_once()
    
    mock_proc.poll.return_value = 1 # Simulate terminated
    await adapter.close()
    assert adapter.process is None

@pytest.mark.asyncio
async def test_request_error_handling(adapter, project_root, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    error_payload = {"code": -32600, "message": "Invalid Request"}
    stdout_buffer.write(create_lsp_response(adapter._message_id_counter + 1, error=error_payload))
    
    with pytest.raises(RuntimeError, match="LSP Error:.*Invalid Request"):
        await adapter.get_definition(project_root / "test.py", 0, 0)

@pytest.mark.asyncio
async def test_malformed_response_json(adapter, project_root, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    malformed_json_response = "Content-Length: 10\r\n\r\n{oops".encode('utf-8')
    stdout_buffer.write(malformed_json_response)
    
    with pytest.raises(json.JSONDecodeError):
        await adapter.get_definition(project_root / "test.py", 0, 0)

@pytest.mark.asyncio
async def test_malformed_response_header(adapter, project_root, stdout_buffer, stdin_buffer):
    await adapter.start_server()
    stdout_buffer.write(create_lsp_response(1, {"capabilities": {}})) # initialize
    await adapter.initialize()

    # Simulate stderr output for debugging the test itself
    mock_proc_instance = adapter.process # Get the actual mock_proc used by the adapter
    mock_proc_instance.stderr.read.return_value = b"Some error from LSP server stderr"


    malformed_header_response = "NotContentLength: 10\r\n\r\n{}".encode('utf-8')
    stdout_buffer.write(malformed_header_response)
    
    with pytest.raises(ValueError, match="Invalid response header from LSP server"):
        await adapter.get_definition(project_root / "test.py", 0, 0)

@pytest.mark.asyncio
async def test_server_already_running(adapter, mock_popen_constructor):
    await adapter.start_server() # First start
    mock_popen_constructor.assert_called_once()
    
    await adapter.start_server() # Second start
    mock_popen_constructor.assert_called_once() # Should not be called again
