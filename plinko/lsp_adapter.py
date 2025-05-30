import asyncio
from pathlib import Path
# Typing imports are removed as per user feedback to avoid adding type annotations.
# from typing import Any, Dict, List, Optional 

# Imports for multilspy
from multilspy import LanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
# multilspy_types contains TypedDicts, which are structurally similar to dicts at runtime.
from multilspy import multilspy_types 

class LSPAdapter:
    def __init__(self, project_root: Path, language_server_command: str = "pyright-langserver --stdio"):
        """
        Initializes the LSPAdapter.
        Note: The `language_server_command` is currently not directly used by `multilspy`
        as it uses a pre-configured server for Python (typically jedi-language-server).
        """
        self.project_root = project_root
        # The language_server_command is noted but not passed to Multilspy's LanguageServer.create for Python.
        self.logger_instance = MultilspyLogger() # Basic logger
        self.config = MultilspyConfig.from_dict({"code_language": "python", "trace_lsp_communication": False})
        
        # repository_root_path must be an absolute path string
        abs_project_root = str(self.project_root.resolve())
        self.client: LanguageServer = LanguageServer.create(self.config, self.logger_instance, abs_project_root)
        
        self._server_context = None # To store the async context from client.start_server()
        self._is_server_active = False # Flag to track if server context is active

    async def start_server_and_initialize(self):
        """
        Starts the Language Server using multilspy.
        The actual LSP initialize request is handled by multilspy when its server starts.
        """
        if self._is_server_active:
            print("LSP server context already active.")
            return

        if not self.client:
            raise ConnectionError("Multilspy client not initialized.")

        try:
            print(f"Starting LSP server via multilspy for project: {self.project_root}")
            # Enter the async context manager provided by multilspy
            self._server_context = self.client.start_server()
            await self._server_context.__aenter__()
            self._is_server_active = True
            print("LSP server started and initialized via multilspy.")
            # multilspy doesn't directly return capabilities here in a simple way.
            # For Plinko's current usage, this was not essential.
            return {"status": "initialized"} 
        except Exception as e:
            self._is_server_active = False # Ensure flag is reset on error
            print(f"Error starting multilspy server: {e}")
            # Propagate the error or handle it as per Plinko's requirements
            raise ConnectionError(f"Failed to start and initialize multilspy server: {e}")


    async def open_document(self, file_path: Path):
        """
        Notifies the LSP server that a document has been opened.
        Uses multilspy's open_file context manager.
        """
        if not self._is_server_active or not self.client:
            raise ConnectionError("LSP server is not active. Call start_server_and_initialize first.")

        try:
            # multilspy expects a relative path string from the project root
            relative_file_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            # If file_path is not within project_root, multilspy might handle absolute paths
            # or this indicates an issue. For now, we assume relative path is expected.
            print(f"Warning: File {file_path} may not be relative to project root {self.project_root}. Using absolute path.")
            # multilspy's open_file actually takes relative path, so this will likely fail if not relative.
            # The original LSPAdapter used URI, which is absolute.
            # Let's check how multilspy's open_file handles this.
            # From multilspy source: uses str(PurePath(self.repository_root_path, relative_file_path))
            # So, it strictly needs a path relative to the repository_root_path.
            raise ValueError(f"File path {file_path} must be relative to project root {self.project_root} for multilspy.")

        print(f"Opening document: {relative_file_path} via multilspy")
        try:
            # open_file is a context manager. It sends didOpen and didClose.
            async with self.client.open_file(relative_file_path):
                # The file is considered open within this block for any requests.
                # If we need to keep it open beyond one request, this model needs adjustment,
                # but for Plinko's get_definition, it's opened per request.
                pass
            print(f"Document {relative_file_path} processed (opened and closed) by multilspy.")
        except Exception as e:
            print(f"Error during multilspy open_file for {relative_file_path}: {e}")
            raise

    async def get_definition(self, file_path: Path, line: int, character: int):
        """
        Requests the definition of a symbol at a given location using multilspy.
        Line and character are 0-based.
        """
        if not self._is_server_active or not self.client:
            raise ConnectionError("LSP server is not active.")

        try:
            relative_file_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            raise ValueError(f"File path {file_path} must be relative to project root {self.project_root} for multilspy.")

        print(f"Requesting definition for {relative_file_path} at L{line}:C{character} via multilspy")
        try:
            # multilspy's request_definition handles opening/closing the file internally using its context manager.
            response = await self.client.request_definition(relative_file_path, line, character)
            
            # The response is List[multilspy_types.Location].
            # multilspy_types.Location is a TypedDict, so it's already a list of dicts.
            # Ensure keys are what Plinko expects (uri, range). 'uri' is present.
            # 'range' is present: {"start": {"line":..., "character":...}, "end":{...}}
            # This matches the typical LSP structure.
            return response
        except Exception as e:
            print(f"Error during multilspy request_definition: {e}")
            # Adapt to Plinko's error handling or re-raise
            raise RuntimeError(f"LSP Error from multilspy: {e}")


    async def get_references(self, file_path: Path, line: int, character: int, include_declaration: bool = True):
        """
        Requests all references to a symbol at a given location using multilspy.
        Note: multilspy's request_references has `includeDeclaration` defaulting to False.
        """
        if not self._is_server_active or not self.client:
            raise ConnectionError("LSP server is not active.")
        
        try:
            relative_file_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            raise ValueError(f"File path {file_path} must be relative to project root {self.project_root} for multilspy.")

        print(f"Requesting references for {relative_file_path} at L{line}:C{character} via multilspy")
        try:
            # multilspy's request_references also handles file open/close.
            # It does not directly expose includeDeclaration in its simplified request_references.
            # Need to check if this is available or if we need to use a more generic send_request if multilspy supports it.
            # Looking at multilspy source, request_references hardcodes "includeDeclaration": False.
            # This is a deviation from the old adapter. For now, we accept this limitation.
            if include_declaration:
                print("Warning: multilspy's request_references currently does not support includeDeclaration=True easily. Proceeding with includeDeclaration=False.")
            
            response = await self.client.request_references(relative_file_path, line, character)
            return response
        except Exception as e:
            print(f"Error during multilspy request_references: {e}")
            raise RuntimeError(f"LSP Error from multilspy: {e}")

    async def shutdown_server(self):
        """
        Shuts down the language server managed by multilspy.
        This involves exiting the async context manager.
        """
        if not self._server_context:
            print("LSP server context not established or already shut down.")
            return

        if self._is_server_active:
            print("Shutting down LSP server via multilspy.")
            try:
                await self._server_context.__aexit__(None, None, None)
                print("LSP server shutdown complete.")
            except Exception as e:
                print(f"Error during multilspy server context exit: {e}")
                # Decide if we need to raise an error or just log
            finally:
                self._is_server_active = False
                self._server_context = None
        else:
            print("LSP server was not active.")
            self._server_context = None # Ensure it's cleared

    # Removed original start_server, initialize, _send_request, _send_notification, shutdown, close methods
    # as their responsibilities are now handled by multilspy or the new methods.

    @staticmethod
    async def example_main(): # Renamed from main to avoid confusion if this file is run
        # Example Usage (for testing purposes)
        # Ensure a Python project exists at this path for jedi-language-server to work.
        # For example, create a dummy project root with a sample .py file.
        project_path = Path(__file__).parent.parent / "dummy_project" 
        project_path.mkdir(exist_ok=True)
        test_py_file = project_path / "sample.py"
        test_py_file.write_text("def hello_world():\n    pass\n\nhello_world()")

        # Using a file known to be in the project for multilspy.
        # Path for open_document and requests should be relative to project_root.
        file_in_project = Path("sample.py") 

        adapter = LSPAdapter(project_root=project_path)
        
        try:
            await adapter.start_server_and_initialize()
            
            # multilspy's open_file is a context manager. For Plinko's current usage,
            # definition/references requests handle this internally.
            # If we needed to explicitly keep a file open for multiple operations:
            # async with adapter.client.open_file(str(file_in_project)):
            #    definition = await adapter.get_definition(file_in_project, 2, 2) # Line 3, char 3 in 1-based
            
            # Test get_definition (line/char are 0-based for LSP)
            # For "hello_world()" call on line 3 (0-indexed 2)
            print(f"Getting definition for {file_in_project} L2:C0")
            definition = await adapter.get_definition(file_in_project, 2, 0) 
            print(f"Definition: {definition}")

        except Exception as e:
            print(f"An error occurred in example_main: {e}")
        finally:
            await adapter.shutdown_server()

