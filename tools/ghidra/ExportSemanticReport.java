/* ============================================================================
 * ExportSemanticReport.java — Ghidra headless export script
 * ============================================================================
 *
 * Produces a JSON semantic report from any analyzed binary containing:
 *   - Port I/O operations (IN/OUT instructions with port identification)
 *   - Hardware functions (functions containing port I/O)
 *   - Import classification (PORT_IO, SCAFFOLDING, OTHER)
 *   - Scaffolding functions (no port I/O)
 *
 * Usage (headless):
 *   analyzeHeadless <project_dir> <project_name> \
 *     -import <binary> \
 *     -postScript ExportSemanticReport.java <output.json> \
 *     -scriptPath /path/to/this/dir
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.mem.MemoryAccessException;

import java.io.File;
import java.io.FileWriter;
import java.io.FileInputStream;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ExportSemanticReport extends GhidraScript {

    /* ---- Import classification tables ---- */

    private static final String[] PORT_IO_IMPORTS = {
        "READ_PORT_UCHAR", "READ_PORT_USHORT", "READ_PORT_ULONG",
        "WRITE_PORT_UCHAR", "WRITE_PORT_USHORT", "WRITE_PORT_ULONG",
        "READ_PORT_BUFFER_UCHAR", "READ_PORT_BUFFER_USHORT", "READ_PORT_BUFFER_ULONG",
        "WRITE_PORT_BUFFER_UCHAR", "WRITE_PORT_BUFFER_USHORT", "WRITE_PORT_BUFFER_ULONG"
    };

    private static final String[] SCAFFOLDING_IMPORTS = {
        "IoCompleteRequest", "IoCreateDevice", "IoDeleteDevice",
        "IoCreateSymbolicLink", "IoDeleteSymbolicLink",
        "IofCompleteRequest", "IofCallDriver",
        "IoAttachDeviceToDeviceStack", "IoDetachDevice",
        "IoGetDeviceObjectPointer",
        "KeInitializeEvent", "KeSetEvent", "KeWaitForSingleObject",
        "KeInitializeSpinLock", "KeAcquireSpinLock", "KeReleaseSpinLock",
        "ExAllocatePool", "ExAllocatePoolWithTag", "ExFreePool", "ExFreePoolWithTag",
        "RtlInitUnicodeString", "RtlCopyUnicodeString",
        "DbgPrint", "KdPrint",
        "ObReferenceObject", "ObDereferenceObject",
        "ZwClose", "ZwCreateFile", "ZwReadFile", "ZwWriteFile",
        "PoCallDriver", "PoStartNextPowerIrp", "PoSetPowerState"
    };

    /* ---- Port I/O operation record ---- */

    private static class PortOp {
        String address;
        String port;
        String direction;
        String width;
        String function;

        PortOp(String address, String port, String direction, String width, String function) {
            this.address = address;
            this.port = port;
            this.direction = direction;
            this.width = width;
            this.function = function;
        }
    }

    /* ---- Hardware function record ---- */

    private static class HwFunc {
        String name;
        String address;
        long size;
        Set<String> portsAccessed;

        HwFunc(String name, String address, long size) {
            this.name = name;
            this.address = address;
            this.size = size;
            this.portsAccessed = new HashSet<>();
        }
    }

    /* ---- Import record ---- */

    private static class ImportRec {
        String dll;
        String function;
        String category;

        ImportRec(String dll, String function, String category) {
            this.dll = dll;
            this.function = function;
            this.category = category;
        }
    }

    /* ---- Scaffolding function record ---- */

    private static class ScaffoldFunc {
        String name;
        String address;
        String reason;

        ScaffoldFunc(String name, String address, String reason) {
            this.name = name;
            this.address = address;
            this.reason = reason;
        }
    }

    @Override
    public void run() throws Exception {
        /* Get output path from script arguments */
        String[] args = getScriptArgs();
        if (args.length < 1) {
            printerr("Usage: ExportSemanticReport.java <output_json_path>");
            return;
        }
        String outputPath = args[0];

        println("ExportSemanticReport: starting analysis...");

        /* ---- Collect binary metadata ---- */
        String filename = new File(currentProgram.getExecutablePath()).getName();
        String format = currentProgram.getExecutableFormat();
        String machine = currentProgram.getLanguage().getProcessor().toString();
        String imageBase = formatAddress(currentProgram.getImageBase());

        /* Normalize format string */
        if (format != null && format.toLowerCase().contains("pe")) {
            /* Check if PE32 or PE32+ based on pointer size */
            int pointerSize = currentProgram.getDefaultPointerSize();
            format = (pointerSize <= 4) ? "PE32" : "PE32+";
        }

        /* Compute SHA-256 */
        String sha256 = computeSHA256(currentProgram.getExecutablePath());

        /* ---- Scan functions for port I/O ---- */
        List<PortOp> portOps = new ArrayList<>();
        List<HwFunc> hwFuncs = new ArrayList<>();
        List<ScaffoldFunc> scaffoldFuncs = new ArrayList<>();

        FunctionManager funcMgr = currentProgram.getFunctionManager();
        FunctionIterator funcIter = funcMgr.getFunctions(true);

        while (funcIter.hasNext()) {
            Function func = funcIter.next();
            String funcName = func.getName();
            Address entryAddr = func.getEntryPoint();
            AddressSetView body = func.getBody();
            long funcSize = body.getNumAddresses();

            List<PortOp> funcPortOps = new ArrayList<>();
            Set<String> funcPorts = new HashSet<>();

            /* Walk instructions in function body */
            InstructionIterator instIter =
                currentProgram.getListing().getInstructions(body, true);

            while (instIter.hasNext()) {
                Instruction inst = instIter.next();
                byte[] bytes;
                try {
                    bytes = inst.getBytes();
                } catch (MemoryAccessException e) {
                    continue;
                }

                if (bytes.length < 1) continue;
                int opcode = bytes[0] & 0xFF;

                String direction = null;
                String width = null;
                String port = null;

                switch (opcode) {
                    case 0xE4: /* IN AL, imm8 */
                        direction = "read"; width = "byte";
                        port = (bytes.length >= 2) ?
                            formatHexByte(bytes[1] & 0xFF) : "unknown";
                        break;
                    case 0xE5: /* IN EAX, imm8 */
                        direction = "read"; width = "dword";
                        port = (bytes.length >= 2) ?
                            formatHexByte(bytes[1] & 0xFF) : "unknown";
                        break;
                    case 0xE6: /* OUT imm8, AL */
                        direction = "write"; width = "byte";
                        port = (bytes.length >= 2) ?
                            formatHexByte(bytes[1] & 0xFF) : "unknown";
                        break;
                    case 0xE7: /* OUT imm8, EAX */
                        direction = "write"; width = "dword";
                        port = (bytes.length >= 2) ?
                            formatHexByte(bytes[1] & 0xFF) : "unknown";
                        break;
                    case 0xEC: /* IN AL, DX */
                        direction = "read"; width = "byte"; port = "DX";
                        break;
                    case 0xED: /* IN EAX, DX */
                        direction = "read"; width = "dword"; port = "DX";
                        break;
                    case 0xEE: /* OUT DX, AL */
                        direction = "write"; width = "byte"; port = "DX";
                        break;
                    case 0xEF: /* OUT DX, EAX */
                        direction = "write"; width = "dword"; port = "DX";
                        break;
                    default:
                        break;
                }

                if (direction != null) {
                    String instAddr = formatAddress(inst.getAddress());
                    funcPortOps.add(new PortOp(instAddr, port, direction, width, funcName));
                    funcPorts.add(port);
                }
            }

            if (!funcPortOps.isEmpty()) {
                /* Hardware function */
                portOps.addAll(funcPortOps);
                HwFunc hw = new HwFunc(funcName,
                    formatAddress(entryAddr), funcSize);
                hw.portsAccessed = funcPorts;
                hwFuncs.add(hw);
            } else {
                /* Scaffolding function */
                scaffoldFuncs.add(new ScaffoldFunc(funcName,
                    formatAddress(entryAddr), "no port I/O operations"));
            }
        }

        /* ---- Collect imports ---- */
        List<ImportRec> imports = new ArrayList<>();
        SymbolTable symTab = currentProgram.getSymbolTable();
        SymbolIterator extSymIter = symTab.getExternalSymbols();

        while (extSymIter.hasNext()) {
            Symbol sym = extSymIter.next();
            if (sym.getSymbolType() != SymbolType.FUNCTION &&
                sym.getSymbolType() != SymbolType.LABEL) {
                continue;
            }

            String symName = sym.getName();
            String dll = "unknown";

            /* Get parent namespace to find DLL name */
            Namespace ns = sym.getParentNamespace();
            if (ns != null && !ns.isGlobal()) {
                dll = ns.getName();
            }

            String category = classifyImport(symName);
            imports.add(new ImportRec(dll, symName, category));
        }

        /* ---- Build JSON output ---- */
        StringBuilder json = new StringBuilder();
        json.append("{\n");

        /* Schema info */
        json.append("    \"schema_version\": 1,\n");
        json.append("    \"generator\": \"ghidra\",\n");
        json.append("    \"ghidra_version\": \"");
        json.append(ghidra.framework.Application.getApplicationVersion());
        json.append("\",\n");

        /* Binary info */
        json.append("    \"binary\": {\n");
        json.append("        \"filename\": ").append(jsonString(filename)).append(",\n");
        json.append("        \"sha256\": ").append(jsonString(sha256)).append(",\n");
        json.append("        \"format\": ").append(jsonString(format)).append(",\n");
        json.append("        \"machine\": ").append(jsonString(machine)).append(",\n");
        json.append("        \"image_base\": ").append(jsonString(imageBase)).append("\n");
        json.append("    },\n");

        /* Port operations */
        json.append("    \"port_operations\": [\n");
        for (int i = 0; i < portOps.size(); i++) {
            PortOp op = portOps.get(i);
            json.append("        {\n");
            json.append("            \"address\": ").append(jsonString(op.address)).append(",\n");
            json.append("            \"port\": ").append(jsonString(op.port)).append(",\n");
            json.append("            \"direction\": ").append(jsonString(op.direction)).append(",\n");
            json.append("            \"width\": ").append(jsonString(op.width)).append(",\n");
            json.append("            \"function\": ").append(jsonString(op.function)).append("\n");
            json.append("        }");
            if (i < portOps.size() - 1) json.append(",");
            json.append("\n");
        }
        json.append("    ],\n");

        /* Hardware functions */
        json.append("    \"hardware_functions\": [\n");
        for (int i = 0; i < hwFuncs.size(); i++) {
            HwFunc hw = hwFuncs.get(i);
            json.append("        {\n");
            json.append("            \"name\": ").append(jsonString(hw.name)).append(",\n");
            json.append("            \"address\": ").append(jsonString(hw.address)).append(",\n");
            json.append("            \"size\": ").append(hw.size).append(",\n");
            json.append("            \"ports_accessed\": [");
            List<String> sortedPorts = new ArrayList<>(hw.portsAccessed);
            java.util.Collections.sort(sortedPorts);
            for (int j = 0; j < sortedPorts.size(); j++) {
                if (j > 0) json.append(", ");
                json.append(jsonString(sortedPorts.get(j)));
            }
            json.append("],\n");
            json.append("            \"classification\": \"PORT_IO\"\n");
            json.append("        }");
            if (i < hwFuncs.size() - 1) json.append(",");
            json.append("\n");
        }
        json.append("    ],\n");

        /* Imports */
        json.append("    \"imports\": [\n");
        for (int i = 0; i < imports.size(); i++) {
            ImportRec imp = imports.get(i);
            json.append("        {\n");
            json.append("            \"dll\": ").append(jsonString(imp.dll)).append(",\n");
            json.append("            \"function\": ").append(jsonString(imp.function)).append(",\n");
            json.append("            \"category\": ").append(jsonString(imp.category)).append("\n");
            json.append("        }");
            if (i < imports.size() - 1) json.append(",");
            json.append("\n");
        }
        json.append("    ],\n");

        /* Scaffolding functions */
        json.append("    \"scaffolding_functions\": [\n");
        for (int i = 0; i < scaffoldFuncs.size(); i++) {
            ScaffoldFunc sf = scaffoldFuncs.get(i);
            json.append("        {\n");
            json.append("            \"name\": ").append(jsonString(sf.name)).append(",\n");
            json.append("            \"address\": ").append(jsonString(sf.address)).append(",\n");
            json.append("            \"reason\": ").append(jsonString(sf.reason)).append("\n");
            json.append("        }");
            if (i < scaffoldFuncs.size() - 1) json.append(",");
            json.append("\n");
        }
        json.append("    ]\n");

        json.append("}\n");

        /* ---- Write output ---- */
        File outFile = new File(outputPath);
        outFile.getParentFile().mkdirs();
        FileWriter writer = new FileWriter(outFile);
        writer.write(json.toString());
        writer.close();

        println("ExportSemanticReport: wrote " + outputPath);
        println("  Port operations: " + portOps.size());
        println("  Hardware functions: " + hwFuncs.size());
        println("  Imports: " + imports.size());
        println("  Scaffolding functions: " + scaffoldFuncs.size());
    }

    /* ---- Helper methods ---- */

    private String classifyImport(String name) {
        for (String s : PORT_IO_IMPORTS) {
            if (s.equals(name)) return "PORT_IO";
        }
        for (String s : SCAFFOLDING_IMPORTS) {
            if (s.equals(name)) return "SCAFFOLDING";
        }
        return "OTHER";
    }

    private String formatAddress(Address addr) {
        return "0x" + addr.toString().replaceAll("^0+", "");
    }

    private String formatHexByte(int val) {
        return "0x" + String.format("%02x", val).toUpperCase();
    }

    private String computeSHA256(String path) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            FileInputStream fis = new FileInputStream(new File(path));
            byte[] buffer = new byte[8192];
            int bytesRead;
            while ((bytesRead = fis.read(buffer)) != -1) {
                md.update(buffer, 0, bytesRead);
            }
            fis.close();
            byte[] digest = md.digest();
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) {
                sb.append(String.format("%02x", b & 0xFF));
            }
            return sb.toString();
        } catch (Exception e) {
            return "error: " + e.getMessage();
        }
    }

    /** Escape a string for JSON output */
    private String jsonString(String val) {
        if (val == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < val.length(); i++) {
            char c = val.charAt(i);
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                    break;
            }
        }
        sb.append("\"");
        return sb.toString();
    }
}
