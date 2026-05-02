from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
from xml.dom import minidom

from app.core.logging import get_logger

logger = get_logger(__name__)


class XESExporter:
    XES_VERSION = "2.0"
    XES_NAMESPACE = "http://www.xes-standard.org/"

    def export(self, events: List[Dict[str, Any]]) -> str:
        log = ET.Element("log")
        log.set("xes.version", self.XES_VERSION)
        log.set("xes.features", "")
        log.set("xmlns", self.XES_NAMESPACE)

        self._add_extensions(log)
        self._add_globals(log)

        traces = defaultdict(list)
        for event in events:
            traces[event.get("case_id", "unknown")].append(event)

        for case_id, trace_events in sorted(traces.items()):
            trace_elem = ET.SubElement(log, "trace")
            self._add_string_attr(trace_elem, "concept:name", case_id)
            for event_data in sorted(trace_events, key=lambda e: e.get("timestamp", datetime.min)):
                event_elem = ET.SubElement(trace_elem, "event")
                self._add_event_attributes(event_elem, event_data)

        xml_str = ET.tostring(log, encoding="unicode", xml_declaration=True)
        try:
            return minidom.parseString(xml_str).toprettyxml(indent="  ")
        except Exception:
            return xml_str

    def _add_extensions(self, log: ET.Element) -> None:
        for name, prefix, uri in [
            ("Concept", "concept", "http://www.xes-standard.org/concept.xesext"),
            ("Time", "time", "http://www.xes-standard.org/time.xesext"),
            ("Organizational", "org", "http://www.xes-standard.org/org.xesext"),
            ("Lifecycle", "lifecycle", "http://www.xes-standard.org/lifecycle.xesext"),
        ]:
            ext = ET.SubElement(log, "extension")
            ext.set("name", name)
            ext.set("prefix", prefix)
            ext.set("uri", uri)

    def _add_globals(self, log: ET.Element) -> None:
        global_trace = ET.SubElement(log, "global")
        global_trace.set("scope", "trace")
        self._add_string_attr(global_trace, "concept:name", "UNKNOWN")

        global_event = ET.SubElement(log, "global")
        global_event.set("scope", "event")
        self._add_string_attr(global_event, "concept:name", "UNKNOWN")
        self._add_date_attr(global_event, "time:timestamp", datetime(1970, 1, 1))
        self._add_string_attr(global_event, "lifecycle:transition", "complete")

    def _add_event_attributes(self, event_elem: ET.Element, event_data: Dict[str, Any]) -> None:
        self._add_string_attr(event_elem, "concept:name", event_data.get("activity", "Unknown"))
        self._add_date_attr(event_elem, "time:timestamp", event_data.get("timestamp", datetime.now()))
        self._add_string_attr(event_elem, "org:resource", event_data.get("resource", "unknown"))
        self._add_string_attr(event_elem, "lifecycle:transition", "complete")

        for key, value in event_data.get("attributes", {}).items():
            if isinstance(value, bool):
                self._add_boolean_attr(event_elem, key, value)
            elif isinstance(value, (int, float)):
                self._add_float_attr(event_elem, key, value)
            elif isinstance(value, str):
                self._add_string_attr(event_elem, key, value)

    def _add_string_attr(self, parent: ET.Element, key: str, value: str) -> None:
        attr = ET.SubElement(parent, "string")
        attr.set("key", key)
        attr.set("value", str(value))

    def _add_date_attr(self, parent: ET.Element, key: str, value) -> None:
        attr = ET.SubElement(parent, "date")
        attr.set("key", key)
        if isinstance(value, str):
            attr.set("value", value)
        else:
            attr.set("value", value.isoformat())

    def _add_float_attr(self, parent: ET.Element, key: str, value: float) -> None:
        attr = ET.SubElement(parent, "float")
        attr.set("key", key)
        attr.set("value", str(value))

    def _add_boolean_attr(self, parent: ET.Element, key: str, value: bool) -> None:
        attr = ET.SubElement(parent, "boolean")
        attr.set("key", key)
        attr.set("value", str(value).lower())


_xes_exporter: Optional[XESExporter] = None


def get_xes_exporter() -> XESExporter:
    global _xes_exporter
    if _xes_exporter is None:
        _xes_exporter = XESExporter()
    return _xes_exporter