if __name__ == "__main__":
    # To run this example, ensure dummy_project and sample.py are set up.
    # Also, `multilspy` and `jedi-language-server` must be installed.
    # Example:
    # (cd .. && python -m venv .venv && . .venv/bin/activate && pip install multilspy && pip install .)
    # python -m plinko.lsp_adapter
    
    # Setup dummy project for the example to run
    project_path_main = Path(__file__).parent.parent / "dummy_project" 
    project_path_main.mkdir(exist_ok=True)
    test_py_file_main = project_path_main / "sample.py"
    if not test_py_file_main.exists(): # Create only if it doesn't exist
        test_py_file_main.write_text("def hello_world():\n    pass\n\nhello_world()\n")
        print(f"Created dummy file: {test_py_file_main}")
    
    asyncio.run(LSPAdapter.example_main())

# Note on original `language_server_command`:
# The `language_server_command` parameter (e.g., "pyright-langserver --stdio")
# is not directly used when creating `LanguageServer` via `LanguageServer.create`
# for Python, as `multilspy` defaults to `jedi-language-server` and manages its execution.
# If `pyright-langserver` is a strict requirement, `multilspy` would need modification
# or a custom `LanguageServer` subclass implementation that uses `pyright-langserver`.
# This refactoring adheres to using `multilspy`'s standard mechanism for Python.I have refactored `plinko/lsp_adapter.py` to use the `multilspy` library.

