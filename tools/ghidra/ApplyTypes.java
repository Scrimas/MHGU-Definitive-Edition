// Applies a tools/ghidra_types.py list to the open program: struct rows (name, size) with their field rows (struct,
// offset, type, name or -, comment) become structures in the category /mhgu-de (one whose content differs is replaced
// in place); this rows (address, struct) put the function into the class namespace of that name with __thiscall, so
// the decompiler types r0 from the structure and keeps inferring the other parameters and the return type. A function
// in another namespace and a thunk are left alone; one an earlier list typed and this one does not goes back to the
// global namespace. Every skip is reported.
// @category MHGU-DE
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class ApplyTypes extends GhidraScript {
    static final CategoryPath CAT = new CategoryPath("/mhgu-de");

    DataType type(String t, Map<String, StructureDataType> built) throws IOException {
        if (t.startsWith("ptr:")) return new PointerDataType(built.get(t.substring(4)));
        if (t.startsWith("undef")) return Undefined.getUndefinedDataType(Integer.parseInt(t.substring(5)));
        switch (t) {
            case "u8": return UnsignedCharDataType.dataType;
            case "s8": return SignedCharDataType.dataType;
            case "u16": return UnsignedShortDataType.dataType;
            case "s16": return ShortDataType.dataType;
            case "u32": return UnsignedIntegerDataType.dataType;
            case "s32": return IntegerDataType.dataType;
            case "f32": return FloatDataType.dataType;
            case "u64": return UnsignedLongLongDataType.dataType;
            case "f64": return DoubleDataType.dataType;
            case "ptr": return PointerDataType.dataType;
        }
        throw new IOException("bad type: " + t);
    }

    // what a re-run compares: size, description and every defined field
    static String content(Structure s) {
        StringBuilder b = new StringBuilder(s.getLength() + "|" + s.getDescription());
        for (DataTypeComponent c : s.getDefinedComponents())
            b.append("\n").append(c.getOffset()).append("|").append(c.getDataType().getPathName()).append("|")
             .append(c.getFieldName()).append("|").append(c.getComment());
        return b.toString();
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<String> rows = Files.readAllLines(Paths.get(args[0]), StandardCharsets.UTF_8);
        List<String> out = new ArrayList<>();
        Map<String, Integer> n = new TreeMap<>();
        DataTypeManager dtm = currentProgram.getDataTypeManager();
        SymbolTable st = currentProgram.getSymbolTable();
        Map<String, StructureDataType> built = new LinkedHashMap<>();
        for (String row : rows) {
            String[] c = row.split("\t", -1);
            if (c[0].equals("struct")) {
                StructureDataType s = new StructureDataType(CAT, c[1], Integer.decode(c[2]), dtm);
                s.setDescription(c[3]);
                built.put(c[1], s);
            } else if (c[0].equals("field")) {
                DataType dt = type(c[3], built);
                built.get(c[1]).replaceAtOffset(Integer.decode(c[2]), dt, dt.getLength(), c[4].equals("-") ? null : c[4], c[5]);
            } else if (!c[0].equals("this")) throw new IOException("bad row: " + row);
        }
        for (StructureDataType s : built.values()) {     // file order: the views the objects point to come first
            DataType old = dtm.getDataType(CAT, s.getName());
            String r;
            if (old instanceof Structure && content((Structure) old).equals(content(s))) r = "struct-already";
            else { dtm.addDataType(s, DataTypeConflictHandler.REPLACE_HANDLER); r = old == null ? "struct-created" : "struct-replaced"; }
            n.merge(r, 1, Integer::sum);
        }
        Set<String> listed = new HashSet<>();
        for (String row : rows) {
            String[] c = row.split("\t", -1);
            if (c[0].equals("this")) listed.add(toAddr(Long.decode(c[1])) + "\t" + c[2]);
        }
        for (String name : built.keySet()) {
            Namespace ns = st.getNamespace(name, null);
            if (!(ns instanceof GhidraClass)) continue;
            List<Function> gone = new ArrayList<>();
            for (Symbol s : st.getSymbols(ns))
                if (s.getSymbolType() == SymbolType.FUNCTION && !listed.contains(s.getAddress() + "\t" + name))
                    gone.add((Function) s.getObject());
            for (Function f : gone) {
                f.setParentNamespace(currentProgram.getGlobalNamespace());
                f.setCallingConvention(Function.UNKNOWN_CALLING_CONVENTION_STRING);
            }
            if (!gone.isEmpty()) n.merge("this-untyped", gone.size(), Integer::sum);
        }
        for (String row : rows) {
            String[] c = row.split("\t", -1);
            if (!c[0].equals("this")) continue;
            Function f = getFunctionAt(toAddr(Long.decode(c[1])));
            String r;
            Namespace ns = st.getNamespace(c[2], null);
            if (f == null) r = "skip-no-function";
            else if (f.isThunk()) r = "skip-thunk";      // its decompilation is the thunked function's
            else if (ns != null && !(ns instanceof GhidraClass)) r = "skip-not-a-class:" + c[2];
            else if (f.getParentNamespace().equals(ns) && "__thiscall".equals(f.getCallingConventionName())) r = "this-already";
            else if (!f.getParentNamespace().isGlobal() && !built.containsKey(f.getParentNamespace().getName()))
                r = "skip-namespace:" + f.getParentNamespace().getName(true);
            else {
                r = "this-typed";
                if (ns == null) ns = st.createClass(null, c[2], SourceType.USER_DEFINED);
                f.setParentNamespace(ns);
                f.setCallingConvention("__thiscall");
            }
            String key = r.contains(":") ? r.substring(0, r.indexOf(':')) : r;
            n.merge(key, 1, Integer::sum);
            if (r.startsWith("skip")) out.add(r + "\t" + row);
        }
        out.add(0, "applied " + rows.size() + " rows: " + n);
        Files.write(Paths.get(args[1]), out, StandardCharsets.UTF_8);
    }
}
