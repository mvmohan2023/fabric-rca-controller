import argparse
import json
import os


def load(path):
    with open(path) as f:
        return json.load(f)


def output_paths(source_type, run_id):
    base = f"artifacts/{source_type}s/{run_id}/traffic"
    return (
        f"{base}/rocev2_hotspot_report.json",
        f"{base}/rocev2_hotspot_report.txt",
    )


def build_hotspot_report(deep):
    rx_rollup = deep.get("rx_rollup", [])

    worst_rx = rx_rollup[:5]

    result = {
        "worst_rx_ports": [],
        "top_problem_flows": [],
    }

    for rx in worst_rx:
        result["worst_rx_ports"].append(
            {
                "rx_port": rx.get("rx_port", "unknown"),
                "flow_count": rx.get("flow_count", rx.get("flows", 0)),
                "frame_delta": rx.get("sum_frames_delta", rx.get("frame_delta", 0)),
                "retransmissions": rx.get("sum_frames_retx", rx.get("retransmissions", 0)),
                "sequence_errors": rx.get("sum_frames_seqerror", rx.get("sequence_errors", 0)),
                "max_latency_ns": rx.get("max_latency_ns", 0),
            }
        )

        for flow in rx.get("worst_flows", []):
            result["top_problem_flows"].append(
                {
                    "flow": flow.get("flow_key", flow.get("flow", "unknown")),
                    "rx_port": flow.get("rx_port", "unknown"),
                    "tx_port": flow.get("tx_port", "unknown"),
                    "frames_delta": flow.get("frames_delta", flow.get("frame_delta", 0)),
                    "frames_retx": flow.get("frames_retx", flow.get("retransmissions", 0)),
                    "frames_seqerror": flow.get("frames_seqerror", flow.get("sequence_errors", 0)),
                    "max_latency_ns": flow.get("max_latency_ns", 0),
                }
            )

    result["top_problem_flows"] = sorted(
        result["top_problem_flows"],
        key=lambda x: (
            x["frames_seqerror"],
            x["frames_retx"],
            x["frames_delta"],
            x["max_latency_ns"],
        ),
        reverse=True,
    )[:15]

    return result


def render_text(report, run_id):

    lines = []
    lines.append("ROCEV2 HOTSPOT REPORT")
    lines.append(f"Run ID: {run_id}")
    lines.append("")

    lines.append("WORST RX PORTS")
    for r in report["worst_rx_ports"]:
        lines.append(
            f"{r['rx_port']} | flows={r.get('flow_count', r.get('flows', 0))} | "
            f"delta={r['frame_delta']} | "
            f"retx={r['retransmissions']} | "
            f"seqerr={r['sequence_errors']} | "
            f"max_latency_ns={r['max_latency_ns']}"
        )

    lines.append("")
    lines.append("TOP PROBLEM FLOWS")

    for f in report["top_problem_flows"]:
        lines.append(
            f"{f['flow']} | "
            f"delta={f['frames_delta']} | "
            f"retx={f['frames_retx']} | "
            f"seqerr={f['frames_seqerror']} | "
            f"max_latency_ns={f['max_latency_ns']}"
        )

    return "\n".join(lines)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", default="campaign")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--deep", required=True)

    args = parser.parse_args()

    deep = load(args.deep)

    report = build_hotspot_report(deep)

    json_path, txt_path = output_paths(args.source_type, args.run_id)

    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    with open(txt_path, "w") as f:
        f.write(render_text(report, args.run_id))

    print(f"RoCEv2 hotspot JSON report : {json_path}")
    print(f"RoCEv2 hotspot text report : {txt_path}")

    print("")
    print("ROCEV2 HOTSPOT SUMMARY")

    for r in report["worst_rx_ports"]:
        print(
            f"{r['rx_port']} "
            f"delta={r['frame_delta']} "
            f"retx={r['retransmissions']} "
            f"seqerr={r['sequence_errors']}"
        )


if __name__ == "__main__":
    main()
