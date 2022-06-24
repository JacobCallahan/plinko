"""This module uses multiple techniques to gain insight about known entity usage."""
import ast
from pathlib import Path

from logzero import logger

from plinko import code_parser
from plinko.helpers import gen_variants, get_coverage
from plinko.parsers import python_importer


class NodeParser(ast.NodeVisitor):
    """Move through a series of nodes and pull out relevant information."""

    def __init__(self, **kwargs):
        self.interests = {
            "method_calls": [],  # [{module: method}]
            "attributes_accessed": [],  # [attribute name]
            "module_accessed": [],  # [module name]
            "entity_instance": [],  # [entity name]
            "assignment": {},  # {target: value}
        }
        self.known_entities = kwargs.get("known_entities", [])
        super()

    def _add_to_path(self, parent, child, type_name=None):
        """Add a specific or empty _path list to each visited node."""
        if not parent.__dict__.get("_path"):
            parent._path = []
        if not child.__dict__.get("_path"):
            child._path = parent._path[:]
        if type_name:
            child._path.append(type_name)

    def _handle_assignment(self, node, name):
        """Read a node's path and determine if it is part of an assignment."""
        if "assignment" in node._path:
            if node._path[-1] == "target":
                self.interests["assignment"][ast.unparse(node).strip()] = None
            elif "value" in node._path:
                for key, val in self.interests["assignment"].items():
                    if val is None:
                        self.interests["assignment"][key] = name

    # this should be assigned to the Setting(s) entity instead of search
    # [D 230822 12:53:00 python_parser:179] Investigating line: setting_object = entities.Setting().search(query={'search': f'name={request.param}'})[0]
    # [D 230822 12:53:00 python_parser:184] Found interests {'method_calls': ['search'], 'attributes_accessed': ['entities.Setting', 'param'], 'module_accessed': ['entities', 'request'], 'entity_instance': ['Setting'], 'assignment': {'setting_object': 'search'}}


    def generic_visit(self, node):
        """Add a _path attribute to each node to track parents."""
        for child in ast.iter_child_nodes(node):
            self._add_to_path(node, child, "generic")
        ast.NodeVisitor.generic_visit(self, node)

    def visit_Assign(self, node):
        for child in ast.iter_child_nodes(node):
            self._add_to_path(node, child, "assignment")
            if child in node.targets:
                self._add_to_path(node, child, "target")
            else:
                self._add_to_path(node, child, "value")
        ast.NodeVisitor.generic_visit(self, node)

    def visit_Call(self, node):
        for child in ast.iter_child_nodes(node):
            if node.func == child:
                self._add_to_path(node, child, "call")
        ast.NodeVisitor.generic_visit(self, node)

    def visit_Attribute(self, node):
        """Visit an Attribute node and add relevant information to the interests dictionary.
        If the attribute is being called, check if it is a known entity instance or a method call.
        If it is a known entity instance, add the attribute to the attributes_accessed list.
        If it is not a known entity instance, add it to the method_calls list.
        If it is not being called, add it to the attributes_accessed list.
        """
        for child in ast.iter_child_nodes(node):
            self._add_to_path(node, child, "attribute")
        attr = node.attr
        self._handle_assignment(node, attr)
        if node._path and node._path[-1] == "call":
            # something is being called
            if attr in self.known_entities:
                # an entity is being instaced
                self.interests["entity_instance"].append(attr)
                self.interests["attributes_accessed"].append(ast.unparse(node).strip())
            else:
                # not a direct entity instance, so we'll store it
                self.interests["method_calls"].append(attr)
        else:
            # we're an attribute of something, so store it for inspection
            self.interests["attributes_accessed"].append(attr)
        ast.NodeVisitor.generic_visit(self, node)

    def visit_Name(self, node):
        for child in ast.iter_child_nodes(node):
            self._add_to_path(node, child)
        name = node.id
        self._handle_assignment(node, name)
        if node._path and node._path[-1] == "call":
            # something is being called
            if name in self.known_entities:
                # an entity is being instaced
                self.interests["entity_instance"].append(name)
            else:
                # not a direct entity instance, so we'll store it
                self.interests["method_calls"].append(name)
        elif node._path and node._path[-1] == "attribute":
            # possible module member is being accessed
            self.interests["module_accessed"].append(ast.unparse(node).strip())
        ast.NodeVisitor.generic_visit(self, node)


