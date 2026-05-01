"""This module uses multiple techniques to gain insight about known entity usage."""
import ast
import asyncio
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from logzero import logger

from plinko import code_parser
from plinko.lsp_adapter import LSPAdapter


class Function:
    def __init__(self, ast_node, parent_parser, location=None, **kwargs):
        self.ast = ast_node # Store ast_node
        self.parent_parser = parent_parser
        self.lsp_adapter = kwargs.get("lsp_adapter", parent_parser.lsp_adapter)
        self.location = location or self.parent_parser.code_file.name
        self.parent_class = kwargs.get("parent_class")
        
        self.name = self.ast.name
        self.is_test = False
        self.is_fixture = False
        self.decs = []
        self._find_decorators() # Initialize decorators

        if self.name.startswith("test_") and self.parent_parser.code_file.name.startswith("test_"):
            self.is_test, self.is_fixture = True, False
        
        for dec in self.decs: # Check fixture status from decorators
            if "fixture" in dec:
                self.is_fixture = True
                self.is_test = False # A fixture is not usually a test itself
                break

        self.full_name = ":".join(
            filter(None, (self.location, self.parent_class, self.name))
        )
        self.args = {arg.arg for arg in self.ast.args.args}
        
        self.covers, self.calls, self.fixtures = (
            set(),
            set(),
            set(),
        )
        # self.parse() # Removed direct call to parse
        
        self.parent_parser.methods[self.full_name] = self
        if self.parent_parser.methods.get(self.name) and self.parent_parser.methods.get(self.name) is not self:
            del self.parent_parser.methods[self.name]

    # _find_entity method removed

    def _find_decorators(self):
        """Find all decorators attached to this function."""
        for dec in self.ast.decorator_list:
            if isinstance(dec, ast.Name):
                self.decs.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                # For decorators like @pytest.mark.foo, dec.attr would be 'foo'
                # For @something.else, it would be 'else'.
                # We might want the full decorator string in some cases.
                self.decs.append(ast.unparse(dec).strip()) # Store full decorator string
            else: # For ast.Call, etc.
                self.decs.append(ast.unparse(dec).strip())

    async def async_parse_with_lsp(self):
        """
        Parses the function's body using LSP to find calls and determine coverage.
        """
        logger.debug(f"Async parsing with LSP for function: {self.full_name} in {self.parent_parser.code_file}")

        for node in ast.walk(self.ast): # Iterate through all nodes in the function's AST
            if isinstance(node, ast.Call):
                call_func = node.func
                # Line numbers are 1-based in AST, LSP expects 0-based
                call_line = call_func.lineno - 1 
                call_char = call_func.col_offset

                try:
                    logger.debug(f"Getting definition for call {ast.unparse(call_func)} at {self.parent_parser.code_file}:{call_line+1}:{call_char}")
                    definition_response = await self.lsp_adapter.get_definition(
                        self.parent_parser.code_file, call_line, call_char
                    )
                    
                    # definition_response can be a list or a single dict, or None
                    definitions = []
                    if isinstance(definition_response, list):
                        definitions = definition_response
                    elif isinstance(definition_response, dict) and 'uri' in definition_response and 'range' in definition_response:
                        definitions = [definition_response]
                    
                    if not definitions:
                        logger.warning(f"No definition found for {ast.unparse(call_func)} in {self.full_name}")
                        self.calls.add(f"UNRESOLVED:{ast.unparse(call_func)}")
                        continue

                    for definition in definitions:
                        def_uri = definition.get('uri')
                        # def_range = definition.get('range') # For future use if needed
                        
                        if not def_uri:
                            self.calls.add(f"UNRESOLVED:{ast.unparse(call_func)} (no URI)")
                            continue

                        parsed = urlparse(def_uri)
                        if parsed.scheme != "file":
                            self.calls.add(f"UNRESOLVED:{ast.unparse(call_func)} (non-file URI)")
                            continue
                        def_path = Path(unquote(parsed.path))
                        
                        # Attempt to form a representative string for the call
                        # This is a simplification; robustly getting the FQN from LSP is harder
                        call_target_str = f"{def_path.stem}.{ast.unparse(call_func)}" # Default/fallback
                        
                        # Try to infer a module path relative to project or site-packages
                        try:
                            # Try to make it relative to project root if possible
                            rel_path = def_path.relative_to(self.parent_parser.project_root)
                            module_parts = list(rel_path.parent.parts)
                            if rel_path.stem != "__init__":
                                module_parts.append(rel_path.stem)
                            call_target_str = ".".join(module_parts) + f".{ast.unparse(call_func)}"
                        except ValueError: # Not under project root, try to find site-packages
                            if 'site-packages' in def_path.parts:
                                sp_index = def_path.parts.index('site-packages')
                                module_parts = list(def_path.parts[sp_index+1:])
                                if module_parts[-1] == "__init__.py": # e.g. .../module/__init__.py
                                     module_parts = module_parts[:-1]
                                elif module_parts[-1].endswith(".py"): # e.g. .../module/file.py
                                    module_parts[-1] = module_parts[-1][:-3] # remove .py
                                call_target_str = ".".join(module_parts) + f".{ast.unparse(call_func)}"
                        
                        self.calls.add(call_target_str)
                        logger.debug(f"Call to {call_target_str} added from {self.full_name}")

                        # Coverage Check
                        for entity_name in self.parent_parser.entities: # e.g., entity_name is 'nailgun'
                            # Check if the definition path contains the entity name as a directory component
                            # This is a simple heuristic. More robust would be to check against a list of entity module names.
                            if f"/{entity_name}/" in def_uri or def_uri.endswith(f"/{entity_name}.py"):
                                # Determine the specific method/function name from the call or definition
                                # For now, using ast.unparse(call_func) which might be MyClass.method or just method
                                called_member_name = ast.unparse(call_func)
                                if '.' in called_member_name: # Likely Class.method or module.method
                                    called_member_name = called_member_name.split('.')[-1]

                                self.covers.add(f"{entity_name} {called_member_name}")
                                logger.debug(f"Coverage added: {entity_name} {called_member_name} by {self.full_name}")
                                if self.parent_parser.create_on_instance:
                                     # Simplistic check: if the call looks like an instantiation (e.g. MyClass())
                                     # This is hard to determine accurately without type info for `call_func` itself
                                     # A better check might be if the definition points to an __init__ method of a class
                                     # or if `ast.unparse(call_func)` matches an entity name (e.g. `nailgun.Client()`)
                                    if called_member_name.lower() == entity_name.lower() or called_member_name == "Client": # Heuristic
                                        self.covers.add(f"{entity_name} create")
                                        logger.debug(f"Coverage added: {entity_name} create by {self.full_name}")


                except Exception as e:
                    logger.error(f"Error getting definition for {ast.unparse(call_func)} in {self.full_name}: {e}")
                    self.calls.add(f"ERROR_RESOLVING:{ast.unparse(call_func)}")
        logger.debug(f"Finished LSP parsing for {self.full_name}. Calls: {self.calls}, Covers: {self.covers}")


