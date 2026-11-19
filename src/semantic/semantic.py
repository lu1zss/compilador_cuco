"""Valida as extensões Cuco e anota a AST para a geração de C."""

from copy import deepcopy
import re


COMMON_METHODS = {
    "size": ((), "size_t"), "capacity": ((), "size_t"),
    "isEmpty": ((), "_Bool"), "isFull": ((), "_Bool"), "clear": ((), "void"),
}
METHODS = {
    "List": {
        "add": (("element",), "_Bool"),
        "insert": (("index", "element"), "_Bool"),
        "remove": (("index",), "element"),
        "get": (("index",), "element"),
        "set": (("index", "element"), "void"),
    },
    "Stack": {"push": (("element",), "_Bool"), "pop": ((), "element"),
              "peek": ((), "element")},
    "Queue": {"enqueue": (("element",), "_Bool"), "dequeue": ((), "element"),
              "peek": ((), "element")},
}
UNKNOWN = ("unknown",)
VOID = ("scalar", "void")
INTEGER_WORDS = {"char", "short", "int", "long", "signed", "unsigned", "_Bool", "size_t"}


def integer(type_):
    return type_[0] == "enum" or (
        type_[0] == "scalar" and set(type_[1].split()) <= INTEGER_WORDS
    )


def numeric(type_):
    return integer(type_) or (
        type_[0] == "scalar" and set(type_[1].split()) <= {"float", "double", "long", "_Complex"}
    )


def compatible(expected, actual, expression=None):
    if expected == actual or UNKNOWN in (expected, actual):
        return True
    if numeric(expected) and numeric(actual):
        return True
    if expected[0] == "pointer":
        if actual[0] == "array":
            actual = ("pointer", actual[1])
        if actual[0] == "pointer":
            return expected[1] == actual[1] or VOID in (expected[1], actual[1])
        if integer(actual) and expression and expression["kind"] == "Constant":
            return integer_literal(expression["value"]) == 0
        if expression and expression["kind"] == "ID":
            return expression["name"] == "NULL"
    return False


def integer_literal(value):
    digits = value.rstrip("uUlL")
    if not re.fullmatch(r"0[xX][0-9a-fA-F]+|[0-9]+", digits):
        return None
    if digits.lower().startswith("0x"):
        return int(digits, 16)
    return int(digits, 8 if digits.startswith("0") else 10)


