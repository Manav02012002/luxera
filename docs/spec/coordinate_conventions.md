# Coordinate Conventions

## World Frame
- `+X`: primary horizontal axis.
- `+Y`: secondary horizontal axis.
- `+Z`: up.

## Luminaire Local Frame
- `+Z`: up (same gravity direction as world after transform).
- Nadir direction is local `-Z`.
- Type-C photometry convention:
  - `C=0` toward local `+X`
  - `C=90` toward local `+Y`

## Euler Rotation Convention
- `from_euler_zyx(position, yaw, pitch, roll)` uses ZYX composition.
- Rotation matrix is `Rz(yaw) * Ry(pitch) * Rx(roll)`.
- Meaning:
  - `yaw`: rotation about world/local-aligned `Z`
  - `pitch`: rotation about `Y`
  - `roll`: rotation about `X`

## Aim/Up Convention
- `from_aim_up(position, aim, up)` creates orientation such that local `-Z` points along `aim`.
- This matches downlight semantics where the optical axis is downward.
- `up` resolves the in-plane twist around the aim axis.

## Sampling Pipeline
- World direction is transformed to luminaire-local direction.
- Local direction is converted to photometric angles (C/Gamma for Type-C).
- Symmetry reduction + interpolation are applied in photometric space.

## Invariance Expectations
- Yaw-only, pitch-only, and roll-only transforms must rotate unit vectors around the expected axes.
- Rotating a luminaire should rotate the illuminance field accordingly (same values in rotated positions).
