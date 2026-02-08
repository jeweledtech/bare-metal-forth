Project Memory:

Purpose & context
Jolly Genius Inc (jeweledtech on GitHub) is developing two interconnected systems: Bare-Metal Forth, a bare-metal Forth-83 operating system designed for space missions and critical systems, and a Universal Binary Translator for cross-platform executable analysis and translation. The project philosophy centers on the "ship builder's mindset" - prioritizing radical simplicity, reliability, and outcome-based engineering over convenience features. The OS is conceptualized as ship's systems software for long-duration space missions, emphasizing zero external dependencies and direct hardware control.
The target collaborators are professionals with backgrounds in space sciences, physics, embedded systems, and critical infrastructure - people willing to commit to serious, long-term technical work rather than casual contributors. Success is measured by creating production-quality systems that can operate independently without underlying OS layers or external dependencies.

Current state (as of 2026-02-07)
The Bare-Metal Forth system is FULLY FUNCTIONAL and boots in QEMU. All 34 automated tests pass. The system has been pushed to https://github.com/jeweledtech/bare-metal-forth (2 commits on master branch).

Build: `make clean && make` produces bmforth.img (512-byte bootloader + 32KB kernel = 33280 bytes).
Test: `qemu-system-i386 -drive file=build/bmforth.img,format=raw,if=floppy -serial tcp::4444,server=on,wait=off -display none` then connect to TCP port 4444 for serial console.

Working features (verified by tests):
- 88+ dictionary words including all core stack ops, arithmetic, logic, memory access
- Forth-83 floored division semantics (all sign combinations verified)
- Word definitions with : and ; (simple and nested: SQUARE, CUBE, QUADRUPLE)
- IF/ELSE/THEN control flow
- DO...LOOP with I index access (counted loops, nested loops)
- CONSTANT and VARIABLE defining words
- BASE/STATE accessible from Forth code (BASE @ ., STATE @ .)
- .S displays stack bottom-to-top (Forth convention)
- Serial I/O (COM1 0x3F8) for QEMU -nographic testing
- VGA text mode output (0xB8000) for bare-metal display
- Ctrl+C break handler with full state save/restore (ESP, EBP, STATE, HERE, LATEST)
- SP@ and SP! diagnostic words for stack pointer inspection
- WORDS lists all dictionary entries
- SEE decompiles words

Architecture details:
- Register usage: ESI = Instruction Pointer (IP), EBP = Return Stack, ESP = Data Stack, EAX = working/TOS
- NEXT macro: lodsd; jmp [eax] (Direct Threaded Code)
- Memory map: kernel at 0x7E00, data stack at 0x10000, return stack at 0x20000, dictionary at 0x30000, system vars at 0x28000, TIB at 0x28100, VGA at 0xB8000
- DEFCODE/DEFWORD/DEFVAR/DEFCONST macros build dictionary entries
- cold_start loop: INTERPRET, BRANCH, -8 (infinite interpreter loop)

Universal Binary Translator status: tools/translator has CLI skeleton (compiles, links). Decoders/loaders/codegen are stubs. tools/floored-division has complete 3-arch codegen with tests. tools/driver-extract has 100+ Windows API mappings framework.

Key bugs fixed in latest session (11 bugs total):
1. word_ TOIN off-by-one: lodsb advanced ESI past NUL terminator in TIB buffer, causing reads of stale data from previous commands. Fix: dec esi in .end_word.
2. /MOD floored division: checked quotient sign (eax) instead of remainder sign (edx) against divisor. Only failed when dividend positive, divisor negative.
3. ELSE compilation: xchg trick left BRANCH instruction address instead of offset address on stack for THEN to patch. Rewrote with clean pop/push.
4. DO/LOOP/+LOOP compiled code_XXX (native code address) instead of XXX (XT/code field address). NEXT needs double indirection: lodsd gets XT, jmp [eax] reads code field.
5. LOOP reserved an uninitialized 4-byte cell after the backward offset, putting garbage between loop and EXIT. Removed spurious add HERE, 4.
6. DOCON used lodsd (reads ESI = instruction stream) instead of [eax+4] (reads parameter field via XT). Constants returned wrong values.
7. S" and ." overwrote DOSQUOTE XT with string length. Fixed by reserving a length cell between XT and string data.
8. DEFVAR created private storage (var_STATE etc.) but kernel used EQU addresses (VAR_STATE = 0x28000). Forth code and kernel read different locations. Fixed DEFVAR to push EQU address directly.
9. .S printed top-to-bottom instead of standard bottom-to-top. Reversed iteration.
10. .S had no depth cap; corrupted ESP caused thousands of zeros. Added cap at 64.
11. serial_getchar used test al,al (ZF) which broke on NULL characters. Changed to clc/stc (CF).

