from luxera.compliance import ActivityType, check_compliance_from_grid


def test_en12464_compliance_pass():
    grid = [500.0, 520.0, 480.0, 510.0]
    report = check_compliance_from_grid(
        room_name="Office",
        activity_type=ActivityType.OFFICE_GENERAL,
        grid_values_lux=grid,
        maintenance_factor=1.0,
        ugr=19.0,
    )
    assert report.is_compliant is True
    assert report.fail_count == 0


def test_en12464_compliance_fail():
    grid = [200.0, 220.0, 180.0, 190.0]
    report = check_compliance_from_grid(
        room_name="Office",
        activity_type=ActivityType.OFFICE_GENERAL,
        grid_values_lux=grid,
        maintenance_factor=1.0,
        ugr=25.0,
    )
    assert report.is_compliant is False
    assert report.fail_count >= 1
