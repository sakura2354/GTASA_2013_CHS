//@category REA
// Disassemble an address range with Ghidra's own decoder.
// Args: <outFile> <hexStart> <hexEnd>
// NOTE: Ghidra's image base for this artifact is ELF + 0x10000.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Listing;
import java.io.File;
import java.io.PrintWriter;

public class Disasm extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] av = getScriptArgs();
        File out = new File(av[0]);
        long start = Long.parseLong(av[1].startsWith("0x") ? av[1].substring(2) : av[1], 16);
        long end = Long.parseLong(av[2].startsWith("0x") ? av[2].substring(2) : av[2], 16);

        Listing listing = currentProgram.getListing();
        Address a = toAddr(start);
        Address stop = toAddr(end);

        PrintWriter pw = new PrintWriter(out, "UTF-8");
        int n = 0;
        while (a.compareTo(stop) < 0) {
            Instruction ins;
            try {
                ins = listing.getInstructionAt(a);
            } catch (Exception e) {
                ins = null;
            }
            if (ins == null) {
                // try to disassemble on the fly (returns boolean in this release)
                try {
                    disassemble(a);
                    ins = listing.getInstructionAt(a);
                } catch (Exception e) {
                    ins = null;
                }
                if (ins == null) {
                    pw.println(String.format("%08X  <cannot decode>", a.getOffset()));
                    a = a.add(2);
                    continue;
                }
            }
            StringBuilder hex = new StringBuilder();
            byte[] bytes = ins.getBytes();
            for (byte b : bytes) {
                hex.append(String.format("%02x ", b & 0xFF));
            }
            pw.println(String.format("%08X  %-20s %s",
                    ins.getAddress().getOffset(), hex.toString().trim(),
                    ins.toString()));
            n++;
            a = ins.getAddress().add(ins.getLength());
        }
        pw.close();
        println("disassembled " + n + " instructions -> " + out);
    }
}