Critical DTC Forth lesson: In threaded code, compiled cells must contain the XT (code field address), NOT the native code address. NEXT does lodsd to get XT, then jmp [eax] reads through the code field. Only the code field of a word header (first cell) should contain the native code address.

On the horizon
Key development areas include implementing vocabulary loading systems to support modular dictionary loading ("using Amiga, using Linux" style), expanding architecture portability beyond x86 (Pi/ARM64 is a priority), adding block/file system support, and creating UIR-to-Forth code generation to bridge the binary translator with the Forth kernel.
A critical upcoming capability is the driver extraction system - designed to analyze Windows drivers, separate hardware protocol code from Windows scaffolding, and convert the hardware manipulation portions into installable Forth modules. This would enable "scraping drivers into forth" as loadable dictionaries.
User has expressed interest in: CPU detection via CPUID for installer lookup tables, Raspberry Pi boot (SD/SSD adapter), and the fact that most PCs are x86-compatible (Apple Silicon is ARM64, not 68000).

Key learnings & principles
The project has validated that Forth-83's floored division semantics require special handling since most CPUs use symmetric division - the correction must check (remainder XOR divisor) < 0 to detect when symmetric division gave the wrong result, then adjust: quotient -= 1, remainder += divisor.
The "ship builder's manifesto" principle has proven effective as both a technical guideline and collaborator filter. Direct hardware access without HAL layers is achievable and provides the control needed for critical systems applications.
State save/restore philosophy: "best way is to save an image before interpreting a new file or command set - then restore it if ctrl C escapement is triggered so that the system returns to stable." This is implemented via save_esp/save_ebp/save_state/save_here/save_latest snapshots before each read_line.

Approach & patterns
Development follows a systematic five-phase roadmap from Genesis through Production deployment. Technical implementation uses Direct Threaded Code interpretation for real-time compilation capabilities, with assembly-language kernels providing primitives that extend through Forth definitions.
The binary translator employs a multi-stage pipeline: binary format parsing (PE/ELF) -> intermediate representation -> optimization passes -> target architecture code generation.
Collaboration strategy targets specific communities (Forth enthusiasts, space systems developers, embedded systems engineers) rather than general programming audiences.

Tools & resources
Primary development tools: NASM assembler, QEMU emulator, gcc, make, git. All installed on the development machine (Linux).
Build: `make` in project root. Test: launch QEMU with serial TCP, connect with Python script or netcat.
GitHub repo: https://github.com/jeweledtech/bare-metal-forth (remote: origin)
Project directory: /home/bbrown/projects/forthos
IMPORTANT: Do not add AI/Claude/Anthropic attribution to git commits.

Project Instructions:

Taking into account what we've built in the Initial Build conversation: 
The biggest problems with this project are: 1. It requires someone that has written Operating systems before and is familiar with the various microprocessor architecture. 2. The person also needs to be familiar with the Forth 83 standard language and has been able to run it on window's 95 or other non HAL protected-OS'es. The forth that I'm after can compile and execute running code in real time. Not, stop the program -> recompile -> then restart. The earlier forth could write directly to live memory in the buffers and execute code instantly. That is part of what I'm after here. Forth uses RPN (Reverse Polish Notation) so it takes info like the CPU and its registers do. So we want to be able to get around the HAL issues with Windows 98 and-on and the registry piece of crap among other things in this design. It should just run direct forth OS code. No linux layer, no windows layer, no Apple layer. Clean from scratch starting with machine code. Direct BIOS communications with the various CPUs out there now, that may be a major undertaking to ensure you get the right instruction set. And the extended instruction set that is available on some of these devices. Ideally, we would have a transcode table for different processors and the forth OS would build itself for that CPU. But that would assume having a version of this specific OS already running.

When forth loaded you would tell it what dictionary to use using Amiga, using Linux, using Telecom 85. All of which were forth code files that loaded the library collection of definitions. Forth would take, moveax <address from> <address to>  and it pops and pushes onto registers directly (modem, network card, video GPU, ...). The feature we want to build is that you can directly edit any memory address, pointer or register in the system directly. Which is of course dangerous if you don't know what you are doing. The main solution we are after is where this comes in handy is reading a file on a drive, de-compiling it into a translatable version for use on a different CPU (cross-interpreter stuff) that would make moving programs out of windows and onto any other mapped language possible. You could also build an analyzer that could say, "video dll code", "disc access code" ... and name the DLL content as a threaded library. Please reference the "chat gpt produced.docx" for an example. Imagine being able to map the dot-net dll collection and remove all insecurity crap from it so you can just call it like a regular DLL - treat it as a plug and play code module which is what we used to be able to do.