class Function:
    def __init__(self, ast, parent_parser, location=None, **kwargs):
        self.ast = ast
        self.parent_parser = parent_parser
        self.location = location or self.parent_parser.code_file.name
        self.parent_class = kwargs.get("parent_class")
        self.name = self.is_test = self.is_fixture = None
        self.covers, self.calls, self.fixtures, self.args, self.decs = (
            set(),
            set(),
            set(),
            [],
            [],
        )
        self.parse()
        self.parent_parser.methods[self.full_name] = self
        if self.parent_parser.methods.get(self.name):
            del self.parent_parser.methods[self.name]

    def _find_entity(self, line):
        """Search through all known entities and return all matches."""
        found = []
        for entity in self.parent_parser.entities:
            if entity in line:
                found.append(entity)
            elif self.parent_parser._search_aggressiveness != "low":
                variants = gen_variants(entity)
                upper_line = line.upper()
                lower_line = line.lower()
                for variant in variants:
                    if found:
                        continue
                    if variant in line:
                        found.append(entity)
                    elif self.parent_parser._search_aggressiveness == "high":
                        if variant in upper_line or variant in lower_line:
                            found.append(entity)
        return found

    def _find_decorators(self):
        """Find all decorators attached to this function."""
        for dec in self.ast.decorator_list:
            if isinstance(dec, ast.Name):
                self.decs.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                self.decs.append(dec.attr)
            else:
                self.decs.append(ast.unparse(dec).strip())

    def parse(self):
        """Recurse through a this function's AST to find anything useful."""
        # pull decorator information and check for us being a fixture
        self._find_decorators()
        for dec in self.decs:
            if "fixture" in dec:
                self.is_fixture = True
        # pull information about our name
        self.name = self.ast.name
        if self.name.startswith("test_") and self.parent_parser.code_file.name.startswith("test_"):
            self.is_test, self.is_fixture = True, False
        # construct a full name based on location and parent class
        self.full_name = ":".join(
            filter(None, (self.location, self.parent_class, self.name))
        )
        self.args = {arg.arg for arg in self.ast.args.args}
        known_vars = {}
        logger.debug(f"Parsing method ast {self}")
        for line_node in self.ast.body:
            unparsed_line = ast.unparse(line_node)
            logger.debug(f"Investigating line: {unparsed_line}")
            known_entities = self._find_entity(unparsed_line)
            # parse the line and find the interests
            line_parser = NodeParser(known_entities=known_entities)
            line_parser.visit(line_node)
            logger.debug(f"Found interests {line_parser.interests}")
            # check to see if an entity was instanced and/or assigned to a variable
            for entity in line_parser.interests["entity_instance"]:
                if self.parent_parser.create_on_instance:
                    self.covers.add(f"{entity} create")
                for key, val in line_parser.interests["assignment"].items():
                    if val in ("create", "update", "info", "read"):
                        known_vars[key] = entity
            # catch the rest just in case we miss an entity instance
            for entity in [*known_entities, *known_vars]:
                if (
                    entity in line_parser.interests["method_calls"]
                    and self.parent_parser.create_on_instance
                ):
                    self.covers.add(f"{entity} create")
            # check for method calls
            for meth_call in line_parser.interests["method_calls"]:
                if (
                    not line_parser.interests["module_accessed"]
                    and not line_parser.interests["attributes_accessed"]
                    and meth_call not in python_importer.BUILTINS
                ):
                    # a non-external method is being called
                    self.calls.add(meth_call)
                else:
                    found = False
                    # test for the method being a member of a module. module.method()
                    for module in line_parser.interests["module_accessed"]:
                        # We need to resolve uses of self and cls
                        if module in ["self", "cls"] and self.parent_class:
                            #  logger.warning(f"class name: {class_name}, meth call: {meth_call}")
                            if (
                                self.parent_class
                                and meth_call
                                in self.parent_parser.classes[self.parent_class][
                                    "methods"
                                ]
                            ):
                                module = self.parent_class
                            elif (
                                self.parent_class
                                and self.parent_parser.classes[self.parent_class][
                                    "bases"
                                ]
                            ):
                                for base in self.parent_parser.classes[
                                    self.parent_class
                                ]["bases"]:
                                    self.parent_parser._to_investigate.add(
                                        f"{base}.{meth_call}"
                                    )
                            else:
                                logger.debug(f"Can't resolve {module} for {meth_call}")
                        if f"{module}.{meth_call}" in unparsed_line:
                            # the method belongs to this module
                            if module in known_entities:
                                self.covers.add(f"{module} {meth_call}")
                            elif module in known_vars:
                                self.covers.add(f"{known_vars[module]} {meth_call}")
                            else:
                                self.calls.add(f"{module} {meth_call}")
                            found = True
                            break
                        # if it isn't a direct member, see if it is related
                        # entity.something.method()
                        for attr in line_parser.interests["attributes_accessed"]:
                            # We need to resolve uses of self and cls
                            if attr in ["self", "cls"]:
                                if (
                                    self.parent_class
                                    and meth_call
                                    in self.parent_parser.classes[self.parent_class][
                                        "methods"
                                    ]
                                ):
                                    attr = self.parent_class
                                elif (
                                    self.parent_class
                                    and self.parent_parser.classes[self.parent_class][
                                        "bases"
                                    ]
                                ):
                                    for base in self.parent_parser.classes[
                                        self.parent_class
                                    ]["bases"]:
                                        self.parent_parser._to_investigate.add(
                                            f"{base}.{attr}.{meth_call}"
                                        )
                                else:
                                    logger.debug(
                                        f"Can't resolve {attr} for {module}'s {meth_call}"
                                    )
                            # now we need to determine if the attribute is a member of the module
                            if "." in attr:
                                if (split_attr := attr.split("."))[1] in known_entities:
                                    self.covers.add(f"{split_attr[1]} {meth_call}")
                                else:
                                    self.calls.add(f"{split_attr[1]} {meth_call}")
                                found = True
                                break

                            if f"{module}.{attr}.{meth_call}" in unparsed_line:
                                # the method belongs to this module
                                if module in known_entities:
                                    self.covers.add(f"{module} {attr} {meth_call}")
                                elif (
                                    attr in known_entities
                                    or f"{module}.{attr}" in known_vars
                                ):
                                    self.covers.add(f"{attr} {meth_call}")
                                elif module in known_vars:
                                    self.covers.add(
                                        f"{known_vars[module]} {attr} {meth_call}"
                                    )
                                elif attr in known_vars:
                                    self.covers.add(f"{known_vars[attr]} {meth_call}")
                                else:
                                    self.calls.add(f"{module} {attr} {meth_call}")
                                found = True
                                break

                    if not found:
                        self.calls.add(f"{meth_call}".strip())
                        self.parent_parser._to_investigate.add(meth_call)
            logger.debug(
                f"known vars: {known_vars}, known entities: {known_entities} \nMethod Report:\n\t{self.covers}"
            )


