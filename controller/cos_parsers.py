import re
from typing import Dict, Any, List


def _to_bool_enabled(value: str) -> bool:
    return str(value).strip().lower() in ("enable", "enabled", "true", "yes")


def _to_number(value: str):
    value = str(value).strip().replace(",", "")
    if not value:
        return 0
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        return value


def parse_forwarding_class(text: str) -> Dict[str, Any]:
    """
    Parse:
      Forwarding class                       ID      Queue  Policing priority  No-Loss   PFC priority
      mcast                                 8       8      normal             disabled  0
    """
    by_fc: Dict[str, Any] = {}
    by_queue: Dict[str, Any] = {}

    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("Forwarding class"):
            continue

        # Split by 2+ spaces to survive uneven column alignment.
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 6:
            continue

        fc_name = parts[0]
        try:
            fc_id = int(parts[1])
            queue = int(parts[2])
        except Exception:
            continue

        policing_priority = parts[3]
        no_loss = parts[4].strip().lower() == "enabled"
        pfc_priority = _to_number(parts[5])

        entry = {
            "forwarding_class": fc_name,
            "id": fc_id,
            "queue": queue,
            "policing_priority": policing_priority,
            "no_loss": no_loss,
            "pfc_priority": pfc_priority,
        }
        by_fc[fc_name] = entry
        by_queue[str(queue)] = entry

    return {"by_forwarding_class": by_fc, "by_queue": by_queue}


def parse_scheduler_map(text: str) -> Dict[str, Any]:
    """
    Parse blocks like:
      Scheduler: sc2, Forwarding class: rdma_storage, Index: 9
        Transmit rate: 40 percent...
        Explicit Congestion Notification: enable ...
        Drop profiles:
          Low ... dp_as
    """
    schedulers: Dict[str, Any] = {}
    current_fc = None

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        m = re.match(
            r"\s*Scheduler:\s*(\S+),\s*Forwarding class:\s*([A-Za-z0-9_-]+),\s*Index:\s*(\d+)",
            line,
        )
        if m:
            scheduler_name = m.group(1)
            fc_name = m.group(2)
            index = int(m.group(3))
            current_fc = fc_name
            schedulers[current_fc] = {
                "scheduler": scheduler_name,
                "index": index,
                "transmit_rate_percent": None,
                "buffer_size_percent": None,
                "priority": None,
                "ecn_enabled": False,
                "drop_profiles": [],
            }
            i += 1
            continue

        if current_fc:
            tx = re.search(r"Transmit rate:\s*([0-9.]+)\s*percent", line)
            if tx:
                schedulers[current_fc]["transmit_rate_percent"] = _to_number(tx.group(1))

            buf = re.search(r"Buffer size:\s*([0-9.]+)\s*percent", line)
            if buf:
                schedulers[current_fc]["buffer_size_percent"] = _to_number(buf.group(1))

            pri = re.search(r"Priority:\s*([A-Za-z-]+)", line)
            if pri:
                schedulers[current_fc]["priority"] = pri.group(1)

            ecn = re.search(r"Explicit Congestion Notification:\s*([A-Za-z]+)", line)
            if ecn:
                schedulers[current_fc]["ecn_enabled"] = _to_bool_enabled(ecn.group(1))

            dp = re.match(r"\s*(Low|Medium high|High)\s+any\s+\d+\s+([A-Za-z0-9_.-]+)", line)
            if dp:
                schedulers[current_fc]["drop_profiles"].append(
                    {"loss_priority": dp.group(1), "drop_profile": dp.group(2)}
                )

        i += 1

    return {"by_forwarding_class": schedulers}


