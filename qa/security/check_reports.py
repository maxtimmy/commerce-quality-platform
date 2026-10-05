import json
import sys
from collections import Counter
from pathlib import Path


def alert_risk(alert: dict) -> int:
    value = alert.get("riskcode", alert.get("risk", 0))
    try:
        return int(value)
    except (TypeError, ValueError):
        names = {"informational": 0, "info": 0, "low": 1, "medium": 2, "high": 3}
        return names.get(str(value).lower(), 0)


def classifications(report: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    config_name = "zap-web.conf" if report.name == "web.json" else "zap-api.conf"
    path = Path("qa/security") / config_name
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            result[parts[0]] = (parts[1].lower(), parts[2])
    return result


def main(arguments: list[str]) -> int:
    if not arguments:
        raise SystemExit("Usage: check_reports.py REPORT.json [REPORT.json ...]")

    counts: Counter[str] = Counter()
    blocking: list[dict[str, str]] = []
    triaged_alerts: list[dict[str, str]] = []
    reports: list[str] = []
    labels = {0: "informational", 1: "low", 2: "medium", 3: "high"}

    for argument in arguments:
        path = Path(argument)
        if not path.is_file():
            print(f"Missing ZAP report: {path}", file=sys.stderr)
            return 2
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Invalid ZAP report {path}: {exc}", file=sys.stderr)
            return 2
        reports.append(str(path))
        triage = classifications(path)
        for site in payload.get("site", []):
            for alert in site.get("alerts", []):
                risk = alert_risk(alert)
                original_label = labels.get(risk, f"unknown-{risk}")
                plugin_id = str(alert.get("pluginid", ""))
                alert_name = str(alert.get("alert", alert.get("name", "unknown")))
                default_action = "fail" if risk >= 2 else "warn" if risk == 1 else "info"
                action, rationale = triage.get(plugin_id, (default_action, "Default risk policy"))
                if "server error response code" in alert_name.lower():
                    action = "fail"
                    rationale = "HTTP 5xx responses always block DAST runs"
                counts[action] += 1
                triaged_alerts.append(
                    {
                        "report": str(path),
                        "plugin_id": plugin_id,
                        "alert": alert_name,
                        "original_risk": original_label,
                        "action": action,
                        "rationale": rationale,
                    }
                )
                if action == "fail":
                    blocking.append(
                        {
                            "report": str(path),
                            "risk": original_label,
                            "alert": alert_name,
                        }
                    )

    summary = {
        "reports": reports,
        "alert_counts": dict(sorted(counts.items())),
        "blocking_alerts": blocking,
        "triaged_alerts": triaged_alerts,
        "result": "fail" if blocking else "pass",
    }
    output = Path("security-results/summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