class CodeParser:
    def __init__(self, code_file, parent_parser, **kwargs):
        self.code_file = Path(code_file)
        self.parent_parser = parent_parser
        self.project_root = parent_parser.project_root
        self.create_on_instance = parent_parser.create_on_instance
        self.entities = parent_parser.entities
        self._search_aggressiveness = kwargs.get("search_aggressiveness", "low")
        self.max_depth = kwargs.get("max_depth", 0)
        self.lsp_adapter = LSPAdapter(project_root=self.parent_parser.project_root)
        self.classes, self.methods, self.covers = {}, {}, {}
        if code_file not in code_parser.PARSED_FILES:
            code_parser.PARSED_FILES.append(code_file)

    @staticmethod
    def _find_all(needle, haystack):
        if isinstance(needle, dict):
            return {item: CodeParser._find_all(item, haystack) for item in needle}
        elif isinstance(needle, list):
            return [CodeParser._find_all(item, haystack) for item in needle]
        else:
            pos = haystack.find(needle)
            if pos == -1:
                return [pos]
            found = []
            while pos > -1:
                found.append(pos)
                next_pos = haystack[pos + len(needle):].find(needle)
                if next_pos == -1:
                    break
                pos += len(needle) + next_pos
            return found

    def _parse_class_ast(self, class_ast, parents=""):
        """Move through a class and record all the methods and basic structure."""
        class_name = class_ast.name
        full_class_name = f"{parents}.{class_name}" if parents else class_name
        self.classes[class_name] = {"bases": [], "methods": []}
        for class_base in class_ast.bases:
            self.classes[class_name]["bases"].append(ast.unparse(class_base).strip())
        for node in class_ast.body:
            if isinstance(node, ast.ClassDef):
                self._parse_class_ast(node, parents=full_class_name)
            elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                Function(node, self, parent_class=class_name, lsp_adapter=self.lsp_adapter)

    def _parse_file(self):
        """Parse a file, identifying top-level classes and functions for further LSP analysis."""
        logger.info(f"Shallow parsing file for AST structure: {self.code_file.absolute()}")
        if not self.code_file.exists():
            logger.warning(f"{self.code_file} does not exist!")
            return
        try:
            file_content = self.code_file.read_text()
            file_ast = ast.parse(file_content)
        except UnicodeDecodeError:
            logger.warning(f"Unable to parse {self.code_file.absolute()} due to UnicodeDecodeError.")
            return
        except SyntaxError:
            logger.warning(f"Unable to parse {self.code_file.absolute()} due to SyntaxError.")
            return

        for node in file_ast.body:
            if isinstance(node, ast.ClassDef):
                self._parse_class_ast(node)
            elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                Function(node, self, lsp_adapter=self.lsp_adapter)

    def _match_fixtures(self):
        """Match a method's args to available fixtures."""
        fixtures = {meth.name: meth for meth in self.methods.values() if isinstance(meth, Function) and meth.is_fixture}
        for method in self.methods.values():
            if not isinstance(method, Function):
                continue
            for arg in method.args:
                if fixture := fixtures.get(arg):
                    method.fixtures.add(fixture)
                    method.covers.update(fixture.covers)
                elif fixture := self.parent_parser.fixture_handler.fixtures.get(arg):
                    method.fixtures.add(fixture)
                    method.covers.update(fixture.covers)

    async def _async_parse_setup(self):
        """Helper async function to manage LSP server and document opening."""
        try:
            await self.lsp_adapter.start_server_and_initialize()
            if self.methods:
                logger.debug(f"Found {len(self.methods)} methods to LSP parse in {self.code_file}")
                for func_obj in self.methods.values():
                    if isinstance(func_obj, Function):
                        try:
                            await func_obj.async_parse_with_lsp()
                        except Exception as e:
                            logger.error(f"Error during LSP parsing of function {func_obj.full_name}: {e}")
            else:
                logger.debug(f"No methods found by _parse_file to LSP parse in {self.code_file}")
        finally:
            await self.lsp_adapter.shutdown_server()

    def parse(self):
        """Main method that runs everything. Initiates LSP and performs AST parsing."""
        logger.info(f"Starting LSP-assisted parsing for {self.code_file}")
        self._parse_file()

        exc = []

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._async_parse_setup())
            except Exception as e:
                exc.append(e)
            finally:
                loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join()
        if exc:
            logger.error(f"LSP setup or async parsing failed for {self.code_file}: {exc[0]}")

        self._match_fixtures()
        logger.info(f"Completed initial parsing pass for {self.code_file}.")
