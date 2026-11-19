// Applies a tools/ghidra_names.py list (kind TAB address TAB text TAB source) to the open program.
// entry: creates a function there when none starts there (vtable slot targets, tail-called constructors);
// func: renames the function that starts at the address, only while it has a Ghidra name (FUN_..., default);
// label: adds a non-primary label; comment: appends a line to the pre comment. Every skip is reported.
// @category MHGU-DE
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class ApplyNames extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<String> rows = Files.readAllLines(Paths.get(args[0]), StandardCharsets.UTF_8);
        List<String> out = new ArrayList<>();
        Map<String, Integer> n = new TreeMap<>();
        SymbolTable st = currentProgram.getSymbolTable();
        Listing li = currentProgram.getListing();
        for (String row : rows) {
            String[] c = row.split("\t", -1);
            if (c.length < 4) throw new IOException("bad row: " + row);
            Address a = toAddr(Long.decode(c[1]));
            String r;
            if (!currentProgram.getMemory().contains(a)) r = "skip-unmapped";
            else if (c[0].equals("entry")) {
                if (getFunctionAt(a) != null) r = "entry-exists";
                else r = createFunction(a, null) != null ? "entry-created" : "skip-entry-failed";
            } else if (c[0].equals("func")) {
                Function f = getFunctionAt(a);
                Symbol s = f == null ? null : f.getSymbol();
                if (f == null) r = "skip-no-function";
                else if (f.getName().equals(c[2])) r = "func-already";
                else if (s.getSource() != SourceType.DEFAULT && !(s.getSource() == SourceType.ANALYSIS
                         && f.getName().matches("default|(caseD|switchD|LAB|FUN|thunk_FUN)_\\w+")))
                    r = "skip-named:" + f.getName();
                else { f.setName(c[2], SourceType.USER_DEFINED); r = "func-renamed"; }
            } else if (c[0].equals("label")) {
                boolean have = false;
                for (Symbol s : st.getSymbols(a)) have |= s.getName().equals(c[2]);
                if (have) r = "label-already";
                else { st.createLabel(a, c[2], SourceType.USER_DEFINED); r = "label-added"; }
            } else if (c[0].equals("comment")) {
                String old = li.getComment(CommentType.PRE, a);
                if (old != null && Arrays.asList(old.split("\n")).contains(c[2])) r = "comment-already";
                else { li.setComment(a, CommentType.PRE, old == null ? c[2] : old + "\n" + c[2]); r = "comment-added"; }
            } else throw new IOException("bad kind: " + row);
            String key = r.contains(":") ? r.substring(0, r.indexOf(':')) : r;
            n.merge(key, 1, Integer::sum);
            if (r.startsWith("skip")) out.add(r + "\t" + row);
        }
        out.add(0, "applied " + rows.size() + " rows: " + n);
        Files.write(Paths.get(args[1]), out, StandardCharsets.UTF_8);
    }
}
