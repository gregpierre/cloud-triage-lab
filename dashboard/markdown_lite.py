"""
A tiny Markdown-to-HTML converter for the runbook viewer.

It only supports what our runbooks actually use: headings, paragraphs,
ordered and unordered lists, `inline code`, and **bold**. Writing it by hand
keeps the project dependency-free (Flask is the only package).

Security note: all text is HTML-escaped *before* formatting is applied, so a
runbook containing <script> tags renders as plain text instead of running.
"""

import html
import re


def format_inline(text):
    """Escape HTML, then turn `code` and **bold** into tags."""
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def render(markdown_text):
    """Convert a Markdown string to an HTML string."""
    output = []
    paragraph = []      # lines of the paragraph currently being built
    list_tag = None     # "ul" or "ol" while inside a list
    list_items = []

    def flush_paragraph():
        if paragraph:
            output.append(f"<p>{format_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list():
        nonlocal list_tag
        if list_tag:
            items = "".join(f"<li>{format_inline(item)}</li>" for item in list_items)
            output.append(f"<{list_tag}>{items}</{list_tag}>")
            list_items.clear()
            list_tag = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()

        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        ordered = re.match(r"^\d+\.\s+(.*)$", line)
        unordered = re.match(r"^[-*]\s+(.*)$", line)

        if not line:
            flush_paragraph()
            flush_list()
        elif heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{format_inline(heading.group(2))}</h{level}>")
        elif ordered or unordered:
            flush_paragraph()
            tag = "ol" if ordered else "ul"
            if list_tag != tag:
                flush_list()
                list_tag = tag
            list_items.append((ordered or unordered).group(1))
        elif list_tag and raw_line.startswith(" "):
            # An indented line continues the previous list item.
            list_items[-1] += " " + line
        else:
            flush_list()
            paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "\n".join(output)