class SemanticAnalyzer:
    def __init__(self):
        self.scopes = [{}]
        self.symbols = []
        self.record_fields = {}
        self.diagnostics = []
        self.return_type = VOID

    def error(self, node, message):
        self.diagnostics.append({
            "line": node.get("line"), "column": node.get("column"), "message": message,
        })

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def declare(self, node, type_, category="object"):
        name = node.get("name")
        if not name:
            return
        previous = self.scopes[-1].get(name)
        is_collection = type_[0] == "collection" or (
            previous is not None and previous["type"][0] == "collection"
        )
        if previous and is_collection:
            self.error(node, f"declaração duplicada de {name!r}")
        symbol = {
            "name": name, "type": type_, "category": category,
            "depth": len(self.scopes) - 1, "line": node.get("line"),
            "column": node.get("column"),
        }
        self.scopes[-1][name] = symbol
        self.symbols.append(symbol)

    def read_type(self, node):
        kind = node["kind"]
        if kind in {"Typename", "TypeDecl"}:
            return self.read_type(node["type"])
        if kind in {"PtrDecl", "ArrayDecl"}:
            category = "pointer" if kind == "PtrDecl" else "array"
            return (category, self.read_type(node["type"]))
        if kind == "CollectionType":
            element = self.read_type(node["element_type"])
            return ("collection", node["structure"], element)
        if kind == "FuncDecl":
            args = node["args"]["params"] if node["args"] else None
            parameters = None if args is None else tuple(
                self.read_type(arg["type"]) if "type" in arg else ("scalar", "int")
                for arg in args if arg["kind"] != "EllipsisParam"
            )
            if parameters == (VOID,):
                parameters = ()
            variadic = bool(args and args[-1]["kind"] == "EllipsisParam")
            return ("function", self.read_type(node["type"]), parameters, variadic)
        if kind == "IdentifierType":
            words = node["names"]
            if len(words) == 1:
                symbol = self.lookup(words[0])
                if symbol and symbol["category"] == "typedef":
                    return symbol["type"]
            if set(words) <= INTEGER_WORDS and any(
                word in words for word in ("short", "long", "signed", "unsigned")
            ):
                if "char" not in words:
                    words = [word for word in words if word not in {"int", "signed"}]
                    words = words or ["int"]
                words = sorted(words)
            return ("scalar", " ".join(words))
        if kind in {"Struct", "Union"}:
            key = (kind.lower(), node["name"] or f"@{node.get('line')}:{node.get('column')}")
            if node["decls"] is not None:
                self.record_fields[key] = {
                    field["name"]: self.read_type(field["type"]) for field in node["decls"]
                }
            return key
        if kind == "Enum":
            if node["values"]:
                for member in node["values"]["enumerators"]:
                    self.declare(member, ("scalar", "int"), "enumerator")
            return ("enum", node["name"])
        return UNKNOWN

    def validate_collection(self, node, type_):
        if type_[0] != "collection":
            return
        element = type_[2]
        if element == VOID or element[0] in {"function", "array", "collection"}:
            self.error(node, "tipo de elemento inválido para a coleção")
        if element[0] in {"struct", "union"} and element not in self.record_fields:
            self.error(node, "tipo incompleto como elemento da coleção")

    def visit(self, node):
        if not isinstance(node, dict):
            return
        kind = node["kind"]
        if kind in {"Compound", "For"}:
            self.scopes.append({})
            self.visit_children(node)
            self.scopes.pop()
        elif kind == "FuncDef":
            self.visit_function(node)
        elif kind in {"Decl", "Typedef", "CollectionDeclaration"}:
            self.visit_declaration(node)
        elif kind == "Return":
            actual = self.expression(node["expr"]) if node["expr"] else VOID
            self.check_collection_assignment(node, self.return_type, actual, node["expr"])
        elif kind in EXPRESSION_KINDS:
            self.expression(node)
        else:
            self.visit_children(node)

    def visit_children(self, node):
        for value in node.values():
            if isinstance(value, list):
                for child in value:
                    self.visit(child)
            elif isinstance(value, dict) and "kind" in value:
                self.visit(value)

    def visit_function(self, node):
        declaration = node["decl"]
        signature = self.read_type(declaration["type"])
        self.declare(declaration, signature, "function")
        self.validate_collection(declaration, signature[1])
        self.return_type = signature[1]
        self.scopes.append({})
        args = declaration["type"]["args"]
        for parameter in args["params"] if args else []:
            if parameter["kind"] == "Decl":
                self.visit_declaration(parameter)
            elif parameter["kind"] == "ID":
                self.declare(parameter, ("scalar", "int"))
        for parameter in node["param_decls"] or []:
            self.visit_declaration(parameter)
        # Parâmetros e declarações do corpo externo compartilham o escopo.
        self.visit_children(node["body"])
        self.scopes.pop()
        self.return_type = VOID

    def visit_declaration(self, node):
        type_ = self.read_type(node["type"])
        category = {"Typedef": "typedef"}.get(node["kind"], "object")
        if type_[0] == "function":
            category = "function"
            self.validate_collection(node, type_[1])
            for parameter in type_[2] or ():
                self.validate_collection(node, parameter)
        self.validate_collection(node, type_)

        capacity = node.get("capacity")
        initializer = node.get("init")
        if node["kind"] == "CollectionDeclaration":
            if capacity:
                self.validate_capacity(capacity)
            mode = "alias" if initializer else "fixed" if capacity else "dynamic"
            node["semantic"] = {"type": type_, "capacity_mode": mode}
        elif type_[0] == "collection" and len(self.scopes) == 1:
            self.error(node, "coleções devem ser declaradas dentro de uma função")

        self.declare(node, type_, category)
        if initializer:
            actual = self.expression(initializer)
            self.check_collection_assignment(node, type_, actual, initializer)

    def validate_capacity(self, node):
        type_ = self.expression(node)
        if node["kind"] == "ID" and self.lookup(node["name"]) is None:
            self.error(node, f"capacidade usa identificador não declarado: {node['name']!r}")
        elif not integer(type_):
            self.error(node, "a capacidade deve ter tipo inteiro")
        elif node["kind"] == "Constant" and integer_literal(node["value"]) <= 0:
            self.error(node, "a capacidade literal deve ser positiva")

    def check_collection_assignment(self, node, expected, actual, expression):
        if "collection" not in {expected[0], actual[0]}:
            return
        if actual == UNKNOWN and expression and expression["kind"] == "ID":
            self.error(expression, f"identificador não declarado: {expression['name']!r}")
        elif not compatible(expected, actual, expression):
            self.error(node, "tipos de coleção incompatíveis")

    def expression(self, node):
        if node is None:
            return UNKNOWN
        kind = node["kind"]
        if kind == "ID":
            symbol = self.lookup(node["name"])
            if symbol:
                return symbol["type"] if symbol["category"] != "typedef" else UNKNOWN
            if node["name"] in {"true", "false"}:
                return ("scalar", "_Bool")
            if node["name"] == "NULL":
                return ("pointer", VOID)
            return UNKNOWN
        if kind == "Constant":
            if node["type"] == "string":
                return ("array", ("scalar", "char"))
            return ("scalar", node["type"])
        if kind == "FuncCall":
            return self.call(node)
        if kind == "Assignment":
            expected = self.expression(node["lvalue"])
            actual = self.expression(node["rvalue"])
            self.check_collection_assignment(node, expected, actual, node["rvalue"])
            if expected[0] == "collection" and node["op"] != "=":
                self.error(node, "atribuições de coleção exigem o operador '='")
            return expected
        if kind == "StructRef":
            receiver = self.expression(node["name"])
            if receiver[0] == "collection":
                field = node["field"]
                method = field["name"]
                structure = receiver[1]
                if method in METHODS[structure] or method in COMMON_METHODS:
                    self.error(field, f"use {method}() para chamar o método de {structure}")
                else:
                    self.error(field, f"{structure} não possui o membro {method!r}")
                return UNKNOWN
            if node["type"] == "->" and receiver[0] == "pointer":
                receiver = receiver[1]
            return self.record_fields.get(receiver, {}).get(node["field"]["name"], UNKNOWN)
        if kind == "ArrayRef":
            receiver = self.expression(node["name"])
            self.expression(node["subscript"])
            if receiver[0] == "collection":
                self.error(node, "coleções Cuco exigem métodos para acessar elementos")
            return receiver[1] if receiver[0] in {"array", "pointer"} else UNKNOWN
        if kind == "Cast":
            self.expression(node["expr"])
            return self.read_type(node["to_type"])
        if kind == "UnaryOp":
            operand = self.expression(node["expr"])
            if node["op"] in {"sizeof", "_Alignof"}:
                return ("scalar", "size_t")
            if node["op"] == "&":
                return ("pointer", operand)
            if node["op"] == "*" and operand[0] == "pointer":
                return operand[1]
            if node["op"] == "!":
                return ("scalar", "int")
            return operand
        if kind == "BinaryOp":
            left = self.expression(node["left"])
            right = self.expression(node["right"])
            if node["op"] in {"<", "<=", ">", ">=", "==", "!=", "&&", "||"}:
                return ("scalar", "int")
            if numeric(left) and numeric(right):
                return left if not integer(left) else right
            return UNKNOWN
        if kind == "TernaryOp":
            self.expression(node["cond"])
            left = self.expression(node["iftrue"])
            right = self.expression(node["iffalse"])
            return left if left == right else UNKNOWN
        if kind == "ExprList":
            result = UNKNOWN
            for expr in node["exprs"]:
                result = self.expression(expr)
            return result
        if kind == "CompoundLiteral":
            self.visit(node["init"])
            return self.read_type(node["type"])
        self.visit_children(node)
        return UNKNOWN

    def call(self, node):
        callee = node["name"]
        arguments = node["args"]["exprs"] if node["args"] else []
        types = [self.expression(argument) for argument in arguments]
        if callee["kind"] == "StructRef":
            receiver = self.expression(callee["name"])
            if receiver[0] == "collection":
                return self.collection_call(node, receiver, arguments, types)
            if callee["name"]["kind"] == "ID" and self.lookup(callee["name"]["name"]) is None:
                self.error(callee["name"], f"receptor não declarado: {callee['name']['name']!r}")
            if callee["type"] == "->" and receiver[0] == "pointer":
                receiver = receiver[1]
            function = self.record_fields.get(receiver, {}).get(callee["field"]["name"], UNKNOWN)
        else:
            function = self.expression(callee)
            if callee["kind"] == "ID" and callee["name"] == "free":
                if any(type_[0] == "collection" for type_ in types):
                    if len(types) != 1:
                        self.error(node, "free requer um argumento")
                    elif self.lookup("free") is None or function[0] == "function":
                        node["semantic"] = {"operation": "free", "receiver_type": types[0],
                                            "type": VOID}
                    return VOID
        if function[0] == "pointer":
            function = function[1]
        if function[0] != "function":
            return UNKNOWN

        _, result, parameters, variadic = function
        if parameters is not None:
            has_collection = any(type_[0] == "collection" for type_ in (*parameters, *types))
            if has_collection and (len(types) < len(parameters) or
                                   (not variadic and len(types) != len(parameters))):
                self.error(node, "quantidade de argumentos incompatível com a assinatura")
            for expected, actual, argument in zip(parameters, types, arguments):
                self.check_collection_assignment(argument, expected, actual, argument)
        return result

    def collection_call(self, node, receiver, arguments, types):
        _, structure, element = receiver
        callee = node["name"]
        method = callee["field"]["name"]
        definition = METHODS[structure].get(method) or COMMON_METHODS.get(method)
        if callee["type"] != ".":
            self.error(node, "métodos Cuco usam o operador '.'")
            return UNKNOWN
        if definition is None:
            self.error(callee["field"], f"{structure} não possui o método {method!r}")
            return UNKNOWN

        parameters, result = definition
        if len(arguments) != len(parameters):
            self.error(node, f"{method} espera {len(parameters)} argumento(s), recebeu {len(arguments)}")
        for expected, actual, argument in zip(parameters, types, arguments):
            if actual == UNKNOWN and argument["kind"] == "ID":
                self.error(argument, f"identificador não declarado: {argument['name']!r}")
            elif expected == "index" and actual != UNKNOWN and not integer(actual):
                self.error(argument, f"o índice de {method} deve ter tipo inteiro")
            elif expected == "element" and not compatible(element, actual, argument):
                self.error(argument, f"argumento incompatível com o tipo de elemento de {structure}")
        result_type = element if result == "element" else ("scalar", result)
        node["semantic"] = {"operation": method, "receiver_type": receiver, "type": result_type}
        return result_type


EXPRESSION_KINDS = {
    "ID", "Constant", "FuncCall", "Assignment", "StructRef", "ArrayRef", "Cast",
    "UnaryOp", "BinaryOp", "TernaryOp", "ExprList", "CompoundLiteral",
}


def analyze(tree: dict) -> dict:
    """Devolve uma cópia anotada da AST, os símbolos e os diagnósticos."""
    annotated = deepcopy(tree)
    analyzer = SemanticAnalyzer()
    for declaration in annotated["ext"]:
        analyzer.visit(declaration)
    return {"ast": annotated, "symbols": analyzer.symbols, "diagnostics": analyzer.diagnostics}
