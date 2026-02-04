# Repository Analysis Tools

The AI Assistant includes tools for analyzing code repositories. These tools enable the assistant to read, search, and understand code, supporting features like:

- Answering questions about the codebase
- Finding function definitions and usages
- Reviewing code structure
- Self-improvement capabilities

## Available Tools

### `read_file`
Read the contents of a file with line numbers.

**Parameters:**
- `file_path` (required): Path to the file
- `max_length` (optional): Maximum characters to return (default: 50000)
- `start_line` (optional): First line to read (default: 1)
- `end_line` (optional): Last line to read (default: all)

**Example:**
```
read_file("/path/to/file.py", start_line=10, end_line=50)
```

### `list_files`
List files in a directory with optional pattern matching.

**Parameters:**
- `directory` (optional): Directory to list (default: project root)
- `pattern` (optional): Glob pattern (e.g., "*.py", default: "*")
- `recursive` (optional): Search subdirectories (default: false)
- `include_hidden` (optional): Include hidden files (default: false)

**Example:**
```
list_files("src/", pattern="*.ts", recursive=true)
```

### `search_code`
Search for patterns in code files using regex.

**Parameters:**
- `pattern` (required): Regex search pattern
- `directory` (optional): Directory to search (default: project root)
- `file_pattern` (optional): Glob filter for files (default: "*")
- `context_lines` (optional): Lines of context (default: 2)
- `max_results` (optional): Maximum matches (default: 50)
- `case_sensitive` (optional): Case-sensitive (default: true)

**Example:**
```
search_code("def\\s+process_", file_pattern="*.py")
```

### `get_file_info`
Get file metadata without reading contents.

**Parameters:**
- `file_path` (required): Path to the file

Returns: path, size, type, whether it's binary, and if it can be read.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REPOSITORY_PATHS` | Genesis project root | Colon-separated list of allowed directories |
| `REPOSITORY_MAX_FILE_SIZE` | 1048576 (1MB) | Maximum file size to read |
| `ASSISTANT_PERMISSION_LEVEL` | 1 (LOCAL) | Permission level required |

### Settings (via UI/API)

- `repository_paths`: Allowed directories (colon-separated)
- `repository_max_file_size`: Max file size in bytes

## Security

### Permission Requirements

All repository tools require **LOCAL** permission level or higher. This means:
- SANDBOX (0): ❌ Cannot use repository tools
- LOCAL (1): ✅ Can access allowed directories
- SYSTEM (2): ✅ Full access
- FULL (3): ✅ Full access

Set permission level via environment:
```bash
export ASSISTANT_PERMISSION_LEVEL=1
```

### Path Restrictions

- **Allowed Directories**: Files must be within `REPOSITORY_PATHS`
- **Path Traversal Protection**: `../` escapes are blocked
- **Symlink Resolution**: Symlinks are resolved before validation

### Sensitive File Filtering

These patterns are automatically blocked:
- `.env`, `.env.*` - Environment files
- `*.pem`, `*.key` - Private keys
- `*credentials*`, `*secrets*`, `*password*` - Credential files
- `id_rsa*`, `id_ed25519*` - SSH keys
- `.npmrc`, `.pypirc` - Token files
- `*.sqlite*` - Database files

### Binary File Detection

Binary files are detected by:
1. File extension (`.exe`, `.zip`, `.png`, etc.)
2. MIME type detection
3. Content analysis (null bytes)

Binary files cannot be read (use appropriate tools instead).

## Examples

### Explore Project Structure
```
Assistant, show me the structure of the src/ directory

-> list_files("src/", recursive=true)
```

### Find Function Definitions
```
Where is the login function defined?

-> search_code("def login|function login", file_pattern="*.py,*.js")
```

### Read Implementation
```
Show me the chat endpoint implementation

-> search_code("@router.post.*chat", file_pattern="*.py")
-> read_file("server/routes/chat.py", start_line=50, end_line=150)
```

### Check File Before Reading
```
Is config.json readable?

-> get_file_info("config.json")
```

## Troubleshooting

### "Path not in allowed directories"
The file is outside `REPOSITORY_PATHS`. Either:
- Move the file into an allowed directory
- Add the parent directory to `REPOSITORY_PATHS`

### "Requires LOCAL permission"
Set the permission level:
```bash
export ASSISTANT_PERMISSION_LEVEL=1
```

### "Binary file" errors
The file was detected as binary. Use appropriate tools for binary files (e.g., image viewers, archive tools).

### "File too large"
Increase `REPOSITORY_MAX_FILE_SIZE` or read a portion using `start_line`/`end_line`.

### "Sensitive file pattern"
The file matches a sensitive pattern and cannot be read. This is a security feature.