Here's a summary of the key changes:

1.  **Imports**:
    *   Replaced `lspclient`, `subprocess`, and `json` with `multilspy.LanguageServer`, `MultilspyConfig`, `MultilspyLogger`, and `multilspy_types`.

2.  **`__init__`**:
    *   Initializes `MultilspyLogger`, `MultilspyConfig` (configured for `python` language and LSP communication tracing disabled for now).
    *   Creates a `LanguageServer` client instance using `LanguageServer.create()`. The `repository_root_path` is passed as an absolute string.
    *   The `language_server_command` parameter is retained but a comment clarifies that `multilspy` will use its default for Python (jedi-language-server).
    *   Removed old process and lspclient-specific members (`self.process`, `self.client`, `self._message_id_counter`).
    *   Added `self._server_context` to manage the async context from `multilspy`'s `client.start_server()` and `self._is_server_active` flag.

3.  **`start_server_and_initialize()`**:
    *   This new method replaces the separate `start_server` and `initialize` methods.
    *   It enters the async context provided by `self.client.start_server()`, which handles the LSP initialization internally.
    *   Stores the context in `self._server_context` and sets `self._is_server_active = True`.

4.  **`shutdown_server()`**:
    *   This new method replaces the old `shutdown()` and `close()`.
    *   It exits the stored `_server_context` using `__aexit__`, which triggers `multilspy` to shut down the LSP server gracefully.

5.  **`open_document()`**:
    *   This method now uses `multilspy`'s `async with self.client.open_file(relative_file_path): pass`.
    *   It converts the absolute `file_path` to a relative path string with respect to the `project_root`, as required by `multilspy`.
    *   `multilspy` handles sending `textDocument/didOpen` and `textDocument/didClose` internally within the `open_file` context. For Plinko's use case where definition/references are requested one-off, this means the file is opened and closed around each request by `multilspy`'s `request_definition`/`request_references` methods.

6.  **`get_definition()`**:
    *   Calculates the relative file path.
    *   Calls `await self.client.request_definition(relative_file_path, line, character)`.
    *   The response from `multilspy` (`List[multilspy_types.Location]`) is already a list of dictionary-like objects and is structurally compatible with the expected return type.

7.  **`get_references()`**:
    *   Similar to `get_definition`, it calls `await self.client.request_references(...)`.
    *   A note is added that `multilspy`'s current `request_references` for Python (jedi) hardcodes `includeDeclaration: False`, which is a deviation from the old adapter's capability.

8.  **Removed Methods**:
    *   `_send_request`, `_send_notification`, the original `start_server`, `initialize`, `shutdown`, and `close` methods were removed as their functionality is either subsumed by `multilspy` or replaced by the new methods.

9.  **Example Usage (`example_main`)**:
    *   The static `main` method was renamed to `example_main` and updated to demonstrate the new API:
        *   Uses `adapter.start_server_and_initialize()` and `adapter.shutdown_server()`.
        *   Shows how to call `get_definition`.
        *   Includes setup for a dummy project and file for `jedi-language-server` to analyze, as it requires a valid Python environment.

**Important Consideration**:
The refactored adapter now uses `jedi-language-server` (the default for Python in `multilspy`) instead of the previously specified `pyright-langserver --stdio`. This is due to `multilspy`'s design, which abstracts away the direct configuration of server executables in its high-level `LanguageServer.create` API. A comment at the end of the file highlights this.

The code should now function using `multilspy`'s mechanisms.
