---
description: Convert Markdown document to styled dark-theme HTML with Mermaid
---

# Convert MD to HTML

This workflow converts a specified Markdown (`.md`) file to a styled HTML (`.html`) file using the built-in python script `tools/md-to-html.py`.
The tool is particularly useful because it:
- Supports Mermaid diagrams
- Uses a dark-theme UI
- Handles table spacing issues

## Instructions

1. Identify the absolute path to the Markdown file you want to convert. Let's call it `TARGET_MD`.
2. Ensure you are working in the project root directory: `/Users/jinhui/development/tools/claude-skill`
3. Run the python script with the target file as an argument.

// turbo
```bash
python3 tools/md-to-html.py <TARGET_MD>
```

4. The script will generate the corresponding `.html` file in the same directory as the `.md` file.
