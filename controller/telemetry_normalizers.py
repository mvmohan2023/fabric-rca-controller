# controller/telemetry_normalizers.py

import re
from typing import Any, Dict, List, Optional, Tuple


OPTICS_PATH_PREFIX = "/junos/system/linecard/optics/"
QMON_PATH_PREFIX = "/junos/system/linecard/qmon-sw"
INTERFACE_STATE_PREFIXES = (
    "/state/interfaces/interface[",
    "/interfaces/interface[",
)

OPTICS_METRIC_ALIASES = {
    "snmp_if_index": "snmp-if-index",
    "optics/optics_type": "optics-type",
    "optics/module_temp": "module-temperature-c",
    "optics/module_temp_high_alarm_threshold": "module-temperature-high-alarm-threshold-c",
    "optics/module_temp_low_alarm_threshold": "module-temperature-low-alarm-threshold-c",
    "optics/module_temp_high_warning_threshold": "module-temperature-high-warning-threshold-c",
    "optics/module_temp_low_warning_threshold": "module-temperature-low-warning-threshold-c",
    "optics/module_temp_high_alarm": "module-temperature-high-alarm",
    "optics/module_temp_low_alarm": "module-temperature-low-alarm",
    "optics/module_temp_high_warning": "module-temperature-high-warning",
    "optics/module_temp_low_warning": "module-temperature-low-warning",
    "optics/laser_output_power_high_alarm_threshold_dbm": "laser-output-power-high-alarm-threshold-dbm",
    "optics/laser_output_power_low_alarm_threshold_dbm": "laser-output-power-low-alarm-threshold-dbm",
    "optics/laser_output_power_high_warning_threshold_dbm": "laser-output-power-high-warning-threshold-dbm",
    "optics/laser_output_power_low_warning_threshold_dbm": "laser-output-power-low-warning-threshold-dbm",
    "optics/laser_rx_power_high_alarm_threshold_dbm": "laser-rx-power-high-alarm-threshold-dbm",
    "optics/laser_rx_power_low_alarm_threshold_dbm": "laser-rx-power-low-alarm-threshold-dbm",
    "optics/laser_rx_power_high_warning_threshold_dbm": "laser-rx-power-high-warning-threshold-dbm",
    "optics/laser_rx_power_low_warning_threshold_dbm": "laser-rx-power-low-warning-threshold-dbm",
    "optics/laser_bias_current_high_alarm_threshold": "laser-bias-current-high-alarm-threshold",
    "optics/laser_bias_current_low_alarm_threshold": "laser-bias-current-low-alarm-threshold",
    "optics/laser_bias_current_high_warning_threshold": "laser-bias-current-high-warning-threshold",
    "optics/laser_bias_current_low_warning_threshold": "laser-bias-current-low-warning-threshold",
    "optics/wavelength_channel": "wavelength-channel",
    "optics/wavelength_setpoint": "wavelength-setpoint",
    "optics/tx_dither": "tx-dither",
    "optics/frequency_error": "frequency-error",
    "optics/wavelength_error": "wavelength-error",
    "optics/tec_fault": "tec-fault",
    "optics/w_unlocked_alarm": "w-unlocked-alarm",
    "optics/tx_tune_alarm": "tx-tune-alarm",

    # lane metrics
    "optics/lanediags/lane/lane_number": "lane-number",
    "optics/lanediags/lane/lane_laser_temperature": "lane-laser-temperature-c",
    "optics/lanediags/lane/lane_laser_output_power_dbm": "lane-laser-output-power-dbm",
    "optics/lanediags/lane/lane_laser_receiver_power_dbm": "lane-laser-receiver-power-dbm",
    "optics/lanediags/lane/lane_laser_bias_current": "lane-laser-bias-current",
    "optics/lanediags/lane/lane_laser_output_power_high_alarm": "lane-laser-output-power-high-alarm",
    "optics/lanediags/lane/lane_laser_output_power_low_alarm": "lane-laser-output-power-low-alarm",
    "optics/lanediags/lane/lane_laser_output_power_high_warning": "lane-laser-output-power-high-warning",
    "optics/lanediags/lane/lane_laser_output_power_low_warning": "lane-laser-output-power-low-warning",
    "optics/lanediags/lane/lane_laser_receiver_power_high_alarm": "lane-laser-receiver-power-high-alarm",
    "optics/lanediags/lane/lane_laser_receiver_power_low_alarm": "lane-laser-receiver-power-low-alarm",
    "optics/lanediags/lane/lane_laser_receiver_power_high_warning": "lane-laser-receiver-power-high-warning",
    "optics/lanediags/lane/lane_laser_receiver_power_low_warning": "lane-laser-receiver-power-low-warning",
    "optics/lanediags/lane/lane_laser_bias_current_high_alarm": "lane-laser-bias-current-high-alarm",
    "optics/lanediags/lane/lane_laser_bias_current_low_alarm": "lane-laser-bias-current-low-alarm",
    "optics/lanediags/lane/lane_laser_bias_current_high_warning": "lane-laser-bias-current-high-warning",
    "optics/lanediags/lane/lane_laser_bias_current_low_warning": "lane-laser-bias-current-low-warning",
    "optics/lanediags/lane/lane_tx_loss_of_signal_alarm": "lane-tx-loss-of-signal-alarm",
    "optics/lanediags/lane/lane_rx_loss_of_signal_alarm": "lane-rx-loss-of-signal-alarm",
    "optics/lanediags/lane/lane_tx_laser_disabled_alarm": "lane-tx-laser-disabled-alarm",
    "optics/lanediags/lane/media_fec_corr_bits": "media-fec-corr-bits",
    "optics/lanediags/lane/media_fec_uncorr_blocks": "media-fec-uncorr-blocks",
}


