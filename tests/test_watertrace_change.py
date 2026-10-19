import base64

import cv2
import numpy as np

from watertrace.service import change_preview, run_analysis, export_report
from test_watertrace import tif


def test_all_nine_change_states_are_explicit():
    earlier = np.array([[0, 1, 2]] * 3, np.uint8)
    current = earlier.T.copy()
    image = change_preview(current, earlier)
    decoded = cv2.imdecode(np.frombuffer(base64.b64decode(image.split(',')[1]), np.uint8), cv2.IMREAD_COLOR)
    dark = [65, 55, 50]
    assert decoded.tolist() == [
        [dark, dark, dark],
        [dark, [220, 220, 220], [45, 145, 235]],
        [[190, 100, 180], [190, 210, 0], [190, 95, 35]],
    ]


def test_change_preview_requires_pair_and_stays_out_of_export():
    result = run_analysis(tif(), observed_on='2020-01-10')
    assert result['images']['change'] is None
    paired = run_analysis(tif(), observed_on='2020-01-10', reference_raw=tif(),
                          reference_on='2020-01-01', same_orbit=True)
    assert paired['images']['change'].startswith('data:image/png;base64,')
    assert 'images' not in export_report(paired)
    assert paired['summary'] == result['summary']
