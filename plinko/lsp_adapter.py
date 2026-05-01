import asyncio
from pathlib import Path

from logzero import logger
from multilspy import LanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


class LSPAdapter:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.logger_instance = MultilspyLogger()
        self.config = MultilspyConfig.from_dict(
            {"code_language": "python", "trace_lsp_communication": False}
        )
        abs_project_root = str(self.project_root.resolve())
        self.client: LanguageServer = LanguageServer.create(
            self.config, self.logger_instance, abs_project_root
        )
        self._server_context = None
        self._is_server_active = False

    async def start_server_and_initialize(self):
        """Starts the Language Server using multilspy."""
        if self._is_server_active:
            logger.debug("LSP server context already active.")
            return

        if not self.client:
            raise ConnectionError("Multilspy client not initialized.")

        try:
            logger.info(f"Starting LSP server via multilspy for project: {self.project_root}")
            self._server_context = self.client.start_server()
            await self._server_context.__aenter__()
            self._is_server_active = True
            logger.info("LSP server started and initialized via multilspy.")
            return {"status": "initialized"}
        except Exception as e:
            self._is_server_active = False
            logger.error(f"Error starting multilspy server: {e}")
            raise ConnectionError(f"Failed to start and initialize multilspy server: {e}")

    async def open_document(self, file_path: Path):
        """Notifies the LSP server that a document has been opened."""
        if not self._is_server_active or not self.client:
            raise ConnectionError(
                "LSP server is not active. Call start_server_and_initialize first."
            )

        try:
            relative_file_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            raise ValueError(
                f"File path {file_path} must be relative to project root {self.project_root} for multilspy."
            )

        logger.debug(f"Opening document: {relative_file_path} via multilspy")
        try:
            async with self.client.open_file(relative_file_path):
                pass
        except Exception as e:
            logger.error(f"Error during multilspy open_file for {relative_file_path}: {e}")
            raise

    async def get_definition(self, file_path: Path, line: int, character: int):
        """
        Requests the definition of a symbol at a given location.
        Line and character are 0-based.
        """
        if not self._is_server_active or not self.client:
            raise ConnectionError("LSP server is not active.")

        try:
            relative_file_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            raise ValueError(
                f"File path {file_path} must be relative to project root {self.project_root} for multilspy."
            )

        logger.debug(
            f"Requesting definition for {relative_file_path} at L{line}:C{character}"
        )
        try:
            return await self.client.request_definition(relative_file_path, line, character)
        except Exception as e:
            logger.error(f"Error during multilspy request_definition: {e}")
            raise RuntimeError(f"LSP Error from multilspy: {e}")

    async def get_references(
        self, file_path: Path, line: int, character: int, include_declaration: bool = True
    ):
        """
        Requests all references to a symbol at a given location.
        Note: multilspy hardcodes includeDeclaration=False for Python.
        """
        if not self._is_server_active or not self.client:
            raise ConnectionError("LSP server is not active.")

        try:
            relative_file_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            raise ValueError(
                f"File path {file_path} must be relative to project root {self.project_root} for multilspy."
            )

        if include_declaration:
            logger.warning(
                "multilspy's request_references does not support includeDeclaration=True. "
                "Proceeding with includeDeclaration=False."
            )

        logger.debug(
            f"Requesting references for {relative_file_path} at L{line}:C{character}"
        )
        try:
            return await self.client.request_references(relative_file_path, line, character)
        except Exception as e:
            logger.error(f"Error during multilspy request_references: {e}")
            raise RuntimeError(f"LSP Error from multilspy: {e}")

    async def shutdown_server(self):
        """Shuts down the language server managed by multilspy."""
        if not self._server_context:
            logger.debug("LSP server context not established or already shut down.")
            return

        if self._is_server_active:
            logger.info("Shutting down LSP server via multilspy.")
            try:
                await self._server_context.__aexit__(None, None, None)
                logger.info("LSP server shutdown complete.")
            except Exception as e:
                logger.error(f"Error during multilspy server context exit: {e}")
            finally:
                self._is_server_active = False
                self._server_context = None
        else:
            self._server_context = None
