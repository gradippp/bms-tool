"""Pulling the embedded Redux state out of a BookMyShow page."""

import json

from . import BmsParseError

_MARKER = "window.__INITIAL_STATE__"


def extract_initial_state(html: str) -> dict:
    """Return the JSON object assigned to window.__INITIAL_STATE__."""
    idx = html.find(_MARKER)
    if idx == -1:
        raise BmsParseError(
            "No __INITIAL_STATE__ found in the page "
            "(BookMyShow may have served a bot-check or changed its markup)."
        )
    start = html.find("{", idx)
    if start == -1:
        raise BmsParseError("__INITIAL_STATE__ found but no JSON object follows it.")

    depth = 0
    in_string = False
    escaped = False
    end = -1
    for i in range(start, len(html)):
        ch = html[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise BmsParseError("__INITIAL_STATE__ JSON object is truncated.")

    try:
        return json.loads(html[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BmsParseError(f"__INITIAL_STATE__ is not valid JSON: {exc}") from exc


def find_showtimes_payload(state: dict) -> dict:
    """Return the fetchPrimaryDynamic payload holding venues, showtimes and dates."""
    queries = (state.get("showtimesFunctionalApi") or {}).get("queries") or {}
    if not isinstance(queries, dict):
        raise BmsParseError("showtimesFunctionalApi.queries missing or malformed.")

    for name, query in queries.items():
        if not name.startswith("fetchPrimaryDynamic") or not isinstance(query, dict):
            continue
        data = query.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            return data["data"]

    static = queries.get("fetchStaticShowtimes") or {}
    version = (
        ((static.get("data") or {}).get("data") or {}).get("meta") or {}
    ).get("version")
    raise BmsParseError(
        "No fetchPrimaryDynamic payload in the page"
        + (f" (page schema version {version})" if version else "")
        + ". BookMyShow may have changed its response shape."
    )
