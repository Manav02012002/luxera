# Report Contracts

All exported reports must contain auditable provenance.

Mandatory audit fields:
- Project name + schema version
- Job id + job hash
- Solver/backend version details
- Full job settings (including seed and effective defaults)
- Photometry file hashes and source references
- Coordinate convention and units contract
- Compliance assumptions and unsupported-feature disclosures

Bundle modes:
- Client bundle: curated summary outputs
- Audit bundle: full project snapshot, assets, result artifacts, checksums, and manifest
