import json
import sys
from pathlib import Path
from controller.utils import atomic_write_json

VALIDATION_REPORT_FILE = Path("/root/fabric-controller/artifacts/validation/fabric_validation_report.json")
OUTPUT_DIR = Path("/root/fabric-controller/artifacts/precheck")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_validation_report():
    if not VALIDATION_REPORT_FILE.exists():
        raise FileNotFoundError(
            f"Validation report not found: {VALIDATION_REPORT_FILE}. "
            f"Run 'python -m controller.topology_validator' first."
        )

    with open(VALIDATION_REPORT_FILE, "r") as f:
        return json.load(f)


def evaluate_physical_links(summary):
    physical = summary.get("physical_links", {})
    total_expected = physical.get("total_expected", 0)
    present = physical.get("present", 0)
    missing = physical.get("missing", 0)

    passed = (total_expected > 0 and missing == 0 and present == total_expected)

    return {
        "name": "physical_links",
        "status": "pass" if passed else "fail",
        "details": {
            "total_expected": total_expected,
            "present": present,
            "missing": missing,
        },
        "reason": None if passed else (
            f"Physical link validation failed: expected={total_expected}, "
            f"present={present}, missing={missing}"
        )
    }


def evaluate_ip_consistency(summary):
    ip = summary.get("ip_consistency", {})
    total_links_checked = ip.get("total_links_checked", 0)

    ipv4_mismatch = ip.get("ipv4_mismatch", 0)
    ipv4_partial = ip.get("ipv4_partial", 0)
    ipv6_mismatch = ip.get("ipv6_mismatch", 0)
    ipv6_partial = ip.get("ipv6_partial", 0)

    passed = (
        total_links_checked > 0 and
        ipv4_mismatch == 0 and
        ipv4_partial == 0 and
        ipv6_mismatch == 0 and
        ipv6_partial == 0
    )

    return {
        "name": "ip_consistency",
        "status": "pass" if passed else "fail",
        "details": {
            "total_links_checked": total_links_checked,
            "ipv4_match": ip.get("ipv4_match", 0),
            "ipv4_mismatch": ipv4_mismatch,
            "ipv4_partial": ipv4_partial,
            "ipv6_match": ip.get("ipv6_match", 0),
            "ipv6_mismatch": ipv6_mismatch,
            "ipv6_partial": ipv6_partial,
        },
        "reason": None if passed else (
            f"IP consistency validation failed: "
            f"ipv4_mismatch={ipv4_mismatch}, ipv4_partial={ipv4_partial}, "
            f"ipv6_mismatch={ipv6_mismatch}, ipv6_partial={ipv6_partial}"
        )
    }


def evaluate_bgp(summary):
    bgp = summary.get("bgp", {})
    total_expected = bgp.get("total_expected", 0)
    up = bgp.get("up", 0)
    down = bgp.get("down", 0)
    missing = bgp.get("missing", 0)

    passed = (total_expected > 0 and up == total_expected and down == 0 and missing == 0)

    return {
        "name": "bgp",
        "status": "pass" if passed else "fail",
        "details": {
            "total_expected": total_expected,
            "up": up,
            "down": down,
            "missing": missing,
        },
        "reason": None if passed else (
            f"BGP validation failed: expected={total_expected}, up={up}, "
            f"down={down}, missing={missing}"
        )
    }


def build_precheck_report(validation_report):
    summary = validation_report.get("summary", {})

    checks = [
        evaluate_physical_links(summary),
        evaluate_ip_consistency(summary),
        evaluate_bgp(summary),
    ]

    failed_checks = [check for check in checks if check["status"] == "fail"]
    ready_for_stress = len(failed_checks) == 0

    report = {
        "ready_for_stress": ready_for_stress,
        "overall_status": "pass" if ready_for_stress else "fail",
        "checks": {check["name"]: check for check in checks},
        "failure_reasons": [check["reason"] for check in failed_checks if check["reason"]],
        "summary": {
            "physical_links": summary.get("physical_links", {}),
            "ip_consistency": summary.get("ip_consistency", {}),
            "bgp": summary.get("bgp", {}),
        }
    }

    return report


def write_json_report(report, outfile: Path):
    #with open(outfile, "w") as f:
    #    json.dump(report, f, indent=2)
    atomic_write_json(outfile, report, indent=2)


def write_text_report(report, outfile: Path):
    with open(outfile, "w") as f:
        f.write("STRESS PRECHECK REPORT\n")
        f.write("======================\n\n")

        f.write(f"Overall status    : {report['overall_status']}\n")
        f.write(f"Ready for stress  : {report['ready_for_stress']}\n\n")

        f.write("CHECK RESULTS\n")
        f.write("-------------\n")
        for check_name, check in report["checks"].items():
            f.write(f"{check_name}: {check['status']}\n")
            for key, value in check.get("details", {}).items():
                f.write(f"  {key}: {value}\n")
            if check.get("reason"):
                f.write(f"  reason: {check['reason']}\n")
            f.write("\n")

        f.write("FAILURE REASONS\n")
        f.write("---------------\n")
        if not report["failure_reasons"]:
            f.write("None\n")
        else:
            for reason in report["failure_reasons"]:
                f.write(f"- {reason}\n")


def print_console_summary(report, json_out: Path, txt_out: Path):
    print(f"Precheck JSON report : {json_out}")
    print(f"Precheck text report : {txt_out}")
    print("\nPRECHECK SUMMARY")
    print(f"  Overall status   : {report['overall_status']}")
    print(f"  Ready for stress : {report['ready_for_stress']}")

    for check_name, check in report["checks"].items():
        print(f"  {check_name}: {check['status']}")

    if report["failure_reasons"]:
        print("\nFAILURE REASONS")
        for reason in report["failure_reasons"]:
            print(f"  - {reason}")


def main():
    ensure_dir(OUTPUT_DIR)

    validation_report = load_validation_report()
    precheck_report = build_precheck_report(validation_report)

    json_out = OUTPUT_DIR / "stress_precheck_report.json"
    txt_out = OUTPUT_DIR / "stress_precheck_report.txt"

    write_json_report(precheck_report, json_out)
    write_text_report(precheck_report, txt_out)
    print_console_summary(precheck_report, json_out, txt_out)

    sys.exit(0 if precheck_report["ready_for_stress"] else 1)


if __name__ == "__main__":
    main()
