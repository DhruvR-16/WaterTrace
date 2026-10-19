import numpy as np

from scripts.evaluate_watertrace import experimental_baselines
from watertrace.engine import read_raster
from test_watertrace import tif


def test_filtered_controls_keep_nodata_unknown_and_require_dual_agreement():
    data = np.empty((2, 64, 64), np.float32)
    data[0] = -7;data[1] = -13
    data[:, :, :24] = np.array([-29, -35])[:, None, None]
    data[1, :, 35:48] = -35
    data += np.linspace(-1, 1, 64, dtype=np.float32)[None, :, None]
    data[:, 10:20, 10:20] = -9999
    variants = experimental_baselines(read_raster(tif(data=data)))
    vh, valid = variants['filtered_vh_otsu']
    dual, dual_valid = variants['filtered_dual_otsu']
    assert vh[30, 40] and not dual[30, 40]
    assert dual[30, 10]
    assert not valid[9:21, 9:21].any()
    assert not valid[0].any() and not valid[-1].any()
    assert not dual[~valid].any()
    np.testing.assert_array_equal(valid, dual_valid)