QMON_METRIC_ALIASES = {
    "txPkts": "tx-pkts",
    "txBytes": "tx-bytes",
    "tailDropPkts": "tail-drop-pkts",
    "tailDropBytes": "tail-drop-bytes",
    "peakBufferOccupancy": "peak-buffer-occupancy",
    "peakBufferOccupancyPercent": "peak-buffer-occupancy-percent",
    "redDropPkts": "red-drop-pkts",
    "ecnMarkedPkts": "ecn-marked-pkts",
    "ecnMarkedBytes": "ecn-marked-bytes",
    "index": "index",
}


DEFAULT_ANALYZER_THRESHOLDS = {
    "module-temperature-c": {"max": 85.0},
    "lane-laser-temperature-c": {"max": 90.0},
    "laser-output-power-low-alarm-threshold-dbm": {},
    "laser-rx-power-low-alarm-threshold-dbm": {},
    "lane-laser-output-power-dbm": {"min": -30.0, "max": 15.0},
    "lane-laser-receiver-power-dbm": {"min": -30.0, "max": 15.0},
    "lane-laser-bias-current": {"min": 0.0, "max": 150.0},

    # interface / congestion related
    "pre-fec-ber": {"max": 1e-6},
    "in-pcs-errored-seconds": {},
    "fec-corrected-words": {},
    "fec-uncorrectable-words": {},
    "in-resource-drops": {},
    "out-ecn-ce-marked-pkts": {},

    # qmon
    "tx-pkts": {},
    "tx-bytes": {},
    "tail-drop-pkts": {},
    "tail-drop-bytes": {},
    "peak-buffer-occupancy": {},
    "peak-buffer-occupancy-percent": {"max": 100.0},
    "red-drop-pkts": {},
    "ecn-marked-pkts": {},
    "ecn-marked-bytes": {},
}


def is_optics_path(sub_path: str) -> bool:
    return sub_path.startswith(OPTICS_PATH_PREFIX)


def is_qmon_path(sub_path: str) -> bool:
    return sub_path.startswith(QMON_PATH_PREFIX)


def is_interface_state_path(sub_path: str) -> bool:
    return any(sub_path.startswith(prefix) for prefix in INTERFACE_STATE_PREFIXES)

def safe_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.upper() == "NA":
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def normalize_scalar(value: Any) -> Tuple[Any, str]:
    """
    Returns: (normalized_value, value_type)
    value_type in {counter, gauge, state, string, unknown}
    """
    if isinstance(value, bool):
        return value, "state"

    if isinstance(value, int):
        return value, "counter"

    if isinstance(value, float):
        return value, "gauge"

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.upper() == "NA":
            return None, "string"

        num = safe_float(stripped)
        if num is not None:
            if "." in stripped:
                return num, "gauge"
            return int(num), "counter"

        return stripped, "string"

    return value, "unknown"


