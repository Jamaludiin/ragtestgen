import org.jacoco.core.analysis.*;
import org.jacoco.core.tools.ExecFileLoader;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/**
 * Batch coverage analysis. Given a directory of compiled classes under test and
 * a list of JaCoCo .exec files, emits one JSON object per exec file giving, for
 * each class, the set of covered line numbers plus instruction/branch/line
 * counters. Running every exec file in a single JVM keeps the per-test coverage
 * measurement tractable.
 *
 * Usage: java CoverageBatch <classesDir> <execFile>...
 */
public class CoverageBatch {

    static String esc(String s) { return s.replace("\\", "\\\\").replace("\"", "\\\""); }

    public static void main(String[] args) throws IOException {
        File classesDir = new File(args[0]);
        StringBuilder out = new StringBuilder("{\n");
        for (int i = 1; i < args.length; i++) {
            File exec = new File(args[i]);
            ExecFileLoader loader = new ExecFileLoader();
            if (exec.exists() && exec.length() > 0) {
                try { loader.load(exec); } catch (IOException e) { /* truncated dump */ }
            }
            CoverageBuilder builder = new CoverageBuilder();
            Analyzer analyzer = new Analyzer(loader.getExecutionDataStore(), builder);
            try { analyzer.analyzeAll(classesDir); } catch (IOException e) { /* ignore */ }

            if (i > 1) out.append(",\n");
            out.append("\"").append(esc(exec.getName())).append("\": {");
            boolean firstClass = true;
            int ic = 0, im = 0, bc = 0, bm = 0, lc = 0, lm = 0;
            StringBuilder classes = new StringBuilder();
            for (IClassCoverage c : builder.getClasses()) {
                ic += c.getInstructionCounter().getCoveredCount();
                im += c.getInstructionCounter().getMissedCount();
                bc += c.getBranchCounter().getCoveredCount();
                bm += c.getBranchCounter().getMissedCount();
                lc += c.getLineCounter().getCoveredCount();
                lm += c.getLineCounter().getMissedCount();
                List<Integer> covered = new ArrayList<>();
                for (int ln = c.getFirstLine(); ln <= c.getLastLine() && ln > 0; ln++) {
                    if (c.getLine(ln).getStatus() == ICounter.FULLY_COVERED
                            || c.getLine(ln).getStatus() == ICounter.PARTLY_COVERED) {
                        covered.add(ln);
                    }
                }
                if (!firstClass) classes.append(",");
                firstClass = false;
                classes.append("\"").append(esc(c.getName())).append("\":").append(covered);
            }
            out.append("\"instr_covered\":").append(ic).append(",\"instr_missed\":").append(im)
               .append(",\"branch_covered\":").append(bc).append(",\"branch_missed\":").append(bm)
               .append(",\"line_covered\":").append(lc).append(",\"line_missed\":").append(lm)
               .append(",\"lines\":{").append(classes).append("}}");
        }
        out.append("\n}\n");
        System.out.print(out);
    }
}
