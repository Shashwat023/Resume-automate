"""Validation cues emitted after a Next click, before submission."""

import re

from app.services.engine.tier0_harvest import _FIELD_LINE, _GROUP_ROLE, TARGET_ROLES
from app.services.engine.timeouts import with_timeout

_PAGE_ERROR = re.compile(
    r"\b(?:is required|required and must have a value|must (?:be|have|select)|"
    r"please (?:select|choose|enter|fill|complete|correct)|cannot be (?:blank|empty)|"
    r"invalid|errors? found)\b",
    re.I,
)


def find_page_validation_issues(formatted_tree: str) -> list[str]:
    last_label: str | None = None
    found: list[str] = []
    for line in formatted_tree.splitlines():
        match = _FIELD_LINE.match(line)
        if match:
            roles = {part.strip() for part in match.group("role").split(",")}
            label = (match.group("label") or "").strip().rstrip("*").strip()
            if (
                label
                and (roles & TARGET_ROLES or _GROUP_ROLE in roles)
                and not _PAGE_ERROR.search(label)
            ):
                last_label = label
        if _PAGE_ERROR.search(line) and last_label:
            found.append(last_label)
    return list(dict.fromkeys(found))


async def collect_invalid_labels_from_dom(page) -> list[str]:
    script = """(() => [...document.querySelectorAll('[aria-invalid="true"]')].slice(0,40).map(el => {
      const ids = (el.getAttribute('aria-labelledby') || '').split(/\\s+/);
      const labelled = ids.map(id => document.getElementById(id)?.innerText || '').join(' ').trim();
      const label = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText;
      return (el.getAttribute('aria-label') || labelled || label || el.getAttribute('placeholder') || '').trim().slice(0,80);
    }).filter(Boolean))()"""
    try:
        labels = await with_timeout(
            page.evaluate(script), what="evaluate(aria-invalid)"
        )
        return list(
            dict.fromkeys(
                str(label).strip()[:80] for label in labels if str(label).strip()
            )
        )[:40]
    except Exception:  # noqa: BLE001
        return []


async def blocking_field_labels(page, tree: str) -> list[str]:
    return list(
        dict.fromkeys(
            find_page_validation_issues(tree)
            + await collect_invalid_labels_from_dom(page)
        )
    )