def classify_metric_type(metric_name: str, value_type: str) -> str:
    if metric_name.endswith("-alarm") or metric_name.endswith("-warning"):
        return "state"
    if "temperature" in metric_name:
        return "gauge"
    if "power" in metric_name:
        return "gauge"
    if "bias-current" in metric_name:
        return "gauge"
    if "ber" in metric_name:
        return "gauge"
    if "rate" in metric_name:
        return "gauge"
    if "percent" in metric_name:
        return "gauge"
    if "corr-bits" in metric_name or "uncorr-blocks" in metric_name:
        return "counter"
    if "pkts" in metric_name or "bytes" in metric_name or "words" in metric_name or "occupancy" in metric_name:
        return "counter" if "percent" not in metric_name else "gauge"
    if value_type in ("counter", "gauge", "state"):
        return value_type
    return "string"


def extract_interface_from_prefix(prefix: str) -> Optional[str]:
    """
    Examples:
      interfaces/interface[name=et-0/0/0:0]
      state/interfaces/interface[name=et-0/0/4:1]
      cos/interfaces/interface[name=et-0/0/34]
    """
    if not prefix:
        return None
    match = re.search(r"interface\[name=([^\]]+)\]", prefix)
    if match:
        value = match.group(1).strip()
        return value.strip("'\"")
    return None


def extract_lane_from_update_path(update_path: str) -> Optional[str]:
    if not update_path:
        return None
    match = re.search(r"lane\[lane_number=([^\]]+)\]", update_path)
    if match:
        return match.group(1)
    return None


def extract_bin_from_prefix(prefix: str) -> Optional[int]:
    if not prefix:
        return None
    match = re.search(r"symbol\[bin=([^\]]+)\]", prefix)
    if match:
        try:
            return int(str(match.group(1)).strip("'\""))
        except ValueError:
            return None
    return None


def extract_priority_from_prefix(prefix: str) -> Optional[int]:
    if not prefix:
        return None
    match = re.search(r"pfc\[priority=([^\]]+)\]", prefix)
    if match:
        try:
            return int(str(match.group(1)).strip("'\""))
        except ValueError:
            return None
    return None


def extract_queue_from_prefix(prefix: str) -> Optional[int]:
    if not prefix:
        return None
    match = re.search(r"queue\[queue=([^\]]+)\]", prefix)
    if match:
        try:
            return int(str(match.group(1)).strip("'\""))
        except ValueError:
            return None
    return None


def extract_pg_from_prefix(prefix: str) -> Optional[int]:
    if not prefix:
        return None
    match = re.search(r"priority-group\[pg=([^\]]+)\]", prefix)
    if match:
        try:
            return int(str(match.group(1)).strip("'\""))
        except ValueError:
            return None
    return None


def value_from_update(update: Dict[str, Any]) -> Any:
    values = update.get("values") or {}
    if not isinstance(values, dict) or not values:
        return None

    first_key = next(iter(values.keys()))
    return values.get(first_key)


def canonical_metric_name(update_path: str, value_key: Optional[str] = None) -> str:
    if value_key and value_key in OPTICS_METRIC_ALIASES:
        return OPTICS_METRIC_ALIASES[value_key]
    if update_path:
        path_no_index = re.sub(r"\[.*?\]", "", update_path)
        if path_no_index in OPTICS_METRIC_ALIASES:
            return OPTICS_METRIC_ALIASES[path_no_index]
        leaf = path_no_index.split("/")[-1]
        return leaf.replace("_", "-")
    return "unknown-metric"


def canonical_qmon_metric_name(update_path: str, value_key: Optional[str] = None) -> str:
    if value_key and value_key in QMON_METRIC_ALIASES:
        return QMON_METRIC_ALIASES[value_key]
    if update_path and update_path in QMON_METRIC_ALIASES:
        return QMON_METRIC_ALIASES[update_path]
    if update_path:
        return update_path.replace("_", "-")
    return "unknown-metric"


