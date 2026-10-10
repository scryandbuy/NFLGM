# Compressed portable exports

## Cause and change

The Export button called `Session.save()` and moved the entire JSON string
across Pyodide's bridge before creating a download Blob. A large franchise
therefore allocated full-size export strings in addition to the live game.

`Session.export_file()` uses the existing `_save_data()` snapshot and JSON
encoder, writing buffered output through gzip. The browser copies the compressed
temporary file into Blob blocks of at most 256 KiB and removes the file in a
`finally` block. This does not prune history, alter gameplay, advance RNG, or
depend on the latest autosave. An unfinished live game remains in the snapshot.

Exports now use `.json.gz`. Both import selectors accept this format and legacy
`.json`; gzip is detected by content. Import decompresses a stream into the
existing engine file loader. Invalid/truncated compressed input fails and cleans
up the temporary file. Older game builds require decompressing the gzip first.
The start-screen browser-backup recovery continues to return its existing JSON.

## Observed saved-franchise evidence

Input: the user's `nflgm-2034-offseason-2.json`, 211,798,067 bytes. Loading applies
the existing migrations; both export paths then produce the same 211,819,089
decoded bytes. Native and browser decoded SHA-256:

`ddc0b9a86a8cb94b0a2b39ce271473a7e7cb91874622ccaa74cff50305621e01`

| Native engine measurement | Previous | Compressed |
| --- | ---: | ---: |
| Export size | 211.82 MB | 28.17 MB |
| Sampled extra process working set | 204.25 MiB | 4.18 MiB |
| Export time | 1.66 seconds | 11.14 seconds |

Measurements use separate processes with the same source and 10 ms working-set
sampling. Native memory results exclude the browser's Blob and filesystem; they
are not a claim about total Chrome memory. Compression reduced the file by 86.7%.

The actual browser/Pyodide export also completed: 28,170,063 bytes in 16.36 seconds,
with the same decoded hash and no retained temporary export file. Gzip header
filenames explain the seven-byte native/browser compressed size difference.

A second browser run exported in 16.15 seconds, then reloaded the compressed
file through `loadSessionFromBlob()` into a fresh session. Year, stop, player,
transaction and game archive counts, and RNG state were unchanged. Both
temporary import and export files were removed. The user's browser database
and original exported file were never modified.

## Controlled checks and limits

- 11 Python tests: exact save-byte equality, Unicode, NumPy, archive and unfinished
  game data, RNG preservation, existing save encoding and resume behavior.
- JavaScript tests exercise real Blob and decompression streams, old JSON imports,
  gzip imports, bounded transfer, malformed/truncated data, and failure cleanup.
- Existing save/import text cleanup checks, build and JavaScript syntax pass.
- Export still takes a synchronous snapshot and performs compression on the main
  thread. It trades extra processing time for much lower temporary memory.
- This does not reduce the loaded franchise's retained memory or guarantee that
  every tab already at its memory limit can export. No claim of a measured total
  Chrome-memory reduction is made.
