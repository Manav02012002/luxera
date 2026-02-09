from luxera.project.presets import en12464_direct_job, en13032_radiosity_job


def test_presets():
    j1 = en12464_direct_job()
    assert j1.type == "direct"
    j2 = en13032_radiosity_job()
    assert j2.type == "radiosity"
    assert j2.settings.get("max_iterations") == 200
