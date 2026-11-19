"""Reduz os nós Cuco a C e delega a formatação ao pycparser."""

from pathlib import Path
import re

from pycparser import c_ast
from pycparser.c_generator import CGenerator


class CodegenError(ValueError):
    pass


# Cada operação informa retorno, parâmetros adicionais e corpo em C.
COMMON = {
    "size": ("size_t", "", "return cuco_check(buffer)->length;"),
    "capacity": ("size_t", "", "return cuco_check(buffer)->capacity;"),
    "isEmpty": ("bool", "", "return cuco_check(buffer)->length == 0;"),
    "isFull": ("bool", "", "return cuco_check(buffer)->length == buffer->capacity;"),
    "clear": ("void", "", "cuco_check(buffer)->length = 0;\nbuffer->head = 0;"),
    "free": ("void", "", "cuco_destroy(buffer);"),
}
APPEND = ("bool", ", T value", "return cuco_append(buffer, &value);")
GET = "T value;\nmemcpy(&value, cuco_element(buffer, index), sizeof value);\nreturn value;"
METHODS = {
    "List": {
        "add": APPEND,
        "insert": ("bool", ", uintmax_t index, T value", "return cuco_insert(buffer, index, &value);"),
        "get": ("T", ", uintmax_t index", GET),
        "set": ("void", ", uintmax_t index, T value",
                "memcpy(cuco_element(buffer, index), &value, sizeof value);"),
        "remove": ("T", ", uintmax_t index",
                   "T value;\ncuco_remove(buffer, index, &value);\nreturn value;"),
    },
    "Stack": {
        "push": APPEND,
        "peek": ("T", "", "size_t index = cuco_check(buffer)->length - 1;\n" + GET),
        "pop": ("T", "", "size_t index = cuco_check(buffer)->length - 1;\n"
                "T value;\ncuco_remove(buffer, index, &value);\nreturn value;"),
    },
    "Queue": {
        "enqueue": APPEND,
        "peek": ("T", "", "size_t index = 0;\n" + GET),
        "dequeue": ("T", "", "T value;\n"
                    "memcpy(&value, cuco_element(buffer, 0), sizeof value);\n"
                    "buffer->head = (buffer->head + 1) % buffer->capacity;\n"
                    "buffer->length--;\nreturn value;"),
    },
}


def type_key(value):
    if isinstance(value, (list, tuple)):
        return tuple(type_key(part) for part in value)
    return value


