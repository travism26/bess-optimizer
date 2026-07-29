# Search Logs Command

Search and analyze application output logs and debug information from the Python application.

## Usage

```bash
/search_logs [OPTIONS]
```

## Options

- `--pattern <regex>` - Search for pattern in log output
- `--level <level>` - Filter by severity (error, warn, info, debug)
- `--since <time>` - Show logs since a time (e.g., "5m", "1h", "2025-01-15")
- `--limit <n>` - Limit number of results (default: 50)

## Examples

### Search for errors in output
```bash
/search_logs --level error
```

### Search for specific pattern
```bash
/search_logs --pattern "connection.*timeout"
```

### Find recent errors
```bash
/search_logs --level error --since 1h
```

## Implementation

This command searches logs in project workspace directories and tool output files.

### Search project workspace
```bash
# Find log files
find . -name "*.log" -o -name "*_output.txt" | xargs grep "pattern"
```

### Time-based search (files modified in last hour)
```bash
find . -name "*.log" -mmin -60 -exec cat {} \;
```

## Tips

- Check stderr output for execution errors
- Use `-v` flag when running the application for more detailed logs
- Application execution logs contain exit codes and execution times

## Output Format

The command outputs logs in a readable format:
```
[2025-01-15 10:30:45] [INFO] Starting operation
[2025-01-15 10:30:46] [INFO] Processing request
[2025-01-15 10:32:15] [INFO] Operation completed successfully
[2025-01-15 10:32:16] [ERROR] Failed to connect: connection timeout
```

## Debugging Tips

When issues occur, check:
1. Application logs for errors
2. Configuration files
3. Environment variables
4. Python application logs (if using structured logging)
