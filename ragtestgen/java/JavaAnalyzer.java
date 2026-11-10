import com.sun.source.tree.*;
import com.sun.source.util.*;
import javax.tools.*;
import java.io.*;
import java.util.*;

/**
 * Parses Java sources with javac's own parser and emits, as JSON, every method
 * and constructor declaration with its enclosing class, visibility, parameter
 * list, source span, cyclomatic complexity and body text.
 *
 * This replaces the regular-expression extractor of the original tool and
 * supplies the static complexity term used by the prioritization scheme.
 *
 * Usage: java JavaAnalyzer <file.java> [more.java ...]
 */
public class JavaAnalyzer {

    static String esc(String s) {
        StringBuilder b = new StringBuilder();
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"':  b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n");  break;
                case '\r': b.append("\\r");  break;
                case '\t': b.append("\\t");  break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.toString();
    }

    /** McCabe cyclomatic complexity: 1 + number of decision points. */
    static int complexity(MethodTree m) {
        final int[] n = {1};
        new TreeScanner<Void, Void>() {
            public Void visitIf(IfTree t, Void p)                    { n[0]++; return super.visitIf(t, p); }
            public Void visitWhileLoop(WhileLoopTree t, Void p)      { n[0]++; return super.visitWhileLoop(t, p); }
            public Void visitDoWhileLoop(DoWhileLoopTree t, Void p)  { n[0]++; return super.visitDoWhileLoop(t, p); }
            public Void visitForLoop(ForLoopTree t, Void p)          { n[0]++; return super.visitForLoop(t, p); }
            public Void visitEnhancedForLoop(EnhancedForLoopTree t, Void p) { n[0]++; return super.visitEnhancedForLoop(t, p); }
            public Void visitCase(CaseTree t, Void p)                { n[0]++; return super.visitCase(t, p); }
            public Void visitCatch(CatchTree t, Void p)              { n[0]++; return super.visitCatch(t, p); }
            public Void visitConditionalExpression(ConditionalExpressionTree t, Void p) { n[0]++; return super.visitConditionalExpression(t, p); }
            public Void visitBinary(BinaryTree t, Void p) {
                String k = t.getKind().toString();
                if (k.equals("CONDITIONAL_AND") || k.equals("CONDITIONAL_OR")) n[0]++;
                return super.visitBinary(t, p);
            }
        }.scan(m, null);
        return n[0];
    }

    static String visibility(ModifiersTree mods) {
        String s = mods.getFlags().toString();
        if (s.contains("private")) return "private";
        if (s.contains("protected")) return "protected";
        if (s.contains("public")) return "public";
        return "package";
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        StandardJavaFileManager fm = compiler.getStandardFileManager(null, null, null);
        List<File> files = new ArrayList<>();
        for (String a : args) files.add(new File(a));
        JavacTask task = (JavacTask) compiler.getTask(null, fm, d -> {},
                List.of("-proc:none"), null, fm.getJavaFileObjects(files.toArray(new File[0])));
        Iterable<? extends CompilationUnitTree> units = task.parse();
        SourcePositions pos = Trees.instance(task).getSourcePositions();

        StringBuilder out = new StringBuilder("[\n");
        boolean[] first = {true};
        for (CompilationUnitTree cu : units) {
            String path = cu.getSourceFile().getName();
            String text = cu.getSourceFile().getCharContent(true).toString();
            LineMap lines = cu.getLineMap();
            String pkg = cu.getPackageName() == null ? "" : cu.getPackageName().toString();
            new TreeScanner<Void, String>() {
                public Void visitClass(ClassTree c, String encl) {
                    String name = c.getSimpleName().toString();
                    return super.visitClass(c, name.isEmpty() ? encl : name);
                }
                public Void visitMethod(MethodTree m, String encl) {
                    long s = pos.getStartPosition(cu, m), e = pos.getEndPosition(cu, m);
                    if (s < 0 || e < 0 || e > text.length()) return super.visitMethod(m, encl);
                    String body = text.substring((int) s, (int) e);
                    String nm = m.getName().toString();
                    boolean ctor = nm.equals("<init>");
                    List<String> ptypes = new ArrayList<>();
                    for (VariableTree v : m.getParameters()) ptypes.add(v.getType().toString());
                    if (!first[0]) out.append(",\n");
                    first[0] = false;
                    out.append("{\"file\":\"").append(esc(path)).append("\"")
                       .append(",\"package\":\"").append(esc(pkg)).append("\"")
                       .append(",\"class\":\"").append(esc(encl == null ? "" : encl)).append("\"")
                       .append(",\"name\":\"").append(esc(ctor ? encl : nm)).append("\"")
                       .append(",\"constructor\":").append(ctor)
                       .append(",\"visibility\":\"").append(visibility(m.getModifiers())).append("\"")
                       .append(",\"static\":").append(m.getModifiers().getFlags().toString().contains("static"))
                       .append(",\"abstract\":").append(m.getBody() == null)
                       .append(",\"returnType\":\"").append(esc(m.getReturnType() == null ? "" : m.getReturnType().toString())).append("\"")
                       .append(",\"params\":[").append(String.join(",", ptypes.stream().map(x -> "\"" + esc(x) + "\"").toList())).append("]")
                       .append(",\"startLine\":").append(lines.getLineNumber(s))
                       .append(",\"endLine\":").append(lines.getLineNumber(e))
                       .append(",\"complexity\":").append(complexity(m))
                       .append(",\"body\":\"").append(esc(body)).append("\"}");
                    return super.visitMethod(m, encl);
                }
            }.scan(cu, null);
        }
        out.append("\n]\n");
        System.out.print(out);
    }
}
