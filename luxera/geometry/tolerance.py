from __future__ import annotations

# Positional epsilon for near-zero distance/length checks.
EPS_POS = 1e-12

# Angular epsilon (dimensionless tolerance used for orthogonality/unit checks).
EPS_ANG = 1e-9

# Area epsilon for degenerate polygon/triangle checks.
EPS_AREA = 1e-12

# Plane-distance epsilon for coplanarity checks.
EPS_PLANE = 1e-6

# Ray origin epsilon baseline for occlusion/ray casting.
EPS_RAY_ORIGIN = 1e-5

# Vertex weld/snap epsilon for polygon and mesh cleaning.
EPS_WELD = 1e-6

# Scene-cleaning default snap tolerance.
EPS_SNAP = 1e-3

# Shape-quality ratio threshold used for sliver detection.
EPS_SLIVER_RATIO = 1e-3
