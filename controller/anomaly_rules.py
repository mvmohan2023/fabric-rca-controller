def _get(data: dict, path: list, default=0):
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def rule_bgp_up_dropped(pre: dict, post: dict):
    pre_up = _get(pre, ["bgp", "up"], 0)
    post_up = _get(post, ["bgp", "up"], 0)

    if post_up < pre_up:
        return {
            "rule_name": "bgp_up_dropped",
            "severity": "critical",
            "detected": True,
            "details": {
                "pre_up": pre_up,
                "post_up": post_up,
                "delta": post_up - pre_up,
            }
        }

    return {
        "rule_name": "bgp_up_dropped",
        "severity": "critical",
        "detected": False,
        "details": {
            "pre_up": pre_up,
            "post_up": post_up,
            "delta": post_up - pre_up,
        }
    }


def rule_bgp_missing_increased(pre: dict, post: dict):
    pre_missing = _get(pre, ["bgp", "missing"], 0)
    post_missing = _get(post, ["bgp", "missing"], 0)

    if post_missing > pre_missing:
        return {
            "rule_name": "bgp_missing_increased",
            "severity": "critical",
            "detected": True,
            "details": {
                "pre_missing": pre_missing,
                "post_missing": post_missing,
                "delta": post_missing - pre_missing,
            }
        }

    return {
        "rule_name": "bgp_missing_increased",
        "severity": "critical",
        "detected": False,
        "details": {
            "pre_missing": pre_missing,
            "post_missing": post_missing,
            "delta": post_missing - pre_missing,
        }
    }


def rule_links_missing_increased(pre: dict, post: dict):
    pre_missing = _get(pre, ["physical_links", "missing"], 0)
    post_missing = _get(post, ["physical_links", "missing"], 0)

    if post_missing > pre_missing:
        return {
            "rule_name": "links_missing_increased",
            "severity": "critical",
            "detected": True,
            "details": {
                "pre_missing": pre_missing,
                "post_missing": post_missing,
                "delta": post_missing - pre_missing,
            }
        }

    return {
        "rule_name": "links_missing_increased",
        "severity": "critical",
        "detected": False,
        "details": {
            "pre_missing": pre_missing,
            "post_missing": post_missing,
            "delta": post_missing - pre_missing,
        }
    }


def rule_ipv4_mismatch_increased(pre: dict, post: dict):
    pre_v = _get(pre, ["ip_consistency", "ipv4_mismatch"], 0)
    post_v = _get(post, ["ip_consistency", "ipv4_mismatch"], 0)

    if post_v > pre_v:
        return {
            "rule_name": "ipv4_mismatch_increased",
            "severity": "major",
            "detected": True,
            "details": {
                "pre_ipv4_mismatch": pre_v,
                "post_ipv4_mismatch": post_v,
                "delta": post_v - pre_v,
            }
        }

    return {
        "rule_name": "ipv4_mismatch_increased",
        "severity": "major",
        "detected": False,
        "details": {
            "pre_ipv4_mismatch": pre_v,
            "post_ipv4_mismatch": post_v,
            "delta": post_v - pre_v,
        }
    }


def rule_ipv6_mismatch_increased(pre: dict, post: dict):
    pre_v = _get(pre, ["ip_consistency", "ipv6_mismatch"], 0)
    post_v = _get(post, ["ip_consistency", "ipv6_mismatch"], 0)

    if post_v > pre_v:
        return {
            "rule_name": "ipv6_mismatch_increased",
            "severity": "major",
            "detected": True,
            "details": {
                "pre_ipv6_mismatch": pre_v,
                "post_ipv6_mismatch": post_v,
                "delta": post_v - pre_v,
            }
        }

    return {
        "rule_name": "ipv6_mismatch_increased",
        "severity": "major",
        "detected": False,
        "details": {
            "pre_ipv6_mismatch": pre_v,
            "post_ipv6_mismatch": post_v,
            "delta": post_v - pre_v,
        }
    }


def rule_fabric_not_ready(pre: dict, post: dict):
    pre_ready = pre.get("ready_for_stress")
    post_ready = post.get("ready_for_stress")

    if pre_ready is True and post_ready is not True:
        return {
            "rule_name": "fabric_not_ready_after_stress",
            "severity": "critical",
            "detected": True,
            "details": {
                "pre_ready": pre_ready,
                "post_ready": post_ready,
            }
        }

    return {
        "rule_name": "fabric_not_ready_after_stress",
        "severity": "critical",
        "detected": False,
        "details": {
            "pre_ready": pre_ready,
            "post_ready": post_ready,
        }
    }


DEFAULT_RULES = [
    rule_bgp_up_dropped,
    rule_bgp_missing_increased,
    rule_links_missing_increased,
    rule_ipv4_mismatch_increased,
    rule_ipv6_mismatch_increased,
    rule_fabric_not_ready,
]
