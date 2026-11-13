# DATUMOR Code Parsing

M2.3 uses `tree-sitter-language-pack` to parse supported source files.

## Supported extensions

Python, JavaScript, JSX, TypeScript, TSX, Java, C, C++, C#, Go, Rust, PHP and Ruby.

## Output

The parser returns the original source, language metadata, declaration records,
import records, source file paths, line and column locations, declaration
hierarchy, and syntax-error locations. Syntax errors are reported as warnings;
the original source is retained.

## Integration

`extract_document(path)` dispatches supported source-code extensions to
`code_parser.extract_code`. The result uses the existing extraction result
shape (`format`, `source_filename`, `content`, `records`, `metadata`,
`warnings`) with an additional `syntax_errors` field.

## Limitations

Tree-sitter provides syntactic structure, not full semantic resolution.
Import targets are preserved as source snippets and are not resolved against
the repository. Language-specific declaration coverage may be extended as
real repository verification identifies additional grammar constructs.
