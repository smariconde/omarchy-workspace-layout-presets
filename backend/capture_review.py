"""User-reviewed launcher identity for browser-hosted Omarchy webapps."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Callable, Mapping

from .capture import CaptureError, HyprctlReader, SystemHyprctlReader, build_profile, profile_id_from_name
from .capture_store import consume_capture, issue_capture, read_capture
from .launchers import (
    desktop_entry_metadata,
    is_webapp_capable_browser_class,
    list_webapp_entries,
    resolve_desktop_id,
)
from .profile_store import ProfileAlreadyExistsError, ProfileError, create_profile, validate_profile


def _normalized_hint(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _suggested_desktop_id(title: str, webapps: list[dict[str, str]]) -> str | None:
    normalized_title = _normalized_hint(title)
    matches = [
        entry["desktopId"]
        for entry in webapps
        if len(_normalized_hint(entry["displayName"])) >= 3
        and _normalized_hint(entry["displayName"]) in normalized_title
    ]
    return matches[0] if len(matches) == 1 else None


def prepare_capture(
    name: str,
    *,
    reader: HyprctlReader | None = None,
    desktop_resolver: Callable[[str], str | None] = resolve_desktop_id,
    webapp_lister: Callable[[], list[dict[str, str]]] = list_webapp_entries,
    writer: Callable[[str, Mapping[str, Any]], Any] = create_profile,
    draft_issuer: Callable[[str, Mapping[str, Any], Mapping[str, list[str]]], str] = issue_capture,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Save immediately when unambiguous, otherwise return a safe review."""
    source = SystemHyprctlReader() if reader is None else reader
    active_workspace = source.read_json("activeworkspace")
    clients = source.read_json("clients")
    monitors = source.read_json("monitors")
    layout = source.read_json("getoption general:layout")
    profile_id = profile_id_from_name(name)
    profile = build_profile(
        name,
        active_workspace=active_workspace,
        clients=clients,
        monitors=monitors,
        layout=layout,
        desktop_resolver=desktop_resolver,
    )
    webapps = webapp_lister()
    workspace_id = active_workspace.get("id") if isinstance(active_workspace, Mapping) else None
    selected = [
        client for client in clients
        if isinstance(client, Mapping)
        and isinstance(client.get("workspace"), Mapping)
        and client["workspace"].get("id") == workspace_id
    ] if isinstance(clients, list) else []
    nodes = {node["id"]: node for node in [*profile["tiled"]["nodes"], *profile["floating"]]}
    reviews: list[dict[str, Any]] = []
    allowed: dict[str, list[str]] = {}
    if webapps:
        for index, client in enumerate(selected, start=1):
            window_class = client.get("class")
            if not isinstance(window_class, str) or not is_webapp_capable_browser_class(window_class):
                continue
            node_id = f"window-{index}"
            node = nodes[node_id]
            candidates: list[dict[str, str]] = []
            current_id = node["app"].get("desktopId")
            if isinstance(current_id, str):
                metadata = desktop_entry_metadata(current_id)
                label = metadata.get("displayName") if metadata else current_id
                candidates.append({"desktopId": current_id, "displayName": f"{label} · Browser"})
            candidates.extend(
                {"desktopId": entry["desktopId"], "displayName": f"{entry['displayName']} · Web app"}
                for entry in webapps
                if entry["desktopId"] != current_id
            )
            if not candidates:
                continue
            title = client.get("title", "")
            safe_title = title[:256] if isinstance(title, str) else ""
            suggested = _suggested_desktop_id(safe_title, webapps)
            node["app"]["desktopId"] = None
            node["launch"] = {"kind": "unresolved"}
            allowed[node_id] = [candidate["desktopId"] for candidate in candidates]
            reviews.append({
                "nodeId": node_id,
                "wmClass": window_class,
                "ordinal": node["app"]["ordinal"],
                "title": safe_title,
                "suggestedDesktopId": suggested,
                "candidates": candidates,
            })
    if not reviews:
        writer(profile_id, profile)
        return {"saved": True, "profileId": profile_id, "profile": profile, "review": []}, profile["warnings"]
    profile["warnings"].append({
        "code": "webapp_review",
        "message": "Browser-hosted windows need a launcher choice before this preset can be saved.",
    })
    validate_profile(profile)
    capture_id = draft_issuer(profile_id, profile, allowed)
    return {
        "saved": False,
        "captureId": capture_id,
        "profileId": profile_id,
        "review": reviews,
        "expiresInSeconds": 300,
    }, profile["warnings"]


def commit_capture(
    capture_id: str,
    assignments_json: str,
    *,
    draft_reader: Callable[[str], dict[str, Any]] = read_capture,
    draft_consumer: Callable[[str], None] = consume_capture,
    writer: Callable[[str, Mapping[str, Any]], Any] = create_profile,
) -> tuple[str, dict[str, Any]]:
    try:
        assignments = json.loads(assignments_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise CaptureError("webapp assignments must be a JSON object") from error
    record = draft_reader(capture_id)
    allowed = record["allowedAssignments"]
    if not isinstance(assignments, dict) or set(assignments) != set(allowed):
        raise CaptureError("choose a launcher or 'do not restore' for every reviewed window")
    profile = deepcopy(record["profile"])
    nodes = {node["id"]: node for node in [*profile["tiled"]["nodes"], *profile["floating"]]}
    profile["warnings"] = [warning for warning in profile["warnings"] if warning["code"] != "webapp_review"]
    for node_id, choice in assignments.items():
        node = nodes.get(node_id)
        if node is None:
            raise CaptureError("capture review refers to a missing window")
        if choice is None:
            profile["warnings"].append({
                "code": "unresolved_launcher",
                "message": f"No launcher was selected for {node['app']['wmClass']!r} instance {node['app']['ordinal']}.",
            })
            continue
        if not isinstance(choice, str) or choice not in allowed[node_id]:
            raise CaptureError("capture review contains a launcher that was not offered")
        node["app"]["desktopId"] = choice
        node["launch"] = {"kind": "desktop", "desktopId": choice}
    try:
        validate_profile(profile)
    except ProfileError as error:
        raise CaptureError(str(error)) from error
    try:
        writer(record["profileId"], profile)
    except ProfileAlreadyExistsError:
        raise
    except ProfileError as error:
        raise CaptureError(str(error)) from error
    draft_consumer(capture_id)
    return record["profileId"], profile
