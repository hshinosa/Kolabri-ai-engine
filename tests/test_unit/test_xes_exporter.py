from datetime import datetime
import xml.etree.ElementTree as ET

import pytest

from app.services.xes_exporter import XESExporter


def _local_name(tag):
    return tag.split("}", 1)[-1]


def _children(element, name):
    return [child for child in list(element) if _local_name(child.tag) == name]


def _attr_values(parent, element_name, key):
    values = []
    for child in list(parent):
        if _local_name(child.tag) == element_name and child.get("key") == key:
            values.append(child.get("value"))
    return values


@pytest.fixture
def exporter():
    return XESExporter()


def test_empty_events_produces_valid_xml_with_no_traces(exporter):
    xml_output = exporter.export([])
    root = ET.fromstring(xml_output)
    assert _local_name(root.tag) == "log"
    assert len(_children(root, "trace")) == 0


def test_single_event_creates_one_trace_with_one_event(exporter):
    events = [{"case_id": "case-1", "activity": "Study", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "alice"}]
    root = ET.fromstring(exporter.export(events))
    traces = _children(root, "trace")
    assert len(traces) == 1
    assert len(_children(traces[0], "event")) == 1


def test_multiple_events_same_case_id_grouped_in_one_trace(exporter):
    events = [
        {"case_id": "case-1", "activity": "A", "timestamp": datetime(2026, 1, 1, 10, 0), "resource": "alice"},
        {"case_id": "case-1", "activity": "B", "timestamp": datetime(2026, 1, 1, 11, 0), "resource": "alice"},
    ]
    root = ET.fromstring(exporter.export(events))
    traces = _children(root, "trace")
    assert len(traces) == 1
    assert len(_children(traces[0], "event")) == 2


def test_multiple_case_ids_create_separate_traces(exporter):
    events = [
        {"case_id": "case-1", "activity": "A", "timestamp": datetime(2026, 1, 1, 10, 0), "resource": "alice"},
        {"case_id": "case-2", "activity": "B", "timestamp": datetime(2026, 1, 1, 11, 0), "resource": "bob"},
    ]
    root = ET.fromstring(exporter.export(events))
    assert len(_children(root, "trace")) == 2


def test_events_are_sorted_by_timestamp_within_trace(exporter):
    events = [
        {"case_id": "case-1", "activity": "Second", "timestamp": datetime(2026, 1, 1, 11, 0), "resource": "alice"},
        {"case_id": "case-1", "activity": "First", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "alice"},
        {"case_id": "case-1", "activity": "Third", "timestamp": datetime(2026, 1, 1, 12, 0), "resource": "alice"},
    ]
    root = ET.fromstring(exporter.export(events))
    trace = _children(root, "trace")[0]
    names = [_attr_values(event, "string", "concept:name")[0] for event in _children(trace, "event")]
    assert names == ["First", "Second", "Third"]


def test_xml_contains_xes_version_2(exporter):
    root = ET.fromstring(exporter.export([]))
    assert root.get("xes.version") == "2.0"


def test_xml_contains_all_required_extensions(exporter):
    root = ET.fromstring(exporter.export([]))
    extensions = _children(root, "extension")
    names = [extension.get("name") for extension in extensions]
    assert names == ["Concept", "Time", "Organizational", "Lifecycle"]


def test_xml_contains_global_scope_elements(exporter):
    root = ET.fromstring(exporter.export([]))
    globals_ = _children(root, "global")
    scopes = [element.get("scope") for element in globals_]
    assert scopes == ["trace", "event"]


def test_event_attributes_include_string_float_and_boolean_types(exporter):
    events = [{
        "case_id": "case-1",
        "activity": "Study",
        "timestamp": datetime(2026, 1, 1, 9, 0),
        "resource": "alice",
        "attributes": {"topic": "AI", "score": 0.75, "passed": True},
    }]
    root = ET.fromstring(exporter.export(events))
    event = _children(_children(root, "trace")[0], "event")[0]
    assert _attr_values(event, "string", "topic") == ["AI"]
    assert _attr_values(event, "float", "score") == ["0.75"]
    assert _attr_values(event, "boolean", "passed") == ["true"]


def test_missing_case_id_defaults_to_unknown(exporter):
    events = [{"activity": "Study", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "alice"}]
    root = ET.fromstring(exporter.export(events))
    trace = _children(root, "trace")[0]
    assert _attr_values(trace, "string", "concept:name") == ["unknown"]


def test_missing_activity_defaults_to_unknown(exporter):
    events = [{"case_id": "case-1", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "alice"}]
    root = ET.fromstring(exporter.export(events))
    event = _children(_children(root, "trace")[0], "event")[0]
    assert _attr_values(event, "string", "concept:name") == ["Unknown"]


def test_output_is_parseable_xml(exporter):
    xml_output = exporter.export([{"case_id": "case-1", "activity": "Study", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "alice"}])
    root = ET.fromstring(xml_output)
    assert _local_name(root.tag) == "log"


def test_traces_are_sorted_by_case_id(exporter):
    events = [
        {"case_id": "case-b", "activity": "B", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "bob"},
        {"case_id": "case-a", "activity": "A", "timestamp": datetime(2026, 1, 1, 9, 0), "resource": "alice"},
    ]
    root = ET.fromstring(exporter.export(events))
    trace_names = [_attr_values(trace, "string", "concept:name")[0] for trace in _children(root, "trace")]
    assert trace_names == ["case-a", "case-b"]


def test_missing_resource_defaults_to_unknown(exporter):
    events = [{"case_id": "case-1", "activity": "Study", "timestamp": datetime(2026, 1, 1, 9, 0)}]
    root = ET.fromstring(exporter.export(events))
    event = _children(_children(root, "trace")[0], "event")[0]
    assert _attr_values(event, "string", "org:resource") == ["unknown"]


def test_missing_timestamp_uses_generated_iso_value(exporter):
    events = [{"case_id": "case-1", "activity": "Study", "resource": "alice"}]
    root = ET.fromstring(exporter.export(events))
    event = _children(_children(root, "trace")[0], "event")[0]
    timestamp_value = _attr_values(event, "date", "time:timestamp")[0]
    assert "T" in timestamp_value


def test_integer_attribute_is_emitted_as_float_tag(exporter):
    events = [{
        "case_id": "case-1",
        "activity": "Study",
        "timestamp": datetime(2026, 1, 1, 9, 0),
        "resource": "alice",
        "attributes": {"attempts": 3},
    }]
    root = ET.fromstring(exporter.export(events))
    event = _children(_children(root, "trace")[0], "event")[0]
    assert _attr_values(event, "float", "attempts") == ["3"]


def test_global_event_contains_default_lifecycle_transition(exporter):
    root = ET.fromstring(exporter.export([]))
    global_event = _children(root, "global")[1]
    assert _attr_values(global_event, "string", "lifecycle:transition") == ["complete"]