class CodeParser:
    def __init__(self, code_file, parent_parser, **kwargs):
        self.code_file = Path(code_file)
        self.parent_parser = parent_parser
        self.create_on_instance = parent_parser.create_on_instance
        self.max_depth = parent_parser.max_depth
        self.entities = parent_parser.entities
        self._curr_depth = kwargs.get("curr_depth", 0)
        self._search_aggressiveness = kwargs.get("search_aggressiveness", "low")
        self._to_investigate = set()  # {"module", "module attr call"}
        self.import_manager = python_importer.ImportManager
        self.imports = {}  # {import_name: (module, <real_name>)}
        # {class_name: {bases: [bases], methods: [{method_name: method_ast}]}}
        # {method_name: Function}
        # {test_name: Function}
        self.classes, self.methods, self.covers = {}, {}, {}
        code_parser.PARSED_FILES.append(code_file)

    @staticmethod
    def _find_all(needle, haystack):
        if isinstance(needle, dict):
            return {
                item: CodeParser._find_all(item, haystack) for item in needle
            }
        elif isinstance(needle, list):
            return [CodeParser._find_all(item, haystack) for item in needle]
        else:
            pos = haystack.find(needle)
            if pos == -1:
                return [pos]
            found = []
            while pos > -1:
                found.append(pos)
                pos = haystack[pos + 1 :].find(needle)
            return found

    def _parse_general(self, gen_ast):  # this is currently unused
        """Largely for misc imports seen later which are more complex."""
        if isinstance(gen_ast, ast.ClassDef):
            self._parse_class_ast(gen_ast)
        elif isinstance(gen_ast, ast.AsyncFunctionDef | ast.FunctionDef):
            Function(gen_ast, self)  # where does this need to go?
        elif "body" in dir(gen_ast):
            for node in gen_ast.body:
                self._parse_general(node)
        else:
            logger.debug(
                f"Unable to handle node: {gen_ast}\nCode: {ast.unparse(gen_ast)}"
            )

    def _parse_class_ast(self, class_ast, parents=""):
        """Move through a class and record all the methods."""
        self.classes[class_ast.name] = {"bases": [], "methods": []}
        # add the class' bases
        for class_base in class_ast.bases:
            self.classes[class_ast.name]["bases"].append(
                ast.unparse(class_base).strip()
            )
        # add the class' children
        for node in class_ast.body:
            if isinstance(node, ast.ClassDef):
                self._parse_class_ast(node, parents=f"{parents}.{class_ast.name}")
            elif isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                class_func = Function(node, self, parent_class=class_ast.name)
                self.classes[class_ast.name]["methods"].append(class_func)
                #   self.methods[node.name] = node
                # else:
                #     self.methods[f"{parents}~{class_ast.name}~{node.name}"] = node

    def _parse_file(self):
        """Parse a file, bringing in all the high level items."""
        logger.info(f"Starting to parse {self.code_file.absolute()}")
        file_ast = None
        if not self.code_file.exists():
            logger.warning(f"{self.code_file} does not exist!")
            return
        with self.code_file.open() as py_file:
            try:
                file_ast = ast.parse(py_file.read())
            except UnicodeDecodeError:
                logger.warning(f"Unable to parse {self.code_file.absolute()}")
                return
        # move through all high level nodes
        for node in file_ast.body:
            if isinstance(node, ast.ImportFrom):
                for name in node.names:
                    if name.asname:  # if using import something as another_name
                        self.import_manager.register(
                            name.asname, node.__dict__.get("module"), name.name
                        )
                    else:
                        self.import_manager.register(
                            name.name, node.__dict__.get("module")
                        )
            elif isinstance(node, ast.Import):
                # regular imports are pretty similar, but still different enough
                for name in node.names:
                    if name.asname:
                        # this will make sense later...
                        self.import_manager.register(name.asname, name.name)
                    else:
                        self.import_manager.register(name.name)
            elif isinstance(node, ast.ClassDef):
                self._parse_class_ast(node)
            elif isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                # if "test_" in node.name:
                #     self.tests[node.name] = None
                self.methods[node.name] = node

    def _parse_import(self, import_name):
        """Parse through the import's file and get any coverage out of it."""
        if self._curr_depth >= self.max_depth:
            logger.debug(f"Max depth of {self.max_depth} has been reached!")
            return
        # if not, try to fall back to the file itself
        file_path = self.import_manager.get_file(import_name)
        if not file_path or file_path in code_parser.PARSED_FILES:
            # logger.error(f'No file for {import_name}: tried: {file_path}')
            return
        # logger.error(f'Found file for {import_name}: {file_path}')
        # pass the file on to a new parser
        py_parser = CodeParser(
            code_file=file_path,
            parent_parser=self.parent_parser,
            curr_depth=self._curr_depth + 1,
        )
        py_parser.parse()
        # then get the results
        if import_name in py_parser.methods:
            self.import_manager.add_methods(
                import_name, py_parser.methods[import_name]
            )
            self.methods[import_name] = py_parser.methods[import_name]
        else:
            logger.error(f"{import_name} not in {py_parser.methods}")
            for meth, contents in py_parser.methods.items():
                if import_name in meth:
                    self.import_manager.add_methods(import_name, contents)
                    self.methods[import_name] = contents
                    return
            self.import_manager.add_methods(import_name, py_parser.methods)

    def _match_fixtures(self):
        """Match a method's args to available fixtures."""
        fixtures = {meth.name: meth for meth in self.methods.values() if meth.is_fixture}
        for method in self.methods.values():
            for arg in method.args:
                if fixture := fixtures.get(arg):
                    method.fixtures.add(fixture)
                    method.covers.update(fixture.covers)
                elif fixture := self.parent_parser.fixture_handler.fixtures.get(arg):
                    method.fixtures.add(fixture)
                    method.covers.update(fixture.covers)

    def _perform_investigations(self):
        """Check through the investigation list and try to draw conclusions."""
        logger.debug("Resolving all imports")
        self.import_manager.resolve_all()
        # gather all unresolved method calls
        for meth, values in self.methods.items():
            # first, determine if the current method needs to be added
            if values == "stdlib" or meth in self._to_investigate:
                # we can skip both of these right off
                continue
            elif not isinstance(values, Function):
                # we definitely need to investigate this
                logger.debug(f"Adding {meth} to investigation list")
                self._to_investigate.add(meth)
            # next, we need to determine if the method's calls need to be added
            elif isinstance(values, Function) and values.calls:
                for call in values.calls:
                    if isinstance(call, Function):
                        continue
                    meth_call = call.split()[-1]
                    if (
                        meth_call not in self.methods.items()
                        and meth_call not in self._to_investigate
                    ):
                        logger.debug(f"Adding {call} to investigation list")
                        self._to_investigate.add(call)
        # now to carry on all of our investigations!
        for subjects in self._to_investigate.copy():  # copy to avoid size change
            subject = subjects.split()[-1]
            logger.debug(f"Investigating {subjects}")
            if (
                subject in self.methods
                and self.methods.get(subject) != "stdlib"
            ):
                # it is something we've already recorded
                if "ast." in str(type(self.methods[subject])):
                    # this is a non-parsed method, so let's parse it
                    logger.debug(f"Parsing non-parsed method {subject}")
                    Function(self.methods[subject], self)
                elif not isinstance(self.methods[subject], Function):
                    # we don't know anything about this. time to check imports
                    logger.debug(f"Checking imports for {subject}")
                    methods = self.import_manager.get_methods(subject)
                    if not methods or subject not in methods:
                        self._parse_import(subject)
            else:
                # we've not recorded it, so we'll investigate
                logger.debug(f"Checking imports for {subject}")
                methods = self.import_manager.get_methods(subject)
                if not methods or subject not in methods:
                    self._parse_import(subject)
            self._to_investigate.remove(subjects)

    def parse(self):
        """Main method that runs everything."""
        self._parse_file()
        self._perform_investigations()
        max_loops, loop_num = 10, 0
        while self._to_investigate and loop_num < max_loops:
            self._perform_investigations()
            loop_num += 1
        # finally we resolve all the coverage we can
        for method in self.methods:
            # add any coverage from known matching imports
            if not isinstance(self.methods[method], Function):
                self._to_investigate.add({method: self.methods[method]})
                continue
            if not isinstance(self.methods[method].calls, Function):
                logger.warning(
                    f"{self.methods[method].full_name} has unresolved calls:\n{self.methods[method].calls}"
                )
            else:
                for call in self.methods[method].calls:
                    # call_cov = self.import_manager.get_methods(call)
                    # if isinstance(call_cov, dict) and call_cov.get("covers"):
                    #     self.methods[method]["covers"].append(call_cov)
                    self.methods[method].covers.update(call.covers)
            try:
                self.methods[method].covers.update(get_coverage(method, self.methods))
            except RecursionError:
                logger.warning(
                    f"Max recursion depth reached when compiling coverage for {method}."
                )
        # attempt to resolve fixture coverage
        self._match_fixtures()
        # if logger.level == 10:
        #     write_to_file(
        #         self.import_manager.known_imports,
        #         f"projects/hammer/cli/test/imports.yaml",
        #         "tests without coverage",
        #     )
