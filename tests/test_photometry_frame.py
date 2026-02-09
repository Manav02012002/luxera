from luxera.geometry.core import Vector3
from luxera.core.transform import from_euler_zyx
from luxera.photometry.frame import world_dir_to_photometric_angles


def test_world_dir_to_photometric_angles_rotated():
    # Rotate luminaire +90 deg yaw about Z
    t = from_euler_zyx(Vector3(0, 0, 0), yaw_deg=90, pitch_deg=0, roll_deg=0)

    # World +Y should map to local +X for this rotation
    c_deg, gamma_deg = world_dir_to_photometric_angles(t, Vector3(0, 1, 0), "C")

    assert abs(c_deg - 0.0) < 1e-6
    assert abs(gamma_deg - 90.0) < 1e-6
