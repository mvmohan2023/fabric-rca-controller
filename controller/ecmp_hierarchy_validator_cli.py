from __future__ import annotations

import argparse

from controller.ecmp_hierarchy_validator import analyze_ecmp_hierarchy_lifecycle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze ECMP hierarchy lifecycle / stale ECMP token symptoms."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pfe-log", required=True)
    parser.add_argument("--objmon", default=None)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    report = analyze_ecmp_hierarchy_lifecycle(
        run_id=args.run_id,
        pfe_log_path=args.pfe_log,
        objmon_path=args.objmon,
        output_path=args.output,
    )

    print(f"ECMP hierarchy lifecycle report written to: {args.output}")
    print(f"verdict={report.get('verdict')} root_cause={report.get('root_cause')}")


if __name__ == "__main__":
    main()
