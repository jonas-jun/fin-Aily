from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_whitespace(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def trim_text(text: str, max_chars: int = 60000) -> str:
    text = compact_whitespace(text)
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.7)].rstrip()
    tail = text[-int(max_chars * 0.3) :].lstrip()
    return f"{head}\n\n[...중략...]\n\n{tail}"


def render_template(template: str, variables: dict[str, Any]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def format_number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:,.{digits}f}"


def format_money_m(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1000:
        return f"{sign}${number / 1000:,.1f}B"
    return f"{sign}${number:,.0f}M"


def format_money_b_from_raw(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"${number / 1_000_000_000:,.1f}B"


def format_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.1f}%"


def format_x(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f}x"
    except (TypeError, ValueError):
        return str(value)


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "N/A"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_markdown_cell(row.get(key, "N/A")) for key, _ in columns) + " |")
    return "\n".join([header, sep, *body])


def _markdown_cell(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, list):
        return "<br>".join(_markdown_cell(item) for item in value) if value else "N/A"
    text = str(value).replace("\n", "<br>").replace("|", "\\|")
    return text if text.strip() else "N/A"


def bullet_list(items: Iterable[Any]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return "- N/A"
    return "\n".join(f"- {item}" for item in values)


def simple_summary(text: str, max_items: int = 8) -> list[str]:
    clean = compact_whitespace(text)
    sentences = re.split(r"(?<=[.!?。])\s+", clean)
    selected = [sentence.strip() for sentence in sentences if len(sentence.strip()) > 40]
    return selected[:max_items] or ([clean[:500]] if clean else ["원문 텍스트가 비어 있음"])
