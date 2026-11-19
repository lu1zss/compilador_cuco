import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

from src.lexer.lexer import LexerError, tokenize


def main() -> int:
    parser = argparse.ArgumentParser(description="Transpilador Cuco")
    stages = parser.add_subparsers(dest="stage", required=True)
    lexer = stages.add_parser("lexer", help="Exibe ou exporta os tokens de um arquivo")
    syntax = stages.add_parser("parser", help="Exibe ou exporta a árvore sintática")
    semantic = stages.add_parser("semantic", help="Valida tipos e operações da Cuco")
    build = stages.add_parser("build", aliases=["codegen"], help="Gera código C a partir de um arquivo Cuco")
    for stage in (lexer, syntax, semantic, build):
        stage.add_argument("source", type=Path, metavar="ARQUIVO")
        stage.add_argument("-o", "--output", type=Path, metavar="SAÍDA")
    args = parser.parse_args()
    if args.stage == "codegen":
        args.stage = "build"

    try:
        source = args.source.read_text(encoding="utf-8")
        tokens = tokenize(source)
        if args.stage != "lexer":
            from src.parser.parser import ParserError, parse

            try:
                data = parse(tokens)
            except ParserError as error:
                print(f"{args.source}:{error}", file=sys.stderr)
                return 1
        else:
            data = [asdict(token) for token in tokens]

        if args.stage in {"semantic", "build"}:
            from src.semantic.semantic import analyze

            data = analyze(data)
            for diagnostic in data["diagnostics"]:
                position = f"{diagnostic['line'] or '?'}:{diagnostic['column'] or '?'}"
                print(f"{args.source}:{position}: erro semântico: {diagnostic['message']}",
                      file=sys.stderr)
            if data["diagnostics"]:
                return 1

        if args.stage == "build":
            from src.codegen.codegen import CodegenError, generate

            try:
                data = generate(data)
            except CodegenError as error:
                print(f"{args.source}: erro de geração: {error}", file=sys.stderr)
                return 1

        if args.output:
            if args.output.resolve() == args.source.resolve():
                parser.error("o arquivo de saída precisa ser diferente do código-fonte")
            content = data if args.stage == "build" else (
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            args.output.write_text(content, encoding="utf-8")
        elif args.stage == "build":
            print(data, end="")
        elif args.stage != "lexer":
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            for token in tokens:
                print(f"{token.line}:{token.column:<4} {token.kind:<19} {token.lexeme}")
    except LexerError as error:
        print(f"{args.source}:{error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as error:
        print(f"cuco: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