def parse_cos_interface(text: str) -> Dict[str, Any]:
    result = {
        "physical_interface": None,
        "scheduler_map": None,
        "congestion_notification": None,
        "dynamic_threshold_profile": None,
        "drop_congestion_notification": None,
        "classifier": None,
    }

    for line in text.splitlines():
        line = line.rstrip()

        m = re.match(r"Physical interface:\s*([A-Za-z0-9:/.-]+),", line)
        if m:
            result["physical_interface"] = m.group(1)

        m = re.search(r"Scheduler map:\s*([A-Za-z0-9_.-]+)", line)
        if m:
            result["scheduler_map"] = m.group(1)

        m = re.search(r"Congestion-notification:\s*Enabled,\s*Name:\s*([A-Za-z0-9_.-]+)", line)
        if m:
            result["congestion_notification"] = m.group(1)

        m = re.search(r"Dynamic Threshold Profile:\s*([A-Za-z0-9_.-]+)", line)
        if m:
            result["dynamic_threshold_profile"] = m.group(1)

        m = re.search(r"Drop-Congestion-notification:\s*(Enabled|Disabled)", line)
        if m:
            result["drop_congestion_notification"] = m.group(1).lower() == "enabled"

        m = re.match(r"\s*Classifier\s+([A-Za-z0-9_.-]+)\s+dscp", line)
        if m:
            result["classifier"] = m.group(1)

    return result


def parse_interface_queue(text: str) -> Dict[str, Any]:
    """
    Parse queue statistics by queue number.
    """
    queues: Dict[str, Any] = {}
    current_queue = None
    current_fc = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        m = re.match(r"Queue:\s*(\d+),\s*Forwarding classes:\s*([A-Za-z0-9_-]+)", line)
        if m:
            current_queue = m.group(1)
            current_fc = m.group(2)
            queues[current_queue] = {
                "queue": int(current_queue),
                "forwarding_class": current_fc,
                "queued_packets": 0,
                "queued_bytes": 0,
                "transmitted_packets": 0,
                "transmitted_bytes": 0,
                "tail_dropped_packets": 0,
                "tail_dropped_bytes": 0,
                "red_dropped_packets": 0,
                "red_dropped_bytes": 0,
                "ecn_ce_packets": 0,
                "ecn_ce_bytes": 0,
            }
            continue

        if not current_queue:
            continue

        fields = {
            "Packets": None,
            "Bytes": None,
            "Tail-dropped packets": "tail_dropped_packets",
            "Tail-dropped bytes": "tail_dropped_bytes",
            "RED-dropped packets": "red_dropped_packets",
            "RED-dropped bytes": "red_dropped_bytes",
            "ECN-CE packets": "ecn_ce_packets",
            "ECN-CE bytes": "ecn_ce_bytes",
        }

        # Queued / Transmitted packet/byte counters
        if "Queued:" in line:
            section = "queued"
            continue
        if "Transmitted:" in line:
            section = "transmitted"
            continue

        m = re.match(r"\s*(Packets|Bytes)\s*:\s*([0-9,]+)", line)
        if m:
            label = m.group(1)
            val = _to_number(m.group(2))
            if "section" in locals():
                if section == "queued":
                    queues[current_queue][f"queued_{label.lower()}"] = val
                elif section == "transmitted":
                    queues[current_queue][f"transmitted_{label.lower()}"] = val
            continue

        for prefix, key in fields.items():
            if key and prefix in line:
                m2 = re.search(r":\s*([0-9,]+)", line)
                if m2:
                    queues[current_queue][key] = _to_number(m2.group(1))
                break

    return {"by_queue": queues}


def parse_all(raw_sections: Dict[str, str]) -> Dict[str, Any]:
    forwarding = parse_forwarding_class(raw_sections.get("forwarding_class", ""))
    sched = parse_scheduler_map(raw_sections.get("scheduler_map", ""))
    cos_ifd = parse_cos_interface(raw_sections.get("cos_interface", ""))
    qstats = parse_interface_queue(raw_sections.get("interface_queue", ""))

    return {
        "forwarding_class": forwarding,
        "scheduler_map": sched,
        "cos_interface": cos_ifd,
        "interface_queue": qstats,
    }
