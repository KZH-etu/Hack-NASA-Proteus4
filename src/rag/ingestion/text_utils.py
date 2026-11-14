"""HTML-to-Markdown conversion and tag stripping utilities for the RAG pipeline."""

from __future__ import annotations

import html as html_lib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html_tags(text: str) -> str:
    """Remove any remaining HTML tags and decode HTML entities."""
    if not text:
        return ""
    unescaped = html_lib.unescape(text)
    cleaned = _TAG_RE.sub("", unescaped)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


class _StructuredHTMLMarkdownParser(HTMLParser):
    """Convert HTML into clean Markdown preserving h1/h2/h3 hierarchy without tags."""

    _SKIP_TAGS = {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "noscript",
        "svg",
        "button",
        "aside",
        "select",
    }
    _HEADING_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### "}
    _BLOCK_TAGS = {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "td",
        "th",
        "blockquote",
        "figcaption",
        "dd",
        "dt",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._block_stack: list[str] = []
        self._current: list[str] = []
        self.lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if t in self._BLOCK_TAGS:
            self._flush_current()
            self._block_stack.append(t)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if t in self._BLOCK_TAGS:
            self._flush_current(closing_tag=t)
            if self._block_stack and self._block_stack[-1] == t:
                self._block_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._current.append(data)

    def _flush_current(self, closing_tag: str | None = None) -> None:
        text = re.sub(r"\s+", " ", html_lib.unescape("".join(self._current))).strip()
        self._current = []
        if not text:
            return
        tag = closing_tag or (self._block_stack[-1] if self._block_stack else "")
        if tag in self._HEADING_PREFIX:
            line = f"{self._HEADING_PREFIX[tag]}{text}"
        elif tag == "li":
            line = f"- {text}"
        else:
            line = text
        if not self.lines or self.lines[-1] != line:
            self.lines.append(line)


def html_to_clean_markdown(html_text: str, title: str = "") -> str:
    """Convert HTML content into structured Markdown with zero HTML tags."""
    start, end = html_text.find("<main"), html_text.rfind("</main>")
    candidate = html_text[start:end] if start != -1 and end > start else html_text

    parser = _StructuredHTMLMarkdownParser()
    parser.feed(candidate)
    parser._flush_current()
    body = "\n\n".join(parser.lines).strip()

    if len(body) < 150 and candidate is not html_text:
        parser = _StructuredHTMLMarkdownParser()
        parser.feed(html_text)
        parser._flush_current()
        body = "\n\n".join(parser.lines).strip()

    body = strip_html_tags(body)
    clean_title = strip_html_tags(title)
    if clean_title and not body.startswith("# "):
        return f"# {clean_title}\n\n{body}".strip()
    return body


def json_psi_to_markdown(json_path: Path, title: str = "") -> str:
    """Convert a PSI investigation.json file into structured Markdown."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    clean = lambda val: strip_html_tags(re.sub(r"\s+", " ", str(val or "")))

    heading = clean(title) or (
        f"{data.get('accession', '')} {data.get('investigationAcronym', '')}: {clean(data.get('title'))}"
    ).strip()
    parts = [f"# {heading}"]

    meta_line = (
        f"Programme : {clean(data.get('flightProgram'))} ; "
        f"Matériel : {clean(data.get('experimentHardware'))} ; "
        f"Dates : {data.get('investigationStartDate', '')} à {data.get('investigationEndDate', '')} ; "
        f"DOI : {data.get('doi', '')}"
    )
    parts.append(meta_line)

    for key, label in (
        ("objective", "Objectifs"),
        ("hypothesis", "Hypothèse"),
        ("approach", "Approche"),
        ("description", "Description"),
        ("researchImpacts", "Retombées"),
    ):
        val = clean(data.get(key))
        if val:
            parts.append(f"## {label}\n\n{val}")

    pubs = [
        f"- {clean(p.get('authorList'))}. {clean(p.get('title'))}"
        for p in data.get("publications") or []
        if p.get("title")
    ]
    if pubs:
        parts.append("## Publications\n\n" + "\n".join(pubs))

    return "\n\n".join(parts).strip()
