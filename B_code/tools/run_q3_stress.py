"""Q3-baseline-v1 official stress-test orchestrator.

This tool does not implement or tune the Q3 algorithm.  It runs exactly one
operator-started official practice case at a time, captures the console output,
parses only values that are explicitly available, and immediately writes a
machine-readable result beside the console log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree


ALGORITHM_VERSION = "Q3-baseline-v1"
RUN_IDS = tuple(f"Q3-S-{index:03d}" for index in range(1, 6))
ROBOT_ID_DEFAULT = "202619001600"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE = PROJECT_ROOT / "B_code" / "scripts" / "baseline_q3_all.py"
SOURCE_FILES = (
    PROJECT_ROOT / "B_code" / "scripts" / "baseline_q3_all.py",
    PROJECT_ROOT / "B_code" / "src" / "simulator_client.py",
    PROJECT_ROOT / "B_code" / "src" / "geometry.py",
)
FROZEN_DIR = PROJECT_ROOT / "B_code" / "frozen" / "q3_baseline_v1"
FROZEN_FILES = (
    FROZEN_DIR / "baseline_q3_all.py",
    FROZEN_DIR / "simulator_client.py",
    FROZEN_DIR / "geometry.py",
)
RESULTS_ROOT = PROJECT_ROOT / "03_results" / "stress_test" / "q3"
RESULTS_MASTER = PROJECT_ROOT / "03_results" / "RESULTS_MASTER.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one of five operator-started official Q3 stress cases without "
            "changing the frozen baseline."
        )
    )
    parser.add_argument(
        "--run-id",
        choices=RUN_IDS,
        help="Case to run. If omitted, select the first case without a result file.",
    )
    parser.add_argument(
        "--robot-id",
        default=ROBOT_ID_DEFAULT,
        help="Official simulator robot/team identifier; passed through to baseline.",
    )
    parser.add_argument(
        "--actual-sources",
        type=int,
        help=(
            "True source count read from official case information. Omit when "
            "unavailable; the result stays blank and is flagged for manual entry."
        ),
    )
    parser.add_argument(
        "--actual-sources-note",
        help="Short provenance note for --actual-sources, such as official web page.",
    )
    parser.add_argument(
        "--official-log",
        action="append",
        default=[],
        type=Path,
        help="Official raw log to copy after the run; may be supplied more than once.",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Read all five saved run_result.json files and print aggregate JSON.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def verify_frozen_sources() -> dict[str, str]:
    missing = [path for path in SOURCE_FILES + FROZEN_FILES if not path.is_file()]
    if missing:
        raise RuntimeError("Missing required source/frozen file: " + ", ".join(map(str, missing)))

    hashes: dict[str, str] = {}
    for source, frozen in zip(SOURCE_FILES, FROZEN_FILES):
        source_hash = sha256(source)
        frozen_hash = sha256(frozen)
        if source_hash != frozen_hash:
            raise RuntimeError(
                f"Frozen hash mismatch; refusing to run: {source} != {frozen}"
            )
        hashes[source.relative_to(PROJECT_ROOT).as_posix()] = source_hash
    return hashes


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values = []
    for item in root.findall("x:si", namespace):
        values.append("".join(node.text or "" for node in item.findall(".//x:t", namespace)))
    return values


def existing_run_ids_in_master() -> set[str]:
    """Read workbook strings without modifying the workbook."""
    if not RESULTS_MASTER.is_file():
        raise RuntimeError(f"Missing RESULTS_MASTER: {RESULTS_MASTER}")
    with zipfile.ZipFile(RESULTS_MASTER) as archive:
        strings = _shared_strings(archive)
        found: set[str] = set()
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            root = ElementTree.fromstring(archive.read(name))
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for cell in root.findall(".//x:c", ns):
                value = cell.find("x:v", ns)
                inline = cell.find("x:is", ns)
                text = None
                if cell.get("t") == "s" and value is not None and value.text:
                    text = strings[int(value.text)]
                elif inline is not None:
                    text = "".join(node.text or "" for node in inline.findall(".//x:t", ns))
                elif value is not None:
                    text = value.text
                if text in RUN_IDS:
                    found.add(text)
        return found


def select_run_id(requested: str | None) -> str:
    completed = {
        run_id
        for run_id in RUN_IDS
        if (RESULTS_ROOT / run_id / "run_result.json").is_file()
    }
    recorded = existing_run_ids_in_master()
    if requested:
        if requested in completed or requested in recorded:
            raise RuntimeError(f"run_id already exists; refusing to overwrite: {requested}")
        return requested
    for run_id in RUN_IDS:
        if run_id not in completed and run_id not in recorded:
            return run_id
    raise RuntimeError("All five run_ids already exist; no run was started.")


def one_match(pattern: str, text: str, cast):
    match = re.search(pattern, text, flags=re.MULTILINE)
    return cast(match.group(1)) if match else None


def parse_console(text: str, return_code: int) -> dict[str, object]:
    discovered = one_match(r"^\u53d1\u73b0\u9891\u9053\u6570\u91cf:\s*(\d+)\s*$", text, int)
    cleared = one_match(r"^\u6210\u529f\u6e05\u9664\u6570\u91cf:\s*(\d+)\s*$", text, int)
    virtual_time = one_match(r"^\u603bvirtual_time_s:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text, float)
    recon_count = one_match(r"^\u4fa6\u5bdf\u8bb0\u5f55\u6570:\s*(\d+)\s*$", text, int)

    final_clear_counts = [int(value) for value in re.findall(r"clear\u6b21\u6570=(\d+)\s*$", text, re.MULTILINE)]
    clear_attempts = sum(final_clear_counts) if final_clear_counts else None
    clear_results = re.findall(r"result=([^\s]+)\s+virtual_time_s=", text)
    if clear_attempts is not None and cleared is not None:
        # clear_one_channel stops after its first success, so every cleared
        # channel contributes exactly one successful attempt.
        clear_failures = max(clear_attempts - cleared, 0)
    elif clear_results:
        clear_failures = sum(result != "success" for result in clear_results)
    else:
        clear_failures = None

    if recon_count is None:
        measure_count = None
    else:
        supplemental = len(re.findall(r"^channel=\d+ \u8865\u6d4b ", text, re.MULTILINE))
        fallback = len(re.findall(r"^channel=\d+ \u65b0\u4f4d\u7f6e\u8865\u6d4b:", text, re.MULTILINE))
        measure_count = recon_count + supplemental + fallback

    unresolved_match = re.search(r"^\u672a\u6e05\u9664\u9891\u9053:\s*(\[[^\n]*\])", text, re.MULTILINE)
    unresolved = unresolved_match.group(1) if unresolved_match else None
    failure_channels = sorted(
        {
            int(channel)
            for channel, result in re.findall(
                r"^channel=(\d+) clear#\d+ .*? result=([^\s]+)",
                text,
                re.MULTILINE,
            )
            if result != "success"
        }
    )
    interrupted = "baseline\u6267\u884c\u4e2d\u6b62:" in text
    exit_failed = "\u9000\u51fa\u5931\u8d25:" in text
    final_summary_missing = discovered is None or cleared is None or virtual_time is None
    crashed = bool(return_code != 0 or interrupted or exit_failed or final_summary_missing)

    notes = []
    if unresolved:
        notes.append(f"unresolved_channels={unresolved}")
    if failure_channels:
        notes.append(f"clear_failure_channels={failure_channels}")
    if clear_failures:
        notes.append(f"clear_failures={clear_failures}")
    if crashed:
        notes.append("crash_or_incomplete_final_summary")
    if unresolved or clear_failures or crashed:
        notes.insert(0, "FAIL_RECORDED")

    return {
        "discovered_sources": discovered,
        "cleared_sources": cleared,
        "virtual_time_s": virtual_time,
        "measure_count": measure_count,
        "clear_attempts": clear_attempts,
        "clear_failures": clear_failures,
        "move_distance_m": None,
        "crashed": crashed,
        "notes": "; ".join(notes),
    }


def copy_official_logs(paths: list[Path], run_dir: Path) -> list[str]:
    copied = []
    for source in paths:
        resolved = source.expanduser().resolve()
        if not resolved.is_file():
            raise RuntimeError(f"Official log does not exist: {source}")
        destination = run_dir / resolved.name
        if destination.exists():
            raise RuntimeError(f"Refusing to overwrite existing log: {destination}")
        shutil.copy2(resolved, destination)
        copied.append(destination.relative_to(PROJECT_ROOT).as_posix())
    return copied


def run_case(args: argparse.Namespace) -> int:
    hashes = verify_frozen_sources()
    run_id = select_run_id(args.run_id)
    if args.actual_sources is not None and args.actual_sources < 0:
        raise RuntimeError("--actual-sources must be non-negative")
    if args.actual_sources is not None and not args.actual_sources_note:
        raise RuntimeError("--actual-sources-note is required when actual source count is supplied")

    run_dir = RESULTS_ROOT / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RuntimeError(f"Run directory is not empty; refusing to overwrite: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    console_path = run_dir / "console_output.txt"
    result_path = run_dir / "run_result.json"

    command = [sys.executable, str(BASELINE), "--robot-id", args.robot_id]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    started_at = datetime.now().astimezone()
    wall_start = time.perf_counter()

    with console_path.open("x", encoding="utf-8", newline="") as log_stream:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log_stream.write(line)
                log_stream.flush()
        except KeyboardInterrupt:
            process.terminate()
            process.wait(timeout=10)
            raise
        return_code = process.wait()

    runtime_s = time.perf_counter() - wall_start
    console_text = console_path.read_text(encoding="utf-8")
    parsed = parse_console(console_text, return_code)
    official_logs = copy_official_logs(args.official_log, run_dir)

    actual = args.actual_sources
    discovered = parsed["discovered_sources"]
    cleared = parsed["cleared_sources"]
    virtual_time = parsed["virtual_time_s"]
    discovery_rate = discovered / actual if actual not in (None, 0) and discovered is not None else None
    clear_rate = cleared / actual if actual not in (None, 0) and cleared is not None else None
    mean_clear = virtual_time / cleared if cleared not in (None, 0) and virtual_time is not None else None

    notes = [part for part in [str(parsed["notes"])] if part]
    if actual is None:
        notes.append("actual_sources missing; manual entry required from official case information")
    else:
        notes.append(f"actual_sources provenance: {args.actual_sources_note}")

    result = {
        "run_id": run_id,
        "date_time": started_at.isoformat(timespec="seconds"),
        "problem": "Q3",
        "test_type": "stress",
        "algorithm_version": ALGORITHM_VERSION,
        "git_commit": git_commit(),
        "actual_sources": actual,
        "discovered_sources": discovered,
        "cleared_sources": cleared,
        "discovery_rate": discovery_rate,
        "clear_rate": clear_rate,
        "virtual_time_s": virtual_time,
        "mean_clear_time_s": mean_clear,
        "runtime_s": runtime_s,
        "crashed": parsed["crashed"],
        "log_file": console_path.relative_to(PROJECT_ROOT).as_posix(),
        "notes": "; ".join(notes),
        "measure_count": parsed["measure_count"],
        "clear_attempts": parsed["clear_attempts"],
        "clear_failures": parsed["clear_failures"],
        "move_distance_m": parsed["move_distance_m"],
        "actual_sources_provenance": args.actual_sources_note,
        "official_log_files": official_logs,
        "source_sha256": hashes,
        "baseline_command": command,
        "return_code": return_code,
    }
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n===== STRESS ORCHESTRATOR RESULT =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {result_path}")
    print("Next required step: append this run to RESULTS_MASTER.xlsx immediately.")
    return 1 if parsed["crashed"] else 0


def numeric_stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def summarize() -> int:
    results = []
    missing_files = []
    for run_id in RUN_IDS:
        path = RESULTS_ROOT / run_id / "run_result.json"
        if not path.is_file():
            missing_files.append(path.relative_to(PROJECT_ROOT).as_posix())
            continue
        results.append(json.loads(path.read_text(encoding="utf-8")))
    if missing_files:
        raise RuntimeError("Five runs are not complete; missing: " + ", ".join(missing_files))

    actual_known = all(row.get("actual_sources") is not None for row in results)
    total_actual = sum(row["actual_sources"] for row in results) if actual_known else None
    total_discovered = sum(row["discovered_sources"] for row in results if row["discovered_sources"] is not None)
    total_cleared = sum(row["cleared_sources"] for row in results if row["cleared_sources"] is not None)
    missing_fields = {
        row["run_id"]: [
            key
            for key in (
                "actual_sources",
                "discovered_sources",
                "cleared_sources",
                "virtual_time_s",
                "mean_clear_time_s",
                "measure_count",
                "clear_attempts",
                "clear_failures",
                "move_distance_m",
            )
            if row.get(key) is None
        ]
        for row in results
    }
    missing_fields = {key: value for key, value in missing_fields.items() if value}
    summary = {
        "case_count": len(results),
        "full_discovery_cases": sum(
            row.get("actual_sources") is not None
            and row.get("discovered_sources") == row.get("actual_sources")
            for row in results
        ),
        "full_clear_cases": sum(
            row.get("actual_sources") is not None
            and row.get("cleared_sources") == row.get("actual_sources")
            for row in results
        ),
        "total_actual_sources": total_actual,
        "total_discovered_sources": total_discovered,
        "total_cleared_sources": total_cleared,
        "overall_discovery_rate": total_discovered / total_actual if total_actual else None,
        "overall_clear_rate": total_cleared / total_actual if total_actual else None,
        "virtual_time_s": numeric_stats(
            [row["virtual_time_s"] for row in results if row.get("virtual_time_s") is not None]
        ),
        "mean_clear_time_s": numeric_stats(
            [row["mean_clear_time_s"] for row in results if row.get("mean_clear_time_s") is not None]
        ),
        "failed_cases": [row["run_id"] for row in results if "FAIL_RECORDED" in row.get("notes", "")],
        "clear_failures": {
            row["run_id"]: row["clear_failures"]
            for row in results
            if row.get("clear_failures")
        },
        "crashes": [row["run_id"] for row in results if row.get("crashed")],
        "missing_fields": missing_fields,
        "runs": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    try:
        if args.summarize:
            return summarize()
        return run_case(args)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
