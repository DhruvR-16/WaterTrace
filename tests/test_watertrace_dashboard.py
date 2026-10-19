"""Markup and CSS contracts; these do not substitute for browser visual QA."""
from html.parser import HTMLParser
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'watertrace/static'


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_all_dashboard_bindings_resolve_to_unique_elements():
    html = (ROOT / 'index.html').read_text()
    elements = Elements(html).elements
    ids = [attrs['id'] for _, attrs in elements if 'id' in attrs]
    assert len(ids) == len(set(ids))
    bindings = set(re.findall(r"\$\('([^']+)'\)", (ROOT / 'app.js').read_text()))
    assert bindings <= set(ids)
    assert sum(tag == 'main' for tag, _ in elements) == 1
    assert any(tag == 'a' and attrs.get('href') == '#main-content' for tag, attrs in elements)
    for tag, attrs in elements:
        if tag == 'dialog':
            assert attrs.get('aria-labelledby') in ids


def test_radar_geometry_and_range_control_are_not_squeezed_by_generic_input_rules():
    css = (ROOT / 'style.css').read_text()
    assert re.search(r'\.map-stack #satellite\s*\{[^}]*height:auto', css)
    assert re.search(r'#comparison-position\s*\{[^}]*width:clamp\(100px', css)
    assert not re.search(r'\.map-toolbar input\s*\{', css)
    assert 'prefers-reduced-motion:reduce' in css
    assert '[hidden] { display:none!important; }' in css
    assert '@import' not in css


def test_dashboard_exposes_all_six_change_categories():
    html = (ROOT / 'index.html').read_text()
    elements = Elements(html).elements
    classes = {attrs.get('class') for tag, attrs in elements if tag == 'i'}
    assert {'new-swatch', 'repeat-swatch', 'absent-swatch', 'baseline-swatch',
            'no-water-swatch', 'unassessed-swatch'} <= classes
    slider = next(attrs for _, attrs in elements if attrs.get('id') == 'comparison-position')
    assert slider['type'] == 'range' and slider['min'] == '0' and slider['max'] == '100'
    assert slider['aria-label']


def test_markup_does_not_require_unsafe_inline_content_security_policy():
    elements = Elements((ROOT / 'index.html').read_text()).elements
    for tag, attrs in elements:
        assert 'style' not in attrs
        assert not any(name.startswith('on') for name in attrs)
        if tag == 'script':
            assert attrs.get('src', '').startswith('/static/')
    css = (ROOT / 'style.css').read_text()
    assert re.search(r'#comparison-earlier\s*\{[^}]*pointer-events:none', css)


def test_guided_workspace_has_empty_state_and_progressive_technical_controls():
    elements = Elements((ROOT / 'index.html').read_text()).elements
    attrs_by_id = {attrs['id']: attrs for _, attrs in elements if 'id' in attrs}
    assert 'hidden' in attrs_by_id['analysis-content']
    assert 'hidden' not in attrs_by_id['getting-started']
    assert attrs_by_id['zone-detail']['tabindex'] == '-1'
    assert 'next-zone' in attrs_by_id and 'result-explanation' in attrs_by_id
    advanced = [attrs for tag, attrs in elements if tag == 'details' and
                ('advanced-tools' in attrs.get('class', '') or 'technical-details' in attrs.get('class', ''))]
    assert len(advanced) == 3
    assert all('open' not in attrs for attrs in advanced)


@pytest.mark.parametrize('foreground,background', [
    ('142d36', 'ffffff'), ('526871', 'ffffff'), ('526871', 'eef3f5'),
    ('adc5ce', '102b35'), ('e0eef2', '254752'), ('102b35', 'b8ec75'),
    ('ffffff', '176979'), ('775214', 'faf5e9'),
])
def test_primary_dashboard_text_palette_has_readable_contrast(foreground, background):
    def luminance(hex_color):
        components = [int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in components]
        return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted([luminance(foreground), luminance(background)], reverse=True)
    assert (light + .05) / (dark + .05) >= 4.5
