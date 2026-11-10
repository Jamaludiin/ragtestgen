"""Compile, execute and measure JUnit test suites."""
import json, os, re, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib"
JAVA_DIR = Path(__file__).resolve().parent / "java"

CONSOLE = LIB / "junit-platform-console-standalone-1.10.2.jar"
AGENT = LIB / "jacocoagent.jar"
CLI = LIB / "jacococli.jar"
JUNIT4 = LIB / "junit-4.13.2.jar"
HAMCREST = LIB / "hamcrest-core-1.3.jar"
VINTAGE = LIB / "junit-vintage-engine-5.10.2.jar"

COV_CP = ":".join(str(LIB / j) for j in [
    "org.jacoco.core-0.8.12.jar", "org.jacoco.report-0.8.12.jar", "asm-9.7.jar",
    "asm-commons-9.7.jar", "asm-tree-9.7.jar", "asm-analysis-9.7.jar"])

TEST_TIMEOUT = int(os.environ.get("RTG_TEST_TIMEOUT", "40"))
COMPILE_TIMEOUT = 180

HEADER = """{package_line}
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import static org.junit.jupiter.api.Assertions.*;
import java.lang.reflect.*;
import java.util.*;

public class {cls} {{
{body}
}}
"""


def _sanitize(s):
    return re.sub(r"\W+", "_", s).strip("_")


def assemble(package, cls, tests):
    pkg = f"package {package};" if package else ""
    body = "\n\n".join(
        "    // [{id}] {cat}: {desc}\n{code}".format(
            id=t["id"], cat=t["category"], desc=t["description"].replace("\n", " ")[:110],
            code="\n".join("    " + l for l in t["code"].splitlines()))
        for t in tests)
    return HEADER.format(package_line=pkg, cls=cls, body=body)


def _javac(files, out_dir, classpath, timeout=COMPILE_TIMEOUT):
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["javac", "-nowarn", "-encoding", "UTF-8", "-proc:none",
           "-cp", classpath, "-d", str(out_dir), *[str(f) for f in files]]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def compile_suite(work, package, cls_base, tests, prog_classes):
    """Compile the suite, dropping individual tests that do not compile.

    Returns (kept_tests, dropped, test_classes_dir, compile_log).
    """
    tdir = work / "testsrc"
    cdir = work / "testclasses"
    for d in (tdir, cdir):
        if d.exists():
            shutil.rmtree(d)
    tdir.mkdir(parents=True); cdir.mkdir(parents=True)
    cp = f"{prog_classes}:{CONSOLE}"
    pkg_path = tdir / Path(*package.split(".")) if package else tdir

    def write(name, ts):
        pkg_path.mkdir(parents=True, exist_ok=True)
        f = pkg_path / f"{name}.java"
        f.write_text(assemble(package, name, ts))
        return f

    # 1) try the whole suite in one class
    whole = write(cls_base, tests)
    r = _javac([whole], cdir, cp)
    if r.returncode == 0:
        return tests, [], cdir, "combined compile OK"

    # 2) compile each test on its own to find which ones are viable
    shutil.rmtree(cdir); cdir.mkdir()
    files, owner = [], {}
    for t in tests:
        n = f"{cls_base}_{t['id']}"
        files.append(write(n, [t]))
        owner[n] = t
    _javac(files, cdir, cp)
    kept = [owner[n] for n in owner
            if (cdir / (Path(*package.split(".")) if package else Path("."))
                / f"{n}.class").exists()]
    kept.sort(key=lambda t: t["id"])
    dropped = [t["id"] for t in tests if t not in kept]

    # 3) recombine the survivors so every test lives in one class
    shutil.rmtree(cdir); cdir.mkdir()
    for f in list(tdir.rglob("*.java")):
        f.unlink()
    if not kept:
        return [], dropped, cdir, r.stderr[:4000]
    whole = write(cls_base, kept)
    r2 = _javac([whole], cdir, cp)
    if r2.returncode != 0:
        return [], [t["id"] for t in tests], cdir, r2.stderr[:4000]
    return kept, dropped, cdir, f"per-test compile; dropped {len(dropped)}"


def run_tests(fqcn, tests, prog_classes, test_classes, exec_dir, junit4=False):
    """Run each test method in its own JVM under the JaCoCo agent."""
    exec_dir.mkdir(parents=True, exist_ok=True)
    cp = f"{prog_classes}:{test_classes}"
    if junit4:
        cp += f":{JUNIT4}:{HAMCREST}:{VINTAGE}"
    results = []
    for t in tests:
        exec_f = exec_dir / f"t{t['id']}.exec"
        cmd = ["java", f"-javaagent:{AGENT}=destfile={exec_f},dumponexit=true,append=false",
               "-Djava.awt.headless=true", "-Duser.language=en",
               "-jar", str(CONSOLE), "--class-path", cp,
               "--select-method", f"{fqcn}#{t['test_name']}",
               "--details=none", "--disable-banner", "--disable-ansi-colors"]
        status, out = "error", ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=TEST_TIMEOUT, stdin=subprocess.DEVNULL)
            out = (p.stdout + p.stderr)[-1500:]
            status = "pass" if p.returncode == 0 else "fail"
        except subprocess.TimeoutExpired:
            status = "timeout"
        results.append({**t, "status": status, "exec": exec_f.name, "output": out})
    return results


def coverage(prog_classes, exec_files):
    """Per-exec-file coverage via a single JVM."""
    if not exec_files:
        return {}
    cmd = ["java", "-cp", f"{JAVA_DIR}:{COV_CP}", "CoverageBatch",
           str(prog_classes), *[str(f) for f in exec_files]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"CoverageBatch failed: {r.stderr[:400]}")
    return json.loads(r.stdout)


def merge_exec(exec_files, out_file):
    live = [str(f) for f in exec_files if Path(f).exists() and Path(f).stat().st_size > 0]
    if not live:
        return None
    r = subprocess.run(["java", "-jar", str(CLI), "merge", *live, "--destfile", str(out_file)],
                       capture_output=True, text=True, timeout=300)
    return out_file if r.returncode == 0 else None