def build_record(
    *,
    node: str,
    sub_path: str,
    entity: str,
    metric_name: str,
    normalized_value: Any,
    raw_value: Any,
    metric_type: str,
    prefix: str,
    raw_update_path: str,
    labels: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "node": node,
        "path": sub_path,
        "entity": entity,
        "metric": metric_name,
        "value": normalized_value,
        "raw_value": raw_value,
        "labels": labels or {},
        "type": metric_type,
        "source_prefix": prefix,
        "update_path": raw_update_path,
    }

    thresholds = DEFAULT_ANALYZER_THRESHOLDS.get(metric_name)
    if thresholds is not None:
        record["thresholds"] = thresholds

    return record


def normalize_qmon_payload(payload: Dict[str, Any], node: str, sub_path: str) -> List[Dict[str, Any]]:
    """
    Handles payloads like:
      cos/interfaces/interface[name=et-0/0/34]
      cos/interfaces/interface[name=et-0/0/34]/queues/queue[queue=0]
      cos/interfaces/interface[name=et-0/0/34]/priority-groups/priority-group[pg=0]
    """
    records: List[Dict[str, Any]] = []

    prefix = str(payload.get("prefix", "")).strip()
    updates = payload.get("updates") or []
    interface_name = extract_interface_from_prefix(prefix)
    queue_id = extract_queue_from_prefix(prefix)
    pg_id = extract_pg_from_prefix(prefix)

    group = "qmon-interface"
    if "/queues/queue[" in prefix:
        group = "qmon-queue"
    elif "/priority-groups/priority-group[" in prefix:
        group = "qmon-priority-group"

    entity_base = interface_name or node
    entity = entity_base
    if queue_id is not None:
        entity = f"{entity_base}:queue{queue_id}"
    elif pg_id is not None:
        entity = f"{entity_base}:pg{pg_id}"

    for update in updates:
        raw_update_path = update.get("Path", "")
        values = update.get("values") or {}
        value_key = next(iter(values.keys())) if values else None
        raw_value = value_from_update(update)
        normalized_value, value_type = normalize_scalar(raw_value)

        metric_name = canonical_qmon_metric_name(raw_update_path, value_key)
        metric_type = classify_metric_type(metric_name, value_type)

        labels: Dict[str, Any] = {
            "group": group,
        }
        if interface_name:
            labels["interface"] = interface_name
        if queue_id is not None:
            labels["queue"] = queue_id
        if pg_id is not None:
            labels["pg"] = pg_id

        if group != "qmon-interface":
            labels["subcomponent"] = group

        records.append(
            build_record(
                node=node,
                sub_path=sub_path,
                entity=entity,
                metric_name=metric_name,
                normalized_value=normalized_value,
                raw_value=raw_value,
                metric_type=metric_type,
                prefix=prefix,
                raw_update_path=raw_update_path,
                labels=labels,
            )
        )

    return records


