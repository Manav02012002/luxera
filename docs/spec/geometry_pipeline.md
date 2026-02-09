# Geometry Pipeline Contract

## Internal Geometry Standard
- Canonical units: meters.
- Surfaces represented as planar polygons with explicit winding.
- `geometry.surfaces` is authoritative for imported mesh/surface workflows.
- Calc objects must reference `room_id` or `zone_id` when rooms/zones exist.

## Import Priority
1. DXF (room-first workflow)
2. OBJ/GLTF (mesh-first workflow)
3. IFC (space-first workflow, mesh extraction when geometry kernel available; metadata fallback otherwise)

## Scene Cleaning
- `fix_surface_normals`: enforce normal/winding consistency.
- `close_tiny_gaps`: snap near-coincident vertices within tolerance.
- `merge_coplanar_surfaces`: conservative coplanar merge.
- `detect_non_manifold_edges`: flags topology defects (edge valence > 2).
- `detect_room_volumes_from_surfaces`: derive axis-aligned room envelopes from grouped surfaces.

## CLI Operations
- `luxera geometry import <project> <file>`
- `luxera geometry clean <project> [--snap-tolerance ...] [--detect-rooms]`

## Audit
- Geometry import source and resulting project state are captured by project snapshots/debug bundles.
