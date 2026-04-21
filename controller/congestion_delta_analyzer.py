# controller/congestion_delta_analyzer.py

import argparse
import json
import os
from collections import defaultdict


KEY_METRICS = {
    "peak-buffer-occupancy-percent",
    "ecn-marked-pkts",
    "tail-drop-pkts",
    "red-drop-pkts",
}


def load_snapshot(path):
    with open(path) as f:
        return json.load(f)


def build_metric_map(snapshot):
    """
    Build map:
      (node, interface, queue) -> metrics
    """

    m = defaultdict(lambda: defaultdict(float))

    for node in snapshot.get("nodes", []):
        node_name = node.get("node")

        for sub in node.get("subscriptions", []):
            for rec in sub.get("normalized_records", []):
                labels = rec.get("labels") or {}

                if labels.get("group") != "qmon-queue":
                    continue

                metric = rec.get("metric")
                if metric not in KEY_METRICS:
                    continue

                interface = labels.get("interface")
                queue = labels.get("queue")

                key = (node_name, interface, queue)
                value = rec.get("value")

                if isinstance(value, (int, float)):
                    m[key][metric] = max(m[key][metric], value)

    return m


def compute_delta(pre, running, post):
    results = []

    all_keys = set(pre) | set(running) | set(post)

    for key in all_keys:

        node, interface, queue = key

        pre_m = pre.get(key, {})
        run_m = running.get(key, {})
        post_m = post.get(key, {})

        rec = {
            "node": node,
            "interface": interface,
            "queue": queue,
            "delta_running": {},
            "delta_post": {},
            "running_metrics": run_m,
        }

        for metric in KEY_METRICS:
            pre_v = pre_m.get(metric, 0)
            run_v = run_m.get(metric, 0)
            post_v = post_m.get(metric, 0)

            rec["delta_running"][metric] = run_v - pre_v
            rec["delta_post"][metric] = post_v - run_v

        results.append(rec)

    return results


def rank_hotspots(delta_records):

    ranked = []

    for r in delta_records:

        peak = r["running_metrics"].get("peak-buffer-occupancy-percent", 0)
        ecn = r["delta_running"].get("ecn-marked-pkts", 0)
        tail = r["delta_running"].get("tail-drop-pkts", 0)
        red = r["delta_running"].get("red-drop-pkts", 0)

        score = peak * 2 + tail * 5 + red * 4 + ecn * 0.000001

        ranked.append((score, r))

    ranked.sort(reverse=True, key=lambda x: x[0])

    return ranked


def write_report(out_path, ranked, top_n):

    txt_path = out_path.replace(".json", ".txt")

    with open(out_path, "w") as f:
        json.dump([r for _, r in ranked[:top_n]], f, indent=2)

    with open(txt_path, "w") as f:

        f.write("CONGESTION DELTA ANALYSIS\n\n")

        for i, (score, r) in enumerate(ranked[:top_n], 1):

            node = r["node"]
            interface = r["interface"]
            queue = r["queue"]

            peak = r["running_metrics"].get("peak-buffer-occupancy-percent", 0)
            ecn = r["delta_running"].get("ecn-marked-pkts", 0)
            tail = r["delta_running"].get("tail-drop-pkts", 0)

            f.write(
                f"{i}. node={node} interface={interface} queue={queue} score={score}\n"
            )
            f.write(
                f"   peak_buffer%={peak} new_ecn={ecn} new_tail_drop={tail}\n\n"
            )

    print("Delta JSON report :", out_path)
    print("Delta text report :", txt_path)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--pre", required=True)
    parser.add_argument("--running", required=True)
    parser.add_argument("--post", required=True)
    parser.add_argument("--top-n", type=int, default=10)

    args = parser.parse_args()

    pre = load_snapshot(args.pre)
    running = load_snapshot(args.running)
    post = load_snapshot(args.post)

    pre_map = build_metric_map(pre)
    run_map = build_metric_map(running)
    post_map = build_metric_map(post)

    delta_records = compute_delta(pre_map, run_map, post_map)

    ranked = rank_hotspots(delta_records)

    out_path = args.running.replace(".json", "_delta_analysis.json")

    write_report(out_path, ranked, args.top_n)


if __name__ == "__main__":
    main()
