"""Static analysis of Java sources via javac's parser (JavaAnalyzer)."""
import json, subprocess
from pathlib import Path

JAVA_DIR = Path(__file__).resolve().parent / "java"


def analyze(files):
    """Returns a list of method records for the given .java paths."""
    files = [str(f) for f in files]
    if not files:
        return []
    r = subprocess.run(["java", "-cp", str(JAVA_DIR), "JavaAnalyzer", *files],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"JavaAnalyzer failed: {r.stderr[:400]}")
    return json.loads(r.stdout)


def testable(methods):
    """Methods a unit test can meaningfully target.

    Excludes abstract declarations (no body) and `main`, which is an entry
    point rather than a unit of behaviour.
    """
    out = []
    for m in methods:
        if m["abstract"]:
            continue
        if m["name"] == "main" and m["static"]:
            continue
        out.append(m)
    return out
