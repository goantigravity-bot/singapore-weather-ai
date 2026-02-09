#!/bin/bash
# 将 Markdown 文件转换为带有专业样式的 HTML
# 支持 Mermaid 图表渲染
# 使用方法: ./md-to-html.sh <input.md> [output.html]
# 样式参考: customs-sso 项目

set -e

INPUT="$1"
OUTPUT="${2:-${INPUT%.md}.html}"

if [ -z "$INPUT" ]; then
  echo "Usage: $0 <input.md> [output.html]"
  exit 1
fi

if ! command -v grip &> /dev/null; then
  echo "Error: grip not found. Install with: pip3 install grip"
  exit 1
fi

echo "Converting $INPUT → $OUTPUT ..."
grip "$INPUT" --export "$OUTPUT"

python3 << PYEOF
f = '$OUTPUT'
css = """<style>
/* 表格样式 — 参考 customs-sso 项目 */
table {
  border-collapse: collapse !important;
  width: max-content !important;
  min-width: 100% !important;
  max-width: 95vw !important;
  table-layout: auto !important;
}
th, td {
  border: 1px solid #d0d7de !important;
  padding: 12px 18px !important;
  line-height: 1.6 !important;
  vertical-align: top !important;
  text-align: left !important;
  white-space: nowrap !important;
}
td:last-child, th:last-child {
  white-space: normal !important;
}
thead tr { background: #f6f8fa !important; }
tr:nth-child(even) { background: #f9fafb !important; }

/* 代码块增强 */
pre {
  max-width: 95vw !important;
  overflow-x: auto !important;
}

/* Mermaid 图表容器 */
.mermaid {
  text-align: center !important;
  margin: 20px 0 !important;
}
</style>
<!-- Mermaid JS 支持 -->
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({startOnLoad:true, theme:'default', securityLevel:'loose'});</script>
"""

with open(f) as file:
    html = file.read()

# 注入 CSS 和 Mermaid JS
html = html.replace('</head>', css + '</head>', 1)

# grip 将 mermaid 渲染为 <div class="highlight highlight-source-mermaid"><pre><span>...</span></pre></div>
# 需要去除 span 标签恢复纯文本，再包裹在 <div class="mermaid"> 中供 Mermaid JS 渲染
import re

def strip_html_tags(text):
    """去除 HTML 标签，只保留纯文本"""
    return re.sub(r'<[^>]+>', '', text)

def replace_mermaid(match):
    raw = match.group(1)
    # 去除 grip 注入的 <span> 语法高亮标签
    code = strip_html_tags(raw)
    # 恢复 HTML 实体
    code = code.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
    return f'<div class="mermaid">{code}</div>'

html = re.sub(
    r'<div class="highlight highlight-source-mermaid[^"]*"[^>]*>\s*<pre[^>]*>(.*?)</pre>\s*</div>',
    replace_mermaid,
    html,
    flags=re.DOTALL
)

with open(f, 'w') as file:
    file.write(html)
PYEOF

echo "✅ Done: $OUTPUT"
