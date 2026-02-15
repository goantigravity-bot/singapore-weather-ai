#!/usr/bin/env python3
"""Convert docs/*.md to styled dark-theme HTML with Mermaid.js support.

Usage:
    python3 scripts/md-to-html.py                           # Convert all docs/*.md
    python3 scripts/md-to-html.py docs/server-infrastructure.md  # Convert specific file
"""

import sys
import os
import re
import markdown

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #e2e8f0;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --accent2: #a78bfa;
            --border: #334155;
            --success: #4ade80;
            --warn: #fbbf24;
            --danger: #f87171;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.7;
            padding: 2rem;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}

        h1 {{
            font-size: 1.8rem; font-weight: 700; margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #38bdf8, #a78bfa);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        h2 {{
            font-size: 1.35rem; font-weight: 600; color: var(--accent);
            margin: 2rem 0 1rem; padding-bottom: 0.4rem;
            border-bottom: 1px solid var(--border);
        }}
        h3 {{
            font-size: 1.1rem; font-weight: 600; color: var(--accent2);
            margin: 1.5rem 0 0.8rem;
        }}
        h4 {{ font-size: 0.95rem; font-weight: 600; color: var(--text); margin: 1rem 0 0.5rem; }}
        p {{ margin-bottom: 0.8rem; }}
        hr {{ border: none; border-top: 1px solid var(--border); margin: 2rem 0; }}
        a {{ color: var(--accent); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}

        blockquote {{
            border-left: 3px solid var(--accent); padding: 0.5rem 1rem;
            background: rgba(56,189,248,0.06); margin: 1rem 0; border-radius: 0 8px 8px 0;
            color: var(--text-muted);
        }}

        code {{
            font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.85em;
            background: rgba(56,189,248,0.1); padding: 0.15rem 0.4rem;
            border-radius: 4px; color: var(--accent);
        }}
        pre {{
            background: var(--card-bg); border: 1px solid var(--border);
            border-radius: 8px; padding: 1rem 1.2rem; margin: 1rem 0;
            overflow-x: auto; line-height: 1.5;
        }}
        pre code {{
            background: none; padding: 0; color: var(--text); font-size: 0.85rem;
        }}

        table {{
            width: 100%; border-collapse: collapse; margin: 1rem 0;
            background: var(--card-bg); border-radius: 8px; overflow: hidden;
            border: 1px solid var(--border);
        }}
        th, td {{
            text-align: left; padding: 0.6rem 1rem;
            border-bottom: 1px solid var(--border); font-size: 0.9rem;
        }}
        th {{
            color: var(--accent); font-weight: 600; font-size: 0.8rem;
            text-transform: uppercase; letter-spacing: 0.05em;
            background: rgba(56,189,248,0.06);
        }}
        td {{ color: var(--text-muted); }}
        td:first-child {{ color: var(--text); font-weight: 500; }}
        tr:hover td {{ background: rgba(56,189,248,0.04); }}

        ul, ol {{ margin: 0.5rem 0 1rem 1.5rem; }}
        li {{ margin-bottom: 0.3rem; color: var(--text-muted); }}
        strong {{ color: var(--text); }}

        .mermaid {{
            display: flex; justify-content: center;
            padding: 1.5rem 0; overflow-x: auto;
        }}

        footer {{
            text-align: center; color: var(--text-muted); font-size: 0.85rem;
            margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
        <footer>Weather AI — {title} — Generated 2026-02-14</footer>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {{
                primaryColor: '#1e293b',
                primaryTextColor: '#e2e8f0',
                primaryBorderColor: '#475569',
                lineColor: '#64748b',
                secondaryColor: '#1e293b',
                tertiaryColor: '#0f172a',
                fontSize: '14px'
            }}
        }});
    </script>
</body>
</html>"""


def extract_mermaid_blocks(md_text):
    """Extract mermaid code blocks and replace with div placeholders."""
    blocks = []
    def replacer(match):
        blocks.append(match.group(1).strip())
        return f'<div class="mermaid">\n{match.group(1).strip()}\n</div>'
    result = re.sub(r'```mermaid\n(.*?)```', replacer, md_text, flags=re.DOTALL)
    return result


def fix_table_spacing(md_text):
    """Remove blank lines between table rows.

    Many editors (e.g. Doubao) export Markdown with blank lines between
    pipe-delimited table rows, which breaks the Python markdown parser.
    This collapses those blank lines so tables render correctly.
    """
    lines = md_text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        result.append(lines[i])
        # If current line is a table row, skip any immediately following blank lines
        # before the next table row
        if lines[i].strip().startswith('|') and lines[i].strip().endswith('|'):
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                # Peek ahead: only skip blank line if next non-empty line is also a table row
                k = j + 1
                while k < len(lines) and lines[k].strip() == '':
                    k += 1
                if k < len(lines) and lines[k].strip().startswith('|'):
                    j += 1  # skip this blank line
                else:
                    break
            i = j
        else:
            i += 1
    return '\n'.join(result)


def convert_md_to_html(md_path, html_path):
    """Convert a markdown file to dark-themed HTML."""
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Extract title from first H1
    title_match = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
    title = title_match.group(1) if title_match else os.path.basename(md_path)

    # Fix table spacing (remove blank lines between table rows)
    md_text = fix_table_spacing(md_text)

    # Handle mermaid blocks before markdown conversion
    md_text = extract_mermaid_blocks(md_text)

    # Convert markdown to HTML
    html_content = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'codehilite', 'toc'],
        extension_configs={'codehilite': {'css_class': 'highlight', 'guess_lang': False}}
    )

    # Build final HTML
    final_html = HTML_TEMPLATE.format(title=title, content=html_content)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(final_html)

    print(f"✅ {os.path.basename(md_path)} → {os.path.basename(html_path)}")


def main():
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs')

    if len(sys.argv) > 1:
        # Convert specific files
        for md_path in sys.argv[1:]:
            html_path = md_path.rsplit('.', 1)[0] + '.html'
            convert_md_to_html(md_path, html_path)
    else:
        # Convert all .md in docs/
        for f in sorted(os.listdir(docs_dir)):
            if f.endswith('.md'):
                md_path = os.path.join(docs_dir, f)
                html_path = os.path.join(docs_dir, f.rsplit('.', 1)[0] + '.html')
                convert_md_to_html(md_path, html_path)


if __name__ == '__main__':
    main()
