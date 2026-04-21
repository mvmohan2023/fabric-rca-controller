import argparse
import json
from pathlib import Path
from datetime import datetime


def load_json(path):
    with open(path) as f:
        return json.load(f)


def compute_delta(pre, post, key):
    return post.get(key, 0) - pre.get(key, 0)


def analyze(pre_report, post_report):

    pre_summary = pre_report.get("summary", {})
    post_summary = post_report.get("summary", {})

    results = {}

    # -------------------------
    # Physical links
    # -------------------------

    pre_links = pre_summary.get("physical_links", {})
    post_links = post_summary.get("physical_links", {})

    results["physical_links"] = {
        "pre": pre_links,
        "post": post_links,
        "delta_present": compute_delta(pre_links, post_links, "present"),
        "delta_missing": compute_delta(pre_links, post_links, "missing"),
    }

    # -------------------------
    # IP consistency
    # -------------------------

    pre_ip = pre_summary.get("ip_consistency", {})
    post_ip = post_summary.get("ip_consistency", {})

    results["ip_consistency"] = {
        "pre": pre_ip,
        "post": post_ip,
        "delta_ipv4_mismatch": compute_delta(pre_ip, post_ip, "ipv4_mismatch"),
        "delta_ipv6_mismatch": compute_delta(pre_ip, post_ip, "ipv6_mismatch"),
    }

    # -------------------------
    # BGP
    # -------------------------

    pre_bgp = pre_summary.get("bgp", {})
    post_bgp = post_summary.get("bgp", {})

    results["bgp"] = {
        "pre": pre_bgp,
        "post": post_bgp,
        "delta_up": compute_delta(pre_bgp, post_bgp, "up"),
        "delta_down": compute_delta(pre_bgp, post_bgp, "down"),
        "delta_missing": compute_delta(pre_bgp, post_bgp, "missing"),
    }

    # -------------------------
    # Fabric readiness
    # -------------------------

    results["fabric_readiness"] = {
        "pre_ready": pre_report.get("ready_for_stress"),
        "post_ready": post_report.get("ready_for_stress"),
    }

    # -------------------------
    # Verdict
    # -------------------------

    drift_detected = False

    if results["physical_links"]["delta_missing"] != 0:
        drift_detected = True

    if results["ip_consistency"]["delta_ipv4_mismatch"] != 0:
        drift_detected = True

    if results["ip_consistency"]["delta_ipv6_mismatch"] != 0:
        drift_detected = True

    if results["bgp"]["delta_up"] < 0:
        drift_detected = True

    if results["fabric_readiness"]["post_ready"] is False:
        drift_detected = True

    results["drift_detected"] = drift_detected

    return results


def write_text_report(diff, outfile):

    with open(outfile, "w") as f:

        f.write("STRESS DIFF REPORT\n")
        f.write("==================\n\n")

        f.write("PHYSICAL LINKS\n")
        f.write("--------------\n")
        f.write(f"Pre  present : {diff['physical_links']['pre'].get('present')}\n")
        f.write(f"Post present : {diff['physical_links']['post'].get('present')}\n")
        f.write(f"Delta        : {diff['physical_links']['delta_present']}\n\n")

        f.write("IP CONSISTENCY\n")
        f.write("--------------\n")
        f.write(f"IPv4 mismatch delta : {diff['ip_consistency']['delta_ipv4_mismatch']}\n")
        f.write(f"IPv6 mismatch delta : {diff['ip_consistency']['delta_ipv6_mismatch']}\n\n")

        f.write("BGP\n")
        f.write("---\n")
        f.write(f"Pre  up : {diff['bgp']['pre'].get('up')}\n")
        f.write(f"Post up : {diff['bgp']['post'].get('up')}\n")
        f.write(f"Delta   : {diff['bgp']['delta_up']}\n\n")

        f.write("FABRIC READINESS\n")
        f.write("----------------\n")
        f.write(f"Pre ready  : {diff['fabric_readiness']['pre_ready']}\n")
        f.write(f"Post ready : {diff['fabric_readiness']['post_ready']}\n\n")

        f.write("VERDICT\n")
        f.write("-------\n")

        if diff["drift_detected"]:
            f.write("Fabric drift detected after stress\n")
        else:
            f.write("No material drift detected\n")


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)

    args = parser.parse_args()

    base = Path("/root/fabric-controller/artifacts/orchestrator")
    run_dir = base / args.run_id

    pre_file = run_dir / "pre/precheck/stress_precheck_report.json"
    post_file = run_dir / "post/precheck/stress_precheck_report.json"

    pre_report = load_json(pre_file)
    post_report = load_json(post_file)

    diff = analyze(pre_report, post_report)

    diff["run_id"] = args.run_id
    diff["timestamp"] = datetime.utcnow().isoformat()

    json_out = run_dir / "stress_diff_report.json"
    txt_out = run_dir / "stress_diff_report.txt"

    with open(json_out, "w") as f:
        json.dump(diff, f, indent=2)

    write_text_report(diff, txt_out)

    print("\nDiff JSON report :", json_out)
    print("Diff text report :", txt_out)

    print("\nDIFF SUMMARY")

    if diff["drift_detected"]:
        print("Fabric drift detected")
    else:
        print("Fabric stable")


if __name__ == "__main__":
    main()
