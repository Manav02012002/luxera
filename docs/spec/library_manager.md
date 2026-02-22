# Photometry Library Manager

The local library manager provides deterministic indexing and search for IES/LDT assets.

## Commands

1. Build or refresh an index:

```bash
luxera library index <folder> --out <db>
```

- Recursively scans `<folder>` for `.ies` and `.ldt`.
- Computes `sha256` for each file.
- Parses metadata and stores:
  - file path
  - file hash
  - manufacturer
  - luminaire name
  - catalog number
  - lumens
  - CCT
  - CRI
  - beam angle
  - distribution type
  - coordinate system
- Uses deterministic scan ordering (`path` sort) and stable metadata serialization (`sort_keys=True` JSON).

2. Search the index:

```bash
luxera library search --db <db> --query "manufacturer:acme lumens>=2000 cct=4000 beam<80"
```

Supported query forms:

- `manufacturer:<text>` or `mfg:<text>`
- numeric filters:
  - `lumens>=...`, `lumens<=...`, `lumens=...`
  - `cct>=...`, `cct<=...`, `cct=...`
  - `beam>=...`, `beam<=...`, `beam=...`
- free keywords (matches manufacturer, name, catalog number, file name/path)

`--json` prints machine-readable search results for automation.

## GUI Integration

When the workspace GUI is available, a **Photometry Library** tab is present:

- Open/select a library DB.
- Index a folder into that DB.
- Search records in a table.
- Drag a table row into the 2D viewport to place a luminaire at the drop location.

Drop behavior:

- If the photometry file is not yet in project assets, it is added automatically.
- A new luminaire instance is then placed at the dropped XY coordinate with a default mounting height.

