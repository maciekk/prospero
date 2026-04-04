# PDF Export

Selected read commands support `--pdf PATH` to write a formatted PDF alongside the normal terminal output. The flag is additive — terminal output always appears, and the PDF is written in addition.

## Commands with `--pdf`

- `prospero acb report` — combined PDF: capital gains table + year-end ACB pools (two pages/sections in one file)
- `prospero acb show` — ACB pools table
- `prospero plan run` — wealth projection table + summary
- `prospero portfolio value` — portfolio valuation table + summary
- `prospero tax-breakdown` — tax breakdown table

## Architecture

- `PDF_OPTION` is defined once in `src/prospero/cli/_options.py` and imported by each CLI module — not redefined per command.
- All PDF rendering lives in `src/prospero/display/pdf.py`, parallel to `display/tables.py`. One `pdf_*` function per `render_*` function.
- PDFs are black-and-white (grayscale only). Negative values use parentheses accounting notation `($1,234.56)` rather than colour.
- Built-in Helvetica font is used (latin-1 encoding). Avoid non-latin-1 characters (e.g. em dash `—`) in any strings written to PDF cells.

## Adding `--pdf` to a New Command

1. Import `PDF_OPTION` from `src/prospero/cli/_options.py`.
2. Add a `pdf_path: PDF_OPTION = None` parameter to the command function.
3. Add a `pdf_*` function in `src/prospero/display/pdf.py` mirroring the corresponding `render_*` function in `display/tables.py`.
4. Call the `pdf_*` function when `pdf_path` is not `None`.