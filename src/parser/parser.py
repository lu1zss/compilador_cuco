import re

from pycparser import c_ast, c_lexer, c_parser

from src.lexer.lexer import Token


SIZE_T_HEADER = re.compile(r"#\s*include\s*<(?:stddef|stdio|stdlib|string|time|wchar|uchar)\.h>")

COLLECTIONS = {"List", "Stack", "Queue"}
C_SYMBOLS = {token.literal: token.tok_type for token in c_lexer._fixed_tokens}


class ParserError(ValueError):
    pass


class ParserLexer(c_lexer.CLexer):
    """Adapta os tokens da Cuco à interface usada pela gramática de C."""

    def token(self):
        for token in self.source_tokens:
            if token.kind == "DIRECTIVE":
                continue
            if token.kind == "EOF":
                return None
            return self.convert(token)
        return None

    def convert(self, token: Token):
        lexeme = token.lexeme
        if token.kind == "IDENTIFIER":
            kind = "TYPEID" if self.type_lookup_func(lexeme) else "ID"
        elif token.kind.startswith("KW_"):
            kind = c_lexer._keyword_map.get(lexeme)
            if kind is None:
                raise ParserError(
                    f"{token.line}:{token.column}: palavra-chave fora do recorte: {lexeme}"
                )
        elif lexeme in C_SYMBOLS:
            kind = C_SYMBOLS[lexeme]
            if kind == "LBRACE":
                self.on_lbrace_func()
            elif kind == "RBRACE":
                self.on_rbrace_func()
        else:
            # A gramática C distingue subtipos de literais, como hexadecimal e octal.
            # Refina apenas o literal já delimitado pelo lexer da Cuco.
            self.input(lexeme, self.filename)
            try:
                literal = super().token()
            except ParserError as error:
                raise ParserError(
                    f"{token.line}:{token.column}: erro sintático: literal inválido: {lexeme}"
                ) from error
            if literal is None or literal.value != lexeme:
                raise ParserError(f"{token.line}:{token.column}: literal inválido: {lexeme}")
            kind = literal.type
        return c_lexer._Token(kind, lexeme, token.line, token.column)


class CollectionType(c_ast.Node):
    __slots__ = ("structure", "element_type", "coord")
    attr_names = ("structure",)

    def __init__(self, structure, element_type, coord):
        self.structure = structure
        self.element_type = element_type
        self.coord = coord

    def children(self):
        return (("element_type", self.element_type),)


class CollectionDeclaration(c_ast.Node):
    __slots__ = ("name", "type", "capacity", "init", "coord")
    attr_names = ("name",)

    def __init__(self, name, type_, capacity, init, coord):
        self.name = name
        self.type = type_
        self.capacity = capacity
        self.init = init
        self.coord = coord

    def children(self):
        return tuple((name, getattr(self, name)) for name in ("type", "capacity", "init")
                     if getattr(self, name) is not None)


class CucoParser(c_parser.CParser):
    def __init__(self, tokens: list[Token]):
        super().__init__(lexer=ParserLexer)
        self.clex.source_tokens = iter(tokens)
        self.end_token = tokens[-1]
        self.has_size_t = any(
            token.kind == "DIRECTIVE" and SIZE_T_HEADER.match(token.lexeme)
            for token in tokens
        )

    def parse_tokens(self):
        return super().parse("")

    def _parse_translation_unit_or_empty(self):
        # O parser de C reinicializa o escopo no começo de parse().
        if self.has_size_t:
            self._scope_stack[0]["size_t"] = True
        return super()._parse_translation_unit_or_empty()

    def _parse_error(self, msg, coord):
        if not isinstance(coord, c_parser.Coord):
            coord = self._coord(self.end_token.line, self.end_token.column)
        raise ParserError(f"{coord.line}:{coord.column}: erro sintático: {msg}")

    def _starts_collection(self):
        token = self._peek()
        if token is None or token.type != "ID" or token.value not in COLLECTIONS:
            return False
        following = self._peek_type(2)
        if following in {"ID", "TYPEID"}:
            return True
        if following != "LT":
            return False
        # Um nome de estrutura também pode ser uma variável em uma comparação.
        # Com '<', reconhecemos a declaração quando começa um nome de tipo C.
        element = self._peek(3)
        if element is None:
            return False
        if element.type == "ID" and not any(token.value in scope for scope in self._scope_stack):
            # Uma declaração com tipo desconhecido deve produzir erro, em vez
            # de passar como duas comparações encadeadas.
            return self._peek_type(4) in {"GT", "LT", "TIMES"}
        return element.type in c_parser._TYPE_SPEC_SIMPLE or element.type in {
            "TYPEID", "STRUCT", "UNION", "ENUM", "CONST", "VOLATILE", "RESTRICT",
            "_ATOMIC",
        }

    def _starts_declaration(self, tok=None):
        return self._starts_collection() or super()._starts_declaration(tok)

    def _parse_declaration_specifiers(self, allow_no_type=False):
        if self._starts_collection():
            type_ = self.parse_collection_type()
            spec = self._add_declaration_specifier(None, type_, "type", append=True)
            return spec, True, type_.coord
        return super()._parse_declaration_specifiers(allow_no_type)

    def parse_collection_type(self):
        structure = self._advance()
        coord = self._tok_coord(structure)
        if self._accept("LT"):
            element_type = self._parse_type_name()
            self._expect("GT")
        else:
            element_type = c_ast.IdentifierType(["int"], coord=coord)
        return CollectionType(structure.value, element_type, coord)

    def _parse_decl_body(self):
        if not self._starts_collection():
            return super()._parse_decl_body()

        type_ = self.parse_collection_type()
        name = self._advance()
        coord = self._tok_coord(name)
        if name.type not in {"ID", "TYPEID"}:
            self._parse_error("esperado o nome da coleção", coord)
        self._add_identifier(name.value, coord)

        capacity = None
        initializer = None
        if self._accept("LT"):
            capacity = self.parse_capacity()
            self._expect("GT")
        elif self._accept("EQUALS"):
            initializer = self._parse_assignment_expression()

        return [CollectionDeclaration(name.value, type_, capacity, initializer, coord)]

    def parse_capacity(self):
        token = self._advance()
        coord = self._tok_coord(token)
        if token.type == "ID":
            return c_ast.ID(token.value, coord)
        if token.type.startswith("INT_CONST"):
            return c_ast.Constant("int", token.value, coord)
        self._parse_error("esperado um literal inteiro ou identificador para a capacidade", coord)


def serialize(node):
    if isinstance(node, c_ast.Node):
        result = {"kind": type(node).__name__}
        if node.coord is not None:
            result["line"] = node.coord.line
            result["column"] = node.coord.column
        for field in node.__slots__:
            if field not in {"coord", "__weakref__"}:
                result[field] = serialize(getattr(node, field))
        return result
    if isinstance(node, list):
        return [serialize(item) for item in node]
    return node


def parse(tokens: list[Token]) -> dict:
    """Recebe a lista do lexer, incluindo o token EOF."""
    if not tokens or tokens[-1].kind != "EOF":
        raise ParserError("esperado o token EOF ao final da lista")
    tree = serialize(CucoParser(tokens).parse_tokens())
    tree["directives"] = [
        {"kind": "Include", "lexeme": token.lexeme, "line": token.line, "column": token.column}
        for token in tokens if token.kind == "DIRECTIVE"
    ]
    return tree
