import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from lspclient import ContentType, LanguageClient, Message, server

class LSPAdapter:
    def __init__(self, project_root: Path, language_server_command: str = "pyright-langserver --stdio"):
        self.project_root = project_root
        self.language_server_command = language_server_command
        self.process: Optional[subprocess.Popen] = None
        self.client: Optional[LanguageClient] = None
        self._message_id_counter = 0

    async def start_server(self):
        """Starts the language server as a subprocess."""
        if self.process and self.process.poll() is None:
            print("LSP server already running.")
            return

        print(f"Starting LSP server with command: {self.language_server_command}")
        self.process = subprocess.Popen(
            self.language_server_command.split(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        # Create a LanguageClient instance
        # Note: The actual read/write streams will be managed by the client's methods
        self.client = LanguageClient(ContentType.JSONRPC, None, None)
        # The transport_server_init_params argument is not standard for lspclient
        # Initialization parameters are typically sent via the initialize request.

        print("LSP server process started.")

    async def initialize(self) -> Dict[str, Any]:
        """Initializes the language server."""
        if not self.client or not self.process or self.process.poll() is not None:
            raise ConnectionError("LSP server is not running.")

        self._message_id_counter += 1
        initialize_params = {
            "processId": self.process.pid,
            "rootUri": self.project_root.as_uri(),
            "capabilities": {
                "textDocument": {
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "synchronization": {"dynamicRegistration": True, "willSave": False, "didSave": False, "willSaveWaitUntil": False},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True, "commitCharactersSupport": True, "documentationFormat": ["markdown", "plaintext"], "deprecatedSupport": True, "insertReplaceSupport": True}, "contextSupport": True},
                    "signatureHelp": {"dynamicRegistration": True, "signatureInformation": {"documentationFormat": ["markdown", "plaintext"]}},
                    "declaration": {"dynamicRegistration": True, "linkSupport": True},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "typeDefinition": {"dynamicRegistration": True, "linkSupport": True},
                    "implementation": {"dynamicRegistration": True, "linkSupport": True}
                },
                "workspace": {"applyEdit": True, "workspaceEdit": {"documentChanges": True}}
            },
            "trace": "off",
        }
        
        response = await self._send_request("initialize", initialize_params)
        # After initialize, send initialized notification
        await self._send_notification("initialized", {})
        print("LSP server initialized.")
        return response

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sends a request to the LSP server and returns the response."""
        if not self.client or not self.process or self.process.stdin is None or self.process.stdout is None:
            raise ConnectionError("LSP server not running or streams not available.")

        self._message_id_counter += 1
        message = Message(jsonrpc="2.0", id=self._message_id_counter, method=method, params=params)
        
        request_json = json.dumps(message.data).encode('utf-8')
        header = f"Content-Length: {len(request_json)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n".encode('utf-8')
        
        self.process.stdin.write(header)
        self.process.stdin.write(request_json)
        self.process.stdin.flush()
        
        # Read response
        # This is a simplified way to read; a robust client would handle headers and content length properly
        line = self.process.stdout.readline()
        if not line:
            raise ConnectionError("No response from LSP server (header).")
        content_length_header = line.decode('utf-8').strip()
        if not content_length_header.startswith("Content-Length:"):
            # Log stderr for debugging
            if self.process.stderr:
                err_output = self.process.stderr.read()
                if err_output:
                     print(f"LSP Server stderr while reading header: {err_output.decode('utf-8', errors='ignore')}")
            raise ValueError(f"Invalid response header from LSP server: {content_length_header}")

        content_length = int(content_length_header.split(":")[1].strip())
        
        # Read the blank line separating header and content
        self.process.stdout.readline() 
        
        response_json = self.process.stdout.read(content_length)
        response_data = json.loads(response_json.decode('utf-8'))
        
        if 'error' in response_data:
            raise RuntimeError(f"LSP Error: {response_data['error']}")
        return response_data.get('result', {})

    async def _send_notification(self, method: str, params: Dict[str, Any]):
        """Sends a notification to the LSP server."""
        if not self.client or not self.process or not self.process.stdin:
            raise ConnectionError("LSP server not running or stdin not available.")

        message = Message(jsonrpc="2.0", method=method, params=params) # No ID for notifications
        notification_json = json.dumps(message.data).encode('utf-8')
        header = f"Content-Length: {len(notification_json)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n".encode('utf-8')

        self.process.stdin.write(header)
        self.process.stdin.write(notification_json)
        self.process.stdin.flush()
        print(f"Sent notification: {method}")

    async def open_document(self, file_path: Path):
        """Notifies the LSP server that a document has been opened."""
        uri = file_path.as_uri()
        text = file_path.read_text()
        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "python",
                "version": 1,
                "text": text
            }
        })
        print(f"Document opened: {file_path}")

    async def get_definition(self, file_path: Path, line: int, character: int) -> Dict[str, Any]:
        """Requests the definition of a symbol at a given location."""
        uri = file_path.as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character}
        }
        return await self._send_request("textDocument/definition", params)

    async def get_references(self, file_path: Path, line: int, character: int, include_declaration: bool = True) -> Dict[str, Any]:
        """Requests all references to a symbol at a given location."""
        uri = file_path.as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration}
        }
        return await self._send_request("textDocument/references", params)

    async def shutdown(self):
        """Shuts down the language server."""
        if self.client and self.process and self.process.poll() is None:
            await self._send_request("shutdown", {})
            print("LSP server shutdown requested.")
            # Server should exit after shutdown, but give it a moment
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print("LSP server did not exit after shutdown, terminating.")
                self.process.terminate()
            self.client = None
            self.process = None
        else:
            print("LSP server not running or already shut down.")

    async def close(self):
        """Closes the connection to the language server and terminates the process."""
        if self.client:
            await self.shutdown() # Ensure graceful shutdown first
        if self.process and self.process.poll() is None:
            print("Terminating LSP server process.")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("LSP server did not terminate in time, killing.")
                self.process.kill()
        self.client = None
        self.process = None
        print("LSP Adapter closed.")

    async def main():
        # Example Usage (for testing purposes)
        # Replace with your actual project root and file paths
        project_path = Path(__file__).parent.parent # Assuming lsp_adapter.py is in plinko/
        adapter = LSPAdapter(project_root=project_path)
        
        try:
            await adapter.start_server()
            await adapter.initialize()
            
            # Example: Open a document (replace with an actual file in your project)
            # test_file = project_path / "some_test_file.py" 
            # if not test_file.exists():
            #    test_file.write_text("def foo():\n  pass\n\nfoo()")

            # await adapter.open_document(test_file)
            
            # Example: Get definition (replace with actual symbol location)
            # try:
            #    definition = await adapter.get_definition(test_file, 2, 2) # line 2, char 2 (for 'foo' call)
            #    print(f"Definition: {definition}")
            # except Exception as e:
            #    print(f"Error getting definition: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            await adapter.close()

    if __name__ == "__main__":
        asyncio.run(main())