class Generator:
    def __init__(self, result):
        self.tree = result["ast"]
        self.symbols = result["symbols"]
        self.c = CGenerator()
        self.specializations = {}
        self.pending = []
        self.aliases = {}
        source_words = repr(self.tree)
        self.prefix = "cuco_"
        while re.search(r"\b" + self.prefix, source_words):
            self.prefix += "x_"

    def render_element(self, type_):
        if type_ in self.aliases:
            return self.aliases[type_]
        category, *parts = type_
        if category == "scalar":
            return parts[0]
        if category == "pointer":
            return self.render_element(parts[0]) + " *"
        if category in {"struct", "union", "enum"} and len(parts) == 1 and parts[0] and not parts[0].startswith("@"):
            return f"{category} {parts[0]}"
        raise CodegenError("o tipo de elemento precisa ter um nome acessível no escopo global")

    def specialize(self, type_):
        type_ = type_key(type_)
        if type_ not in self.specializations:
            _, structure, element = type_
            description = self.render_element(element)
            suffix = re.sub(r"\W+", "_", description.replace("*", " ptr")).strip("_")
            name = f"{self.prefix}{structure.lower()}_{suffix}"
            if name in self.specializations.values():
                name += f"_{len(self.specializations)}"
            self.specializations[type_] = name
            self.pending.append(self.specialization_code(structure, name, description))
        return self.specializations[type_]

    def specialization_code(self, structure, name, element):
        type_alias = name + "_element"
        lines = [
            f"typedef {element} {type_alias};",
            f"typedef {self.prefix}buffer {name};",
            f"static inline {name} *{name}_create(uintmax_t capacity, bool fixed)\n"
            "{\n"
            f"    return {self.prefix}create(capacity, fixed, sizeof({type_alias}));\n"
            "}",
        ]
        for method, (result, parameters, body) in (COMMON | METHODS[structure]).items():
            result = type_alias if result == "T" else result
            parameters = parameters.replace("T value", f"{type_alias} value")
            statements = "\n".join("    " + line for line in body.splitlines())
            statements = statements.replace("cuco_", self.prefix).replace("T value", f"{type_alias} value")
            lines.append(
                f"static inline {result} {name}_{method}({name} *buffer{parameters})\n"
                "{\n" + statements + "\n}"
            )
        return "\n\n".join(lines) + "\n\n"

    def lower(self, node):
        if isinstance(node, list):
            return [self.lower(child) for child in node]
        if not isinstance(node, dict):
            return node
        kind = node["kind"]
        if kind == "CollectionType":
            name = self.specialize(node["semantic_type"])
            return c_ast.IdentifierType([name, "*"])
        if kind == "CollectionDeclaration":
            return self.lower_declaration(node)
        if kind == "FuncCall" and "semantic" in node:
            return self.lower_call(node)

        cls = getattr(c_ast, kind)
        fields = {field: self.lower(node[field]) for field in cls.__slots__
                  if field not in {"coord", "__weakref__"}}
        return cls(**fields)

    def lower_declaration(self, node):
        name = self.specialize(node["semantic"]["type"])
        inner = c_ast.TypeDecl(node["name"], [], None, c_ast.IdentifierType([name]))
        type_ = c_ast.PtrDecl([], inner)
        if node["init"] is not None:
            init = self.lower(node["init"])
        else:
            fixed = node["capacity"] is not None
            capacity = self.lower(node["capacity"]) if fixed else c_ast.Constant("int", "0")
            init = c_ast.FuncCall(c_ast.ID(name + "_create"), c_ast.ExprList([
                capacity, c_ast.Constant("int", "1" if fixed else "0"),
            ]))
        return c_ast.Decl(node["name"], [], [], [], [], type_, init, None)

    def lower_call(self, node):
        info = node["semantic"]
        operation = info["operation"]
        name = self.specialize(info["receiver_type"]) + "_" + operation
        arguments = self.lower(node["args"]) if node["args"] else c_ast.ExprList([])
        if operation != "free":
            arguments.exprs.insert(0, self.lower(node["name"]["name"]))
        call = c_ast.FuncCall(c_ast.ID(name), arguments)

        if operation == "free" and isinstance(arguments.exprs[0], c_ast.ID):
            variable = arguments.exprs[0]
            reset = c_ast.Assignment("=", variable, c_ast.ID("NULL"))
            # O cast mantém o resultado void e agrupa a expressão com vírgula.
            void = c_ast.Typename(None, [], None, c_ast.TypeDecl(
                None, [], None, c_ast.IdentifierType(["void"])
            ))
            return c_ast.Cast(void, c_ast.ExprList([call, reset]))
        return call

    def generate(self):
        statements = []
        for node in self.tree["ext"]:
            statement = self.c.visit(c_ast.FileAST([self.lower(node)]))
            statements.extend(self.pending)
            self.pending.clear()
            statements.append(statement)
            if node["kind"] == "Typedef":
                for symbol in self.symbols:
                    if (symbol["category"] == "typedef" and symbol["depth"] == 0
                            and symbol["name"] == node["name"]):
                        self.aliases.setdefault(type_key(symbol["type"]), node["name"])
        directives = [node["lexeme"] for node in self.tree["directives"]]
        output = "\n".join(directives) + "\n\n" if directives else ""
        if self.specializations:
            runtime = Path(__file__).with_name("runtime.c").read_text(encoding="utf-8")
            output += runtime.replace("cuco_", self.prefix) + "\n"
        return output + "\n".join(statements)


def generate(result):
    if result["diagnostics"]:
        raise CodegenError("a AST contém erros semânticos")
    return Generator(result).generate()