def normalize_optics_payload(payload: Dict[str, Any], node: str, sub_path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    prefix = payload.get("prefix", "")
    interface_name = extract_interface_from_prefix(prefix)
    updates = payload.get("updates") or []

    for update in updates:
        raw_update_path = update.get("Path", "")
        lane = extract_lane_from_update_path(raw_update_path)

        values = update.get("values") or {}
        value_key = next(iter(values.keys())) if values else None
        raw_value = value_from_update(update)
        normalized_value, value_type = normalize_scalar(raw_value)

        metric_name = canonical_metric_name(raw_update_path, value_key)
        metric_type = classify_metric_type(metric_name, value_type)

        labels: Dict[str, Any] = {}
        if interface_name:
            labels["interface"] = interface_name
        if lane is not None:
            labels["lane"] = lane

        entity = interface_name or node
        if lane is not None:
            entity = f"{entity}:lane{lane}"

        records.append(
            build_record(
                node=node,
                sub_path=sub_path,
                entity=entity,
                metric_name=metric_name,
                normalized_value=normalized_value,
                raw_value=raw_value,
                metric_type=metric_type,
                prefix=prefix,
                raw_update_path=raw_update_path,
                labels=labels,
            )
        )

    return records


def normalize_interface_state_payload(payload: Dict[str, Any], node: str, sub_path: str) -> List[Dict[str, Any]]:
    """
    Specialized normalizer for:
      /state/interfaces/interface[name=<port>]/

    Preserves useful labels for:
      - ethernet summary
      - fec symbol bins
      - ipv4/ipv6 counters
      - interface error counters
      - pfc per-priority counters
    """
    records: List[Dict[str, Any]] = []

    prefix = str(payload.get("prefix", "")).strip()
    updates = payload.get("updates") or []
    interface_name = extract_interface_from_prefix(prefix)
    entity_base = interface_name or node

    bin_id = extract_bin_from_prefix(prefix)
    priority = extract_priority_from_prefix(prefix)

    group = "interface"
    if prefix.endswith("/ethernet"):
        group = "ethernet"
    elif "/ethernet/fec/errors/symbol[" in prefix:
        group = "fec-symbol"
    elif prefix.endswith("/counters/ipv4"):
        group = "ipv4"
    elif prefix.endswith("/counters/ipv6"):
        group = "ipv6"
    elif prefix.endswith("/counters/errors"):
        group = "errors"
    elif "/counters/pfc[" in prefix:
        group = "pfc"
    elif "/units/unit[" in prefix:
        group = "unit"

    for update in updates:
        raw_update_path = update.get("Path", "")
        raw_value = value_from_update(update)
        normalized_value, value_type = normalize_scalar(raw_value)

        metric_name = raw_update_path.split("/")[-1].replace("_", "-") if raw_update_path else "unknown-metric"
        metric_type = classify_metric_type(metric_name, value_type)

        labels: Dict[str, Any] = {
            "group": group,
        }
        if interface_name:
            labels["interface"] = interface_name
        if bin_id is not None:
            labels["bin"] = bin_id
        if priority is not None:
            labels["priority"] = priority

        entity = entity_base
        if bin_id is not None:
            entity = f"{entity_base}:fec-bin{bin_id}"
        elif priority is not None:
            entity = f"{entity_base}:pfc-priority{priority}"

        if group != "interface":
            labels["subcomponent"] = group

        records.append(
            build_record(
                node=node,
                sub_path=sub_path,
                entity=entity,
                metric_name=metric_name,
                normalized_value=normalized_value,
                raw_value=raw_value,
                metric_type=metric_type,
                prefix=prefix,
                raw_update_path=raw_update_path,
                labels=labels,
            )
        )

    return records


def normalize_generic_payload(payload: Dict[str, Any], node: str, sub_path: str) -> List[Dict[str, Any]]:
    """
    Generic fallback normalizer for non-optics paths.
    """
    records: List[Dict[str, Any]] = []
    prefix = payload.get("prefix", "")
    updates = payload.get("updates") or []
    interface_name = extract_interface_from_prefix(prefix)

    for update in updates:
        raw_update_path = update.get("Path", "")
        raw_value = value_from_update(update)
        normalized_value, value_type = normalize_scalar(raw_value)

        metric_name = raw_update_path.split("/")[-1].replace("_", "-") if raw_update_path else "unknown-metric"
        metric_type = classify_metric_type(metric_name, value_type)

        labels: Dict[str, Any] = {}
        if interface_name:
            labels["interface"] = interface_name

        records.append(
            build_record(
                node=node,
                sub_path=sub_path,
                entity=interface_name or node,
                metric_name=metric_name,
                normalized_value=normalized_value,
                raw_value=raw_value,
                metric_type=metric_type,
                prefix=prefix,
                raw_update_path=raw_update_path,
                labels=labels,
            )
        )

    return records


def normalize_telemetry_payload(payload: Dict[str, Any], node: str, sub_path: str) -> List[Dict[str, Any]]:
    if is_optics_path(sub_path):
        return normalize_optics_payload(payload=payload, node=node, sub_path=sub_path)

    if is_qmon_path(sub_path):
        return normalize_qmon_payload(payload=payload, node=node, sub_path=sub_path)

    if is_interface_state_path(sub_path):
        return normalize_interface_state_payload(payload=payload, node=node, sub_path=sub_path)

    return normalize_generic_payload(payload=payload, node=node, sub_path=sub_path)
