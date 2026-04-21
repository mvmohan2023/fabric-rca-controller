# controller/ixia_rocev2_suite.py

import argparse
import os
import shlex
import subprocess
import sys
import time

def run_cmd(cmd: str) -> None:
    print(f"[SUITE] command:\n  {cmd}")
    rc = subprocess.call(cmd, shell=True)
    if rc != 0:
        raise RuntimeError(f"command failed rc={rc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RoCEv2 suite: pre/post stats + verifier + deep inspection")
    parser.add_argument("--source-type", default="campaign", choices=["campaign", "orchestrator"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--inventory", default="controller/ixia_inventory.json")
    parser.add_argument("--api-server", default=None)
    parser.add_argument("--session-id", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--verify-tls", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        base = f"python -m"
        common = (
            f"--source-type {shlex.quote(args.source_type)} "
            f"--run-id {shlex.quote(args.run_id)} "
            f"--inventory {shlex.quote(args.inventory)} "
            f"--timeout {args.timeout} "
        )

        if args.api_server:
            common += f"--api-server {shlex.quote(args.api_server)} "
        if args.session_id is not None:
            common += f"--session-id {args.session_id} "
        if args.verify_tls:
            common += "--verify-tls "

        print("[SUITE] Collect PRE RoCEv2 snapshot")
        run_cmd(
            f"{base} controller.ixia_rocev2_stats "
            f"{common} "
            f"--snapshot-name rocev2_pre"
        )

        print("[SUITE] Collect POST RoCEv2 snapshot")
        run_cmd(
            f"{base} controller.ixia_rocev2_stats "
            f"{common} "
            f"--snapshot-name rocev2_post"
        )

        pre = f"artifacts/{args.source_type}s/{args.run_id}/traffic/rocev2_pre_ixia_rocev2_flow_stats.json"
        post = f"artifacts/{args.source_type}s/{args.run_id}/traffic/rocev2_post_ixia_rocev2_flow_stats.json"
        verdict = f"artifacts/{args.source_type}s/{args.run_id}/traffic/rocev2_verdict.json"

        print("[SUITE] Run RoCEv2 verifier")
        run_cmd(
            f"{base} controller.rocev2_verifier "
            f"--source-type {shlex.quote(args.source_type)} "
            f"--run-id {shlex.quote(args.run_id)} "
            f"--pre {shlex.quote(pre)} "
            f"--post {shlex.quote(post)}"
        )

        print("[SUITE] Run deep inspection")
        run_cmd(
            f"{base} controller.rocev2_deep_inspector "
            f"--source-type {shlex.quote(args.source_type)} "
            f"--run-id {shlex.quote(args.run_id)} "
            f"--pre {shlex.quote(pre)} "
            f"--post {shlex.quote(post)} "
            f"--verdict {shlex.quote(verdict)}"
        )

        print("")
        print("IXIA ROCEV2 SUITE SUMMARY")
        print(f"  Run ID          : {args.run_id}")
        print(f"  Pre snapshot    : {pre}")
        print(f"  Post snapshot   : {post}")
        print(f"  Verdict report  : {verdict}")
        print(
            f"  Deep report     : artifacts/{args.source_type}s/{args.run_id}/traffic/rocev2_deep_inspection.json"
        )

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
