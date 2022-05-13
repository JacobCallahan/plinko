"""This module uses multiple techniques to gain insight about known entity usage"""
import ast
import importlib
import inspect
from importlib import util  # A python bug makes this necessary
from pathlib import Path

from astunparse import unparse
from logzero import logger
from plinko import code_parser
from plinko.parsers import python_importer
from plinko.helpers import gen_variants, get_coverage, write_to_file


class NodeParser(ast.NodeVisitor):
    """Move through a series of nodes and pull out relevant information"""

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
        """Add a specific or empty _path list to each visited node"""
        if not parent.__dict__.get("_path"):
            parent._path = []
        if not child.__dict__.get("_path"):
            child._path = parent._path[:]
        if type_name:
            child._path.append(type_name)

    def _handle_assignment(self, node, name):
        """Read a node's path and determine if it is part of an assignment"""
        if "assignment" in node._path:
            if node._path[-1] == "target":
                self.interests["assignment"][unparse(node).strip()] = None
            elif "value" in node._path:
                for key, val in self.interests["assignment"].items():
                    if val is None:
                        self.interests["assignment"][key] = name

    def generic_visit(self, node):
        """Add a _path attribute to each node to track parents"""
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
        for child in ast.iter_child_nodes(node):
            self._add_to_path(node, child, "attribute")
        attr = node.attr
        self._handle_assignment(node, attr)
        if node._path and node._path[-1] == "call":
            # something is being called
            if attr in self.known_entities:
                # an entity is being instaced
                self.interests["entity_instance"].append(attr)
                self.interests["attributes_accessed"].append(unparse(node).strip())
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
            # this module's member is being accessed
            self.interests["module_accessed"].append(unparse(node).strip())
        ast.NodeVisitor.generic_visit(self, node)


