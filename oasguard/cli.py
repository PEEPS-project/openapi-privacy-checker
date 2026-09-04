"""Command-line interface (installed as `oasguard`, or `python -m oasguard`).

  run       one-shot:  oasguard run <spec-url-or-path>   (the front door)
  capture   run the Locust scenarios against Stripe -> a trace
  detect    compare the trace against the spec -> report (console/json/sarif/markdown)
  enrich    write a corrected spec: violations added, open maps annotated
  all       capture -> detect -> enrich in one run
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

from .detect import analyze, read_trace
from .enrich import enrich
from .rules import PrivacyRules
from .spec import Spec

# Resolved from the module, never the working directory, so the installed
# command finds scenarios/ and the venv regardless of where it is run.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- core steps (shared by the single commands and by `all`) ---------------
def _do_capture(names, host, time_, out, trace_dir):
    """Run scenarios; merge their traces into `out`. Return the request count,
    or None if locust is missing."""
    locust = _find_locust()
    if not locust:
        print("ERROR: locust not found. Install with 'pip install -e .'.",
              file=sys.stderr)
        return None

    names = names or _all_scenarios()
    os.makedirs(trace_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    merged = []
    for name in names:
        path = os.path.join(PROJECT_ROOT, "scenarios", f"{name}.py")
        if not os.path.exists(path):
            print(f"  {name:18} SKIP (no such scenario)")
            continue
        trace = os.path.join(trace_dir, f"{name}.jsonl")
        env = {**os.environ, "TRACE_PATH": trace}
        proc = subprocess.run(
            [locust, "-f", path, "--headless", "-u", "1", "-r", "1",
             "-t", time_, "--host", host],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
        count = _count_lines(trace)
        print(f"  {name:18} "
              + (f"{count} requests" if count else f"FAILED (rc={proc.returncode})"))
        if count:
            with open(trace) as f:
                merged.extend(f.readlines())

    with open(out, "w") as f:
        f.writelines(merged)
    print(f"  merged {len(merged)} requests into {out}")
    return len(merged)


def _emit(report, formats, out_dir, explain=False):
    """Render the report to the requested formats."""
    os.makedirs(out_dir, exist_ok=True)
    if "console" in formats:
        print(report.render("console", verbose=explain))
    if "markdown" in formats:
        _write(report.render("markdown"), os.path.join(out_dir, "report.md"))
    if "json" in formats:
        report.write_json(os.path.join(out_dir, "findings.json"))
        print(f"Wrote {os.path.join(out_dir, 'findings.json')}")
    if "sarif" in formats:
        report.write_sarif(os.path.join(out_dir, "findings.sarif"))
        print(f"Wrote {os.path.join(out_dir, 'findings.sarif')}")


def _do_enrich(spec, report, out, annotate_open_maps):
    enriched, stats = enrich(spec, report, annotate_open_maps=annotate_open_maps)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(enriched.doc, f, indent=2)
    print(f"Enriched spec written to {out}")
    print(f"  violations added to schemas          : {stats['fields_added']}")
    print(f"  open maps annotated (x-observed-pii) : {stats['maps_annotated']}")


# --- commands --------------------------------------------------------------
def cmd_capture(args):
    return 0 if _do_capture(args.names, args.host, args.time,
                            args.out, args.trace_dir) is not None else 1


def cmd_detect(args):
    spec, rules = _load(args.spec, args.rules)
    report = analyze(spec, rules, read_trace(args.trace))
    _emit(report, args.format, args.out_dir, args.explain)
    return _exit_code(report, args.fail_on)


def cmd_enrich(args):
    spec, rules = _load(args.spec, args.rules)
    report = analyze(spec, rules, read_trace(args.trace))
    _do_enrich(spec, report, args.out, not args.no_open_maps)
    return 0


def cmd_run(args):
    """schemathesis-style front door: `oasguard run <spec>`.

    With --trace, analyzes that trace against the spec (portable, works on any
    API). Without it, captures traffic with the Stripe scenarios first."""
    trace = args.trace or os.path.join(args.out_dir, "trace.jsonl")
    if not args.trace:
        print("== capture ==")
        if _do_capture(args.names, args.host, args.time, trace,
                       os.path.join(args.out_dir, "traces")) is None:
            return 1
        print()

    spec, rules = _load(args.spec, args.rules)
    report = analyze(spec, rules, read_trace(trace))
    _emit(report, args.format, args.out_dir, args.explain)
    code = _exit_code(report, args.fail_on)

    if not args.no_enrich:
        print("\n== enrich ==")
        _do_enrich(spec, report, args.enrich_out, True)
    return code


def cmd_all(args):
    print("== capture ==")
    if not args.skip_capture:
        if _do_capture(args.names, args.host, args.time, args.trace, args.trace_dir) is None:
            return 1
    else:
        print(f"  skipped, using {args.trace}")

    print("\n== detect ==")
    spec, rules = _load(args.spec, args.rules)
    report = analyze(spec, rules, read_trace(args.trace))
    _emit(report, args.format, args.out_dir, args.explain)
    code = _exit_code(report, args.fail_on)

    if not args.skip_enrich:
        print("\n== enrich ==")
        _do_enrich(spec, report, args.enrich_out, True)
    return code


# --- helpers ---------------------------------------------------------------
def _load(spec_path, rules_path):
    return Spec.load(spec_path), PrivacyRules.load(rules_path)


def _write(text, path):
    with open(path, "w") as f:
        f.write(text)
    print(f"Wrote {path}")


def _exit_code(report, fail_on):
    if fail_on == "never":
        return 0
    if fail_on == "exposure":
        return 1 if report.exposures else 0
    if fail_on == "any":
        return 1 if (report.inconsistencies or report.exposures) else 0
    return 1 if report.inconsistencies else 0       # default: "violation"


def _find_locust():
    local = os.path.join(PROJECT_ROOT, ".venv", "bin", "locust")
    return local if os.path.exists(local) else shutil.which("locust")


def _all_scenarios():
    folder = os.path.join(PROJECT_ROOT, "scenarios")
    skip = {"common", "capture", "__init__"}
    return sorted(f[:-3] for f in os.listdir(folder)
                  if f.endswith(".py") and f[:-3] not in skip)


def _count_lines(path):
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return sum(1 for _ in f)


# --- parser ----------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="oasguard",
                                description="Detect undeclared personal data in "
                                            "Web API responses via the OpenAPI spec.")
    sub = p.add_subparsers(dest="command", required=True)

    def add_capture_opts(sp):
        sp.add_argument("names", nargs="*", help="scenario names (default: all)")
        sp.add_argument("--host", default="https://api.stripe.com")
        sp.add_argument("--time", default="20s")

    def add_analysis_opts(sp):
        sp.add_argument("--spec", default="spec3.json")
        sp.add_argument("--rules", default=None,
                        help="privacy_rules.yaml (default: bundled)")

    fmt_choices = ["console", "markdown", "json", "sarif"]
    fail_choices = ["never", "violation", "exposure", "any"]

    r = sub.add_parser("run",
                       help="one-shot: capture (or reuse a trace) -> detect -> enrich")
    r.add_argument("spec", help="OpenAPI spec: local path or http(s) URL")
    r.add_argument("names", nargs="*", help="scenarios to capture (default: all)")
    r.add_argument("--trace", default=None,
                   help="analyze this trace instead of capturing (portable mode)")
    r.add_argument("--host", default="https://api.stripe.com")
    r.add_argument("--time", default="20s")
    r.add_argument("--rules", default=None)
    r.add_argument("--out-dir", default="out")
    r.add_argument("--enrich-out", default="out/spec.enriched.json")
    r.add_argument("--format", nargs="+", default=["console", "markdown", "json"],
                   choices=fmt_choices)
    r.add_argument("--fail-on", choices=fail_choices, default="violation")
    r.add_argument("--no-enrich", action="store_true")
    r.add_argument("--explain", action="store_true",
                   help="show full per-finding GDPR explanations")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("capture", help="run scenarios against Stripe into a trace")
    add_capture_opts(c)
    c.add_argument("--out", default="out/trace.jsonl")
    c.add_argument("--trace-dir", default="out/traces")
    c.set_defaults(func=cmd_capture)

    d = sub.add_parser("detect", help="report undeclared / undocumented personal data")
    add_analysis_opts(d)
    d.add_argument("--trace", default="out/trace.jsonl")
    d.add_argument("--format", nargs="+", default=["console"],
                   choices=["console", "markdown", "json", "sarif"],
                   help="one or more output formats (default: console)")
    d.add_argument("--out-dir", default="out")
    d.add_argument("--fail-on", choices=["never", "violation", "exposure", "any"],
                   default="violation",
                   help="exit non-zero on: never | a spec violation (default) | "
                        "any exposure | any finding")
    d.add_argument("--explain", action="store_true",
                   help="show full per-finding GDPR explanations")
    d.set_defaults(func=cmd_detect)

    e = sub.add_parser("enrich", help="write a corrected spec from the findings")
    add_analysis_opts(e)
    e.add_argument("--trace", default="out/trace.jsonl")
    e.add_argument("--out", default="out/spec.enriched.json")
    e.add_argument("--no-open-maps", action="store_true",
                   help="skip Case B (do not annotate open maps)")
    e.set_defaults(func=cmd_enrich)

    a = sub.add_parser("all", help="capture -> detect -> enrich in one run")
    add_capture_opts(a)
    add_analysis_opts(a)
    a.add_argument("--trace", default="out/trace.jsonl")
    a.add_argument("--trace-dir", default="out/traces")
    a.add_argument("--out-dir", default="out")
    a.add_argument("--enrich-out", default="out/spec.enriched.json")
    a.add_argument("--format", nargs="+", default=["console", "markdown", "json"],
                   choices=["console", "markdown", "json", "sarif"])
    a.add_argument("--fail-on", choices=["never", "violation", "exposure", "any"],
                   default="violation")
    a.add_argument("--skip-capture", action="store_true",
                   help="reuse the existing --trace instead of running scenarios")
    a.add_argument("--skip-enrich", action="store_true")
    a.add_argument("--explain", action="store_true",
                   help="show full per-finding GDPR explanations")
    a.set_defaults(func=cmd_all)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
