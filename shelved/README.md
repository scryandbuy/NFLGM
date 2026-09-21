# Shelved: the TypeScript port

Abandoned 2026-09-21 after benchmarking Pyodide.

The port existed because GitHub Pages cannot run Python server-side. It can,
however, serve Pyodide, which runs Python in the browser via WebAssembly.

Measured on this engine, real 2026 rosters, 16 games:

    native CPython   0.106 s/game    272-game season  29 s
    Pyodide (wasm)   0.216 s/game    272-game season  59 s

A 2x penalty, not the 10x that was assumed. First load is 9.6 MB for Pyodide
core plus 3 MB for numpy, cached after.

So Python is the product. Every future system - season loop, draft, free
agency, offseason, UI - stays in Python and is never ported.

What is kept here, in case it is ever wanted: 15 modules, all verified
numerically against their Python originals (gameplan, adjust, zone coverage,
play assembly, TeamState/fieldUnits, the drive loop, playGame/playOvertime,
StatBook, the roster loader and the calibration register). One known open
divergence: the margin distribution runs wider than Python's.
