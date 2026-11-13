from pathlib import Path
from typing import Any

from tree_sitter_language_pack import get_parser

from .metadata_extractor import extract_metadata


class CodeParsingError(Exception):
    """Raised when a source file cannot be parsed."""


LANGUAGES = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".java": "java", ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "c_sharp", ".go": "go", ".rs": "rust",
    ".php": "php", ".rb": "ruby",
}

FORMAT_ALIASES = {
    "py": "python", "pyw": "python",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "javascript", "ts": "typescript", "tsx": "tsx",
    "cs": "c_sharp", "csharp": "c_sharp",
    "cc": "cpp", "cxx": "cpp", "hpp": "cpp",
    "rs": "rust", "rb": "ruby",
}

DECLARATIONS = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
        "arrow_function": "function",
        "function_expression": "function",
    },
    "typescript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "abstract_class_declaration": "class",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "method_definition": "method",
        "method_signature": "method",
        "arrow_function": "function",
    },
    "tsx": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "method_definition": "method",
        "arrow_function": "function",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "record_declaration": "record",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "union_specifier": "union",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "namespace_definition": "namespace",
    },
    "c_sharp": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "struct_declaration": "struct",
        "enum_declaration": "enum",
        "record_declaration": "record",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "namespace_declaration": "namespace",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type",
    },
    "rust": {
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "implementation",
        "mod_item": "module",
        "type_item": "type",
    },
    "php": {
        "function_definition": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "trait_declaration": "trait",
        "enum_declaration": "enum",
        "method_declaration": "method",
    },
    "ruby": {
        "method": "method",
        "singleton_method": "method",
        "class": "class",
        "module": "module",
    },
}

IMPORT_TYPES = {
    "import_statement", "import_from_statement", "import_declaration",
    "import_clause", "namespace_import", "use_declaration",
    "namespace_use_declaration", "using_directive",
    "preproc_include", "include_directive",
    "package_clause",
}

NAME_FIELDS = ("name", "declarator", "type", "path")


def _node_name(node: Any, source: bytes) -> str | None:
    for field in NAME_FIELDS:
        child = node.child_by_field_name(field)
        if child is not None:
            value = source[child.start_byte:child.end_byte].decode(
                "utf-8", errors="replace"
            ).strip()
            if value:
                return value

    for child in node.named_children:
        if child.type in {
            "identifier", "type_identifier", "field_identifier",
            "constant", "namespace_identifier", "property_identifier",
        }:
            value = source[child.start_byte:child.end_byte].decode(
                "utf-8", errors="replace"
            ).strip()
            if value:
                return value
    return None


def _source_text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode(
        "utf-8", errors="replace"
    )


def extract_code(path: str | Path, detected_format: str | None = None) -> dict:
    path = Path(path)
    if not path.is_file():
        raise CodeParsingError(f"Source file does not exist: {path}")

    language = (
        FORMAT_ALIASES.get((detected_format or "").lower())
        or (detected_format.lower() if detected_format else None)
        or LANGUAGES.get(path.suffix.lower())
    )
    if language not in DECLARATIONS:
        raise CodeParsingError(
            f"Unsupported source-code format: {detected_format or path.suffix}"
        )

    try:
        source_text = path.read_text(encoding="utf-8-sig")
        source = source_text.encode("utf-8")
        parser = get_parser(language)
        tree = parser.parse(source)
    except Exception as exc:
        raise CodeParsingError(
            f"Unable to parse {path.name} as {language}: {exc}"
        ) from exc

    declarations = DECLARATIONS[language]
    records = []
    warnings = []
    declaration_counter = 0
    import_counter = 0
    syntax_errors = []

    def walk(node: Any, parent_id: str | None = None) -> None:
        nonlocal declaration_counter, import_counter

        current_parent = parent_id
        node_type = node.type

        if node_type in declarations:
            declaration_counter += 1
            record_id = f"decl-{declaration_counter:06d}"
            records.append({
                "record_type": "declaration",
                "record_id": record_id,
                "declaration_type": declarations[node_type],
                "syntax_type": node_type,
                "name": _node_name(node, source),
                "parent_id": parent_id,
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
                "start_column": node.start_point.column + 1,
                "end_column": node.end_point.column + 1,
                "source_code": _source_text(node, source),
                "file_path": path.as_posix(),
            })
            current_parent = record_id

        if node_type in IMPORT_TYPES:
            import_counter += 1
            records.append({
                "record_type": "import",
                "record_id": f"import-{import_counter:06d}",
                "syntax_type": node_type,
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
                "source_code": _source_text(node, source),
                "file_path": path.as_posix(),
            })

        if node.is_error or node.is_missing:
            syntax_errors.append({
                "syntax_type": node_type,
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
                "source_code": _source_text(node, source)[:500],
                "is_missing": bool(node.is_missing),
                "is_error": bool(node.is_error),
            })

        for child in node.children:
            walk(child, current_parent)

    walk(tree.root_node)

    if tree.root_node.has_error and not syntax_errors:
        syntax_errors.append({
            "syntax_type": "RECOVERED_SYNTAX_ERROR",
            "start_line": tree.root_node.start_point.row + 1,
            "end_line": tree.root_node.end_point.row + 1,
            "source_code": source_text[:500],
            "is_missing": False,
            "is_error": True,
        })

    if syntax_errors:
        warnings.append(
            f"Parser reported {len(syntax_errors)} syntax error or missing-node location(s)."
        )

    parser_metadata = {
        "language": language,
        "file_path": path.as_posix(),
        "line_count": len(source_text.splitlines()),
        "character_count": len(source_text),
        "declaration_count": declaration_counter,
        "import_count": import_counter,
        "syntax_error_count": len(syntax_errors),
        "has_syntax_errors": bool(syntax_errors),
        "parser": "tree-sitter-language-pack",
    }
    normalized_metadata = extract_metadata(
        path,
        detected_format=language,
        content=source_text,
        existing_metadata=parser_metadata,
    )

    return {
        "format": "code",
        "source_filename": path.name,
        "content": source_text,
        "records": records,
        "metadata": normalized_metadata,
        "warnings": warnings,
        "syntax_errors": syntax_errors,
    }
