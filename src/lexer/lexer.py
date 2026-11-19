"""Análise léxica do subconjunto inicial de C17 usado pela Cuco."""

import json
import re
from dataclasses import dataclass
from pathlib import Path


INTEGER_SUFFIX = r"(?:[uU](?:ll|LL|[lL])?|(?:ll|LL|[lL])[uU]?)?"
INTEGER = re.compile(r"(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)" + INTEGER_SUFFIX)
DECIMAL = r"(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[0-9]+[eE][+-]?[0-9]+"
HEX_FLOAT = r"0[xX](?:[0-9a-fA-F]+\.?[0-9a-fA-F]*|\.[0-9a-fA-F]+)[pP][+-]?[0-9]+"
FLOAT = re.compile(rf"(?:{DECIMAL}|{HEX_FLOAT})[fFlL]?")

DIRECTIVE = re.compile(r"#[ \t]*include[ \t]*(?:<[^<>\r\n]+>|\"[^\"\r\n]+\")"
                       r"(?:[ \t]|/\*[^\r\n]*?\*/)*(?://[^\r\n]*)?")
NEWLINE = re.compile(r"\r\n?|\n")


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    lexeme: str
    line: int
    column: int


class LexerError(ValueError):
    def __init__(self, message: str, line: int, column: int):
        super().__init__(f"{line}:{column}: erro léxico: {message}")


RULES_PATH = Path(__file__).with_name("lexer_rules.json")


def load_rules() -> tuple[tuple[re.Pattern[str], str], ...]:
    with RULES_PATH.open(encoding="utf-8") as config:
        rules = json.load(config)

    return tuple((re.compile(rule["pattern"]), rule["action"]) for rule in rules)


COMPILED_RULES = load_rules()


def classify_number(lexeme: str, line: int, column: int) -> str:
    if INTEGER.fullmatch(lexeme):
        return "INTEGER_LITERAL"
    if FLOAT.fullmatch(lexeme):
        return "FLOAT_LITERAL"
    raise LexerError(f"literal numérico inválido {lexeme!r}", line, column)


def apply_rule(action: str, lexeme: str, line: int, column: int,
               at_line_start: bool) -> str | None:
    """Executa as ações que exigem mais do que emitir o tipo do token."""
    if action == "IGNORAR":
        return None
    if action == "COMENTARIO_ABERTO":
        raise LexerError("comentário de bloco sem fechamento", line, column)
    if action == "LITERAL_INVALIDO":
        raise LexerError("literal de texto inválido ou sem fechamento", line, column)
    if action == "DESCONHECIDO":
        raise LexerError(f"caractere inesperado {lexeme!r}", line, column)
    if action == "DIRECTIVE" and not (at_line_start and DIRECTIVE.fullmatch(lexeme)):
        raise LexerError("apenas diretivas #include simples são suportadas", line, column)
    if action == "NUMERO":
        return classify_number(lexeme, line, column)
    return action


def tokenize(source: str) -> list[Token]:
    tokens = []
    offset = 0
    line = column = 1
    at_line_start = True

    while offset < len(source):
        for pattern, action in COMPILED_RULES:
            match = pattern.match(source, offset)
            if match is not None:
                break
        else:
            raise LexerError(f"caractere inesperado {source[offset]!r}", line, column)

        if match.end() == offset:
            raise LexerError(f"a regra {pattern.pattern!r} casou sem consumir caracteres",
                             line, column)

        lexeme = match.group()
        kind = apply_rule(action, lexeme, line, column, at_line_start)
        if kind is not None:
            tokens.append(Token(kind, lexeme, line, column))

        lines = NEWLINE.split(lexeme)
        if len(lines) > 1:
            line += len(lines) - 1
            column = len(lines[-1]) + 1
            at_line_start = True
        else:
            column += len(lexeme)
            if kind is not None:
                at_line_start = False
        offset = match.end()

    tokens.append(Token("EOF", "", line, column))
    return tokens
