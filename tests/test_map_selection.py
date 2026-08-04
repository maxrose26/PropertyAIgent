"""Tests for app.ui.map_selection (Sprint 3A, "Map Navigation and Site
UX", Part 8: "invalid or missing Site selection", "map selection opening
the correct Site")."""
from __future__ import annotations

from app.ui.map_selection import parse_site_id_param, resolve_selected_site_id


def test_resolve_selected_site_id_from_a_real_click():
    assert resolve_selected_site_id([{"site_id": 42, "other_field": "ignored"}]) == 42


def test_resolve_selected_site_id_with_no_selection():
    assert resolve_selected_site_id([]) is None


def test_resolve_selected_site_id_missing_site_id_key():
    assert resolve_selected_site_id([{"some_other_key": 1}]) is None


def test_resolve_selected_site_id_non_numeric_value():
    assert resolve_selected_site_id([{"site_id": "not-a-number"}]) is None


def test_resolve_selected_site_id_uses_the_first_object_only():
    # selection_mode="single-object" in the real app means there's only
    # ever one, but the resolver shouldn't assume that blindly.
    assert resolve_selected_site_id([{"site_id": 1}, {"site_id": 2}]) == 1


def test_resolve_selected_site_id_ignores_name_or_address_fields():
    # Part 3: navigation must use a stable identifier, never the Site name
    # or address - confirm the resolver has no code path that would ever
    # fall back to one.
    result = resolve_selected_site_id([{"Address": "1 Test Street", "site_id": 99}])
    assert result == 99


def test_parse_site_id_param_valid():
    assert parse_site_id_param("42") == 42


def test_parse_site_id_param_missing():
    assert parse_site_id_param(None) is None
    assert parse_site_id_param("") is None


def test_parse_site_id_param_invalid():
    assert parse_site_id_param("not-a-number") is None
    assert parse_site_id_param("42; DROP TABLE sites") is None