class CodeParser:
    def __init__(self, code_file, **kwargs):
        self.code_file = code_file
        self.create_on_instance = kwargs.get("create_on_instance", True)
        self.max_depth = kwargs.get("max_depth")
        self._curr_depth = kwargs.get("curr_depth", 0)
        self.entities = kwargs.get("entities")
        self._search_aggressiveness = kwargs.get("search_aggressiveness", "low")
        self._to_investigate = []  # ["module", "module attr call"]
        self.import_manager = python_importer.ImportManager()
        self.imports = {}  # {import_name: (module, <real_name>)}
        self.tests = {}  # {test_name: <parent class name>}
        self.classes = {} # {class_name: {bases: [bases], methods: [{method_name: method_ast}]}}
        self.methods = {}  # {method_name: {calls: ["scope method_name"], covers: [entity method]}}
        code_parser.PARSED_FILES.append(code_file)

    @staticmethod
    def _ast_to_str(ast_node):
        return unparse(ast_node).strip()

    @staticmethod
    def _find_all(needle, haystack):
        if isinstance(needle, dict):
            return {
                item: CodeParser._find_all(item, haystack) for item in needle.keys()
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

    def _find_entity(self, line):
        """Search through all known entities and return all matches"""
        found = []
        for entity in self.entities:
            if entity in line:
                found.append(entity)
            elif self._search_aggressiveness != "low":
                variants = gen_variants(entity)
                upper_line = line.upper()
                lower_line = line.lower()
                for variant in variants:
                    if found:
                        continue
                    if variant in line:
                        found.append(entity)
                    elif self._search_aggressiveness == "high":
                        if variant in upper_line or variant in lower_line:
                            found.append(entity)
        return found

    def _parse_general(self, gen_ast):
        """Largely for misc imports seen later which are more complex"""
        if isinstance(gen_ast, ast.ClassDef):
            self._parse_class_ast(gen_ast)
        elif isinstance(gen_ast, ast.FunctionDef) or isinstance(gen_ast, ast.AsyncFunctionDef):
            self._parse_method_ast(gen_ast)
        elif "body" in dir(gen_ast):
            for node in gen_ast.body:
                self._parse_general(node)
        else:
            logger.debug(f"Unable to handle node: {gen_ast}\nCode: {unparse(gen_ast)}")

    def _parse_class_ast(self, class_ast, parents=""):
        """Move through a class and record all the methods"""
        self.classes[class_ast.name] = {"bases": [], "methods": []}
        # add the class' bases
        for class_base in class_ast.bases:
            self.classes[class_ast.name]["bases"].append(unparse(class_base).strip())
        # add the class' children
        for node in class_ast.body:
            if isinstance(node, ast.ClassDef):
                self._parse_class_ast(node, parents=f"{parents}.{class_ast.name}")
            elif isinstance(node, ast.FunctionDef) or isinstance(
                node, ast.AsyncFunctionDef
            ):
                self.classes[class_ast.name]["methods"].append({node.name: node})
                if "test_" in node.name:
                    self.tests[node.name] = f"{parents}~{class_ast.name}"
                    # self.methods[node.name] = node
                # else:
                #     self.methods[f"{parents}~{class_ast.name}~{node.name}"] = node

    def _parse_method_ast(self, method_ast, class_name=None):
        """Recurse through a method's AST to find anything useful"""
        name = method_ast.name
        self.methods[name] = {"calls": [], "covers": []}
        known_vars = {}
        logger.debug(f"Parsing method ast {name}")
        for line_node in method_ast.body:
            unparsed_line = self._ast_to_str(line_node)
            logger.debug(f"Investigating line: {unparsed_line}")
            known_entities = self._find_entity(unparsed_line)
            # parse the line and find the interests
            line_parser = NodeParser(known_entities=known_entities)
            line_parser.visit(line_node)
            logger.debug(
                f"Found interests {line_parser.interests}"
            )
            # check to see if an entity was instanced and/or assigned to a variable
            for entity in line_parser.interests["entity_instance"]:
                if self.create_on_instance:
                    self.methods[name]["covers"].append(f"{entity} create")
                for key, val in line_parser.interests["assignment"].items():
                    if val == "create":
                        known_vars[key] = entity
            # catch the rest just in case we miss something
            for entity in [*known_entities, *known_vars]:
                if (
                    entity in line_parser.interests["method_calls"]
                    and self.create_on_instance
                ):
                    self.methods[name]["covers"].append(f"{entity} create")
            # check for method calls
            for meth_call in line_parser.interests["method_calls"]:
                if (
                    not line_parser.interests["module_accessed"]
                    and not line_parser.interests["attributes_accessed"]
                ):
                    # a non-external method is being called
                    self.methods[name]["calls"].append(meth_call)
                else:
                    found = False
                    # test for the method being a member of a module. module.method()
                    for module in line_parser.interests["module_accessed"]:
                        # We need to resolve uses of self and cls
                        if module in ["self", "cls"] and self.classes.get(class_name):
                            #  logger.warning(f"class name: {class_name}, meth call: {meth_call}")
                            if class_name and meth_call in self.classes[class_name]["methods"]:
                                module = class_name
                            elif class_name and self.classes[class_name]["bases"]:
                                for base in self.classes[class_name]["bases"]:
                                    self._to_investigate.append(f"{base}.{meth_call}")
                            else:
                                logger.debug(f"Can't resolve {module} for {meth_call}")
                        if f"{module}.{meth_call}" in unparsed_line:
                            # the method belongs to this module
                            if module in known_entities:
                                self.methods[name]["covers"].append(
                                    f"{module} {meth_call}"
                                )
                            else:
                                self.methods[name]["calls"].append(
                                    f"{module} {meth_call}"
                                )
                            found = True
                            break
                        # if it isn't a direct member, see if it is related
                        # entity.something.method()
                        for attr in line_parser.interests["attributes_accessed"]:
                            # We need to resolve uses of self and cls
                            if attr in ["self", "cls"]:
                                if class_name and meth_call in self.classes[class_name]["methods"]:
                                    attr = class_name
                                elif class_name and self.classes[class_name]["bases"]:
                                    for base in self.classes[class_name]["bases"]:
                                        self._to_investigate.append(f"{base}.{attr}.{meth_call}")
                                else:
                                    logger.debug(f"Can't resolve {attr} for {module}'s {meth_call}")
                            # now we need to determine
                            if f"{module}.{attr}.{meth_call}" in unparsed_line:
                                # the method belongs to this module
                                if module in known_entities:
                                    self.methods[name]["covers"].append(
                                        f"{module} {attr} {meth_call}"
                                    )
                                elif (
                                    attr in known_entities
                                    or f"{module}.{attr}" in known_vars
                                ):
                                    self.methods[name]["covers"].append(
                                        f"{attr} {meth_call}"
                                    )
                                else:
                                    self.methods[name]["calls"].append(
                                        f"{module} {attr} {meth_call}"
                                    )
                                found = True
                                break

                    if not found:
                        self.methods[name]["calls"].append(f"{meth_call}".strip())
                        self._to_investigate.append(meth_call)
            logger.debug(
                f"known vars: {known_vars}, known entities: {known_entities} \nMethod Report: {self.methods[name]}"
            )

    def _parse_file(self):
        """Parse a file, bringing in all the high level items"""
        logger.info(f"Starting to parse {self.code_file}")
        file_ast = None
        if not Path(self.code_file).exists():
            logger.warning(f"{self.code_file} does not exist!")
            return
        with Path(self.code_file).open() as py_file:
            try:
                file_ast = ast.parse(py_file.read())
            except UnicodeDecodeError:
                logger.warning(f"Unable to parse {self.code_file}")
                return
        # move through all high level nodes
        ast.FunctionDef
        ast.ClassDef
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
            elif isinstance(node, ast.FunctionDef) or isinstance(
                node, ast.AsyncFunctionDef
            ):
                if "test_" in node.name:
                    self.tests[node.name] = None
                self.methods[node.name] = node

    def _parse_import(self, import_name):
        """Parse through the import's file and get any coverage out of it"""
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
            create_on_instance=self.create_on_instance,
            max_depth=self.max_depth,
            curr_depth=self._curr_depth + 1,
            entities=self.entities,
        )
        py_parser.parse()
        # then get the results
        if import_name in py_parser.methods:
            self.import_manager.add_methods(import_name, py_parser.methods[import_name].copy())
            self.methods[import_name] = py_parser.methods[import_name].copy()
        else:
            logger.error(f"{import_name} not in {py_parser.methods}")
            for meth, contents in py_parser.methods.items():
                if import_name in meth:
                    self.import_manager.add_methods(import_name, contents.copy())
                    self.methods[import_name] = contents.copy()
                    return
            self.import_manager.add_methods(import_name, py_parser.methods.copy())

    def _perform_investigations(self):
        """Check through the investigation list and try to draw conclusions"""
        self.import_manager.resolve_all()
        # first, add all the class methods
        for class_name, values in self.classes.items():
            for method in values["methods"]:
                [meth_ast] = method.values()
                self._parse_method_ast(meth_ast, class_name)
        # second, gather all unresolved method calls
        for meth, values in self.methods.items():
            # {method_name: {calls: [{scope: [method_names]}, covers: [entity method]}}
            # first, determine if the current method needs to be added
            if values == "stdlib" or meth in self._to_investigate:
                # we can skip both of these right off
                pass
            elif not isinstance(values, dict):
                # we definitely need to investigate this
                self._to_investigate.append(meth)
            # next, we need to determine if the method's calls need to be added
            if isinstance(values, dict) and values.get("calls"):
                for call in values["calls"]:
                    meth_call = call.split()[-1]
                    if (
                        not meth_call in self.methods.items()
                        and not meth_call in self._to_investigate
                    ):
                        self._to_investigate.append(call)
        # now to carry on all of our investigations!
        # first, remove duplicates
        self._to_investigate = list(set(self._to_investigate))
        for subjects in self._to_investigate:
            split_subjects = subjects.split()
            subject = split_subjects[-1]
            logger.debug(f"Investigating {subjects}")
            if (
                subject in self.methods.keys()
                and not self.methods.get(subject) == "stdlib"
            ):
                # it is something we've already recorded
                if "ast." in str(type(self.methods[subject])):
                    # this is a non-parsed method, so let's parse it
                    self._parse_method_ast(self.methods[subject], subject)
                elif type(self.methods[subject]) is not dict:

                    # we don't know anything about this. time to check imports
                    methods = self.import_manager.get_methods(subject)
                    if not methods or not subject in methods:
                        self._parse_import(subject)
            else:
                # we've not recorded it, so we'll investigate
                methods = self.import_manager.get_methods(subject)
                if not methods or not subject in methods:
                    self._parse_import(subject)
            self._to_investigate.remove(subjects)

    def parse(self):
        """Main method that runs everything"""
        self._parse_file()
        self._perform_investigations()
        max_loops, loop_num = 10, 0
        while self._to_investigate and loop_num < max_loops:
            self._perform_investigations()
            loop_num += 1
        # finally we resolve all the coverage we can
        compiled_coverage = {}
        for method in self.methods.keys():
            # add any coverage from known matching imports
            if not isinstance(self.methods[method], dict):
                self._to_investigate.append({method: self.methods[method]})
                continue
            for call in self.methods[method].get("calls", []):
                call_cov = self.import_manager.get_methods(call)
                if isinstance(call_cov, dict) and call_cov.get("covers"):
                    self.methods[method]["covers"].append(call_cov)
            try:
                compiled_coverage[method] = get_coverage(method, self.methods)
            except RecursionError:
                logger.warning(f"Max recursion depth reached when compiling coverage for {method}.")
        if logger.level == 10:
            write_to_file(
                self.import_manager.known_imports,
                f"projects/hammer/cli/test/imports.yaml",
                "tests without coverage",
            )
        self.methods = compiled_coverage
