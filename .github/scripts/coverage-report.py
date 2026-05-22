#!/usr/bin/env python3
"""Render a consolidated coverage comment for the PR from jacoco.xml + git diff.

Two-level coverage check:
  - THRESHOLD_* values gate the build (PR fails if below).
  - TARGET_OVERALL is informational, shown next to the actual % so reviewers
    see how far the project is from the lineamiento (e.g., 90%) without
    blocking merges. Lets repos with low historical coverage migrate gradually.

Outputs:
  - coverage-comment.md (markdown for the sticky PR comment)
  - GITHUB_OUTPUT entries: overall_pct, patch_pct, passed
"""
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

JACOCO_XML = Path(os.environ.get("JACOCO_XML", "target/site/jacoco/jacoco.xml"))
BASE_REF = os.environ.get("BASE_REF", "origin/HEAD")
THRESHOLD_OVERALL = float(os.environ.get("THRESHOLD_OVERALL", "0"))
THRESHOLD_PATCH = float(os.environ.get("THRESHOLD_PATCH", "90"))
TARGET_OVERALL = float(os.environ.get("TARGET_OVERALL", "90"))
REPO = os.environ.get("GITHUB_REPOSITORY", "")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
SOURCE_ROOT = os.environ.get("SOURCE_ROOT", "src/main/java")


def parse_jacoco():
    tree = ET.parse(JACOCO_XML)
    root = tree.getroot()
    total_missed = total_covered = 0
    for c in root.findall("counter"):
        if c.get("type") == "LINE":
            total_missed = int(c.get("missed", 0))
            total_covered = int(c.get("covered", 0))
    total = total_missed + total_covered
    overall_pct = (100.0 * total_covered / total) if total else 0.0

    # Key by package + filename (no source-root prefix) so we can match
    # changed files from either src/main/java/... or src/main/kotlin/...
    file_lines = {}
    for pkg in root.findall("package"):
        pkg_name = pkg.get("name")
        for sf in pkg.findall("sourcefile"):
            key = f"{pkg_name}/{sf.get('name')}"
            lines = {}
            for ln in sf.findall("line"):
                nr = int(ln.get("nr"))
                missed = int(ln.get("mi", 0))
                covered = int(ln.get("ci", 0))
                if missed == 0 and covered == 0:
                    continue
                lines[nr] = covered > 0
            file_lines[key] = lines
    return overall_pct, file_lines


SOURCE_PREFIXES = ("src/main/java/", "src/main/kotlin/")


def strip_source_root(path: str) -> str:
    for prefix in SOURCE_PREFIXES:
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def changed_lines_per_file():
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", f"{BASE_REF}...HEAD", "--", "*.java", "*.kt"],
        text=True,
    )
    result, current = {}, None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            result[current] = set()
        elif line.startswith("@@") and current is not None:
            for token in line.split():
                if token.startswith("+"):
                    parts = token[1:].split(",")
                    start = int(parts[0])
                    count = int(parts[1]) if len(parts) > 1 else 1
                    if count > 0:
                        result[current].update(range(start, start + count))
                    break
    return {k: v for k, v in result.items() if v}


def shorten(path: str) -> str:
    parts = path.split("/")
    return ".../" + "/".join(parts[-3:]) if len(parts) > 3 else path


def fmt_ranges(nums):
    nums = sorted(nums)
    if not nums:
        return ""
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append((start, prev))
        start = prev = n
    out.append((start, prev))
    return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in out)


def main():
    if not JACOCO_XML.exists():
        print(f"::warning::{JACOCO_XML} not found")
        Path("coverage-comment.md").write_text(
            "## 📊 Coverage Report\n\n⚠️ `jacoco.xml` not generated — check the build step.\n"
        )
        write_output(overall=0, patch=None, passed=False)
        return

    overall_pct, file_lines = parse_jacoco()
    changed = changed_lines_per_file()

    rows, total_track, total_cov = [], 0, 0
    for path, lines in changed.items():
        key = strip_source_root(path)
        cov = file_lines.get(key)
        if cov is None:
            for k, v in file_lines.items():
                if k.endswith(key) or key.endswith(k):
                    cov = v
                    break
        if not cov:
            continue
        trackable = lines & cov.keys()
        if not trackable:
            continue
        covered_lines = {ln for ln in trackable if cov[ln]}
        missed = sorted(trackable - covered_lines)
        pct = 100.0 * len(covered_lines) / len(trackable)
        rows.append((path, pct, missed, len(trackable)))
        total_track += len(trackable)
        total_cov += len(covered_lines)

    patch_pct = (100.0 * total_cov / total_track) if total_track else None

    md = ["## 📊 Coverage Report", ""]

    if patch_pct is None:
        md.append("ℹ️ No Java lines changed in this PR — patch coverage not applicable.")
    else:
        patch_emoji = "✅" if patch_pct >= THRESHOLD_PATCH else "❌"
        missing = total_track - total_cov
        md.append(
            f"{patch_emoji} **Patch coverage: {patch_pct:.2f}%** "
            f"(threshold: {THRESHOLD_PATCH:.0f}%) — "
            f"{missing} of {total_track} changed lines missing coverage."
        )

    # Two-level overall: target (informational) + threshold (gating)
    target_emoji = "✅" if overall_pct >= TARGET_OVERALL else "❌"
    if THRESHOLD_OVERALL > 0:
        gate_emoji = "✅" if overall_pct >= THRESHOLD_OVERALL else "❌"
        md.append(
            f"**Project coverage:** {overall_pct:.2f}% "
            f"(target: {TARGET_OVERALL:.0f}% {target_emoji}, gating: ≥{THRESHOLD_OVERALL:.0f}% {gate_emoji})"
        )
    else:
        md.append(
            f"**Project coverage:** {overall_pct:.2f}% "
            f"(target: {TARGET_OVERALL:.0f}% {target_emoji}, gating disabled)"
        )
    md.append("")

    if rows:
        md.append("| File | Patch % | Missing | Lines |")
        md.append("|---|---:|---:|---|")
        for path, pct, missed, _ in sorted(rows, key=lambda r: r[1]):
            md.append(f"| `{shorten(path)}` | {pct:.2f}% | {len(missed)} | {fmt_ranges(missed)} |")
        md.append("")

    if REPO and RUN_ID:
        md.append(f"🔍 [Workflow run](https://github.com/{REPO}/actions/runs/{RUN_ID})")

    output = "\n".join(md) + "\n"
    Path("coverage-comment.md").write_text(output)
    print(output)

    passed = overall_pct >= THRESHOLD_OVERALL and (
        patch_pct is None or patch_pct >= THRESHOLD_PATCH
    )
    write_output(overall=overall_pct, patch=patch_pct, passed=passed)


def write_output(overall, patch, passed):
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if not gh_out:
        return
    patch_str = "NA" if patch is None else f"{patch:.2f}"
    with open(gh_out, "a") as f:
        f.write(f"overall_pct={overall:.2f}\n")
        f.write(f"patch_pct={patch_str}\n")
        f.write(f"passed={'true' if passed else 'false'}\n")


if __name__ == "__main__":
    main()
