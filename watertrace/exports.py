"""Image-free geographic handoff; geometry describes review zones, not water."""
from copy import deepcopy


def geographic_geometry(geometry):
    """Normalize accepted exterior rings to GeoJSON's counterclockwise order."""
    ring = geometry['coordinates'][0]
    x, y = ring[0]
    # Translate first to avoid cancellation for small polygons far from (0, 0).
    signed_area = sum((a[0]-x)*(b[1]-y) - (b[0]-x)*(a[1]-y)
                      for a, b in zip(ring, ring[1:]))
    return {'type': 'Polygon', 'coordinates': [list(reversed(ring)) if signed_area < 0 else ring]}


def geojson_export(report, reviews=None):
    """Export an accepted analysis. Never mutate it or promote human annotations."""
    reviews = reviews or {}
    features = []
    for zone in report['zones']:
        decision = zone.get('decision') or {}
        support = zone.get('spatial_support') or {}
        temporal = zone.get('temporal_support') or {}
        review = reviews.get(zone['id']) or {}
        properties = {key: zone.get(key) for key in (
            'id', 'name', 'crop', 'water_observed_ha', 'uncertain_ha',
            'no_water_detected_ha', 'water_fraction', 'pixels',
            'new_water_candidate_ha', 'repeat_water_observed_ha')}
        properties.update({
            **{key: temporal.get(key) for key in (
                'paired_assessed_ha', 'paired_uncertain_ha', 'paired_assessed_fraction',
                'water_without_baseline_ha', 'observed_water_baseline_fraction',
                'observed_water_baseline_complete')},
            'temporal_policy': temporal.get('policy'),
            'review_queue': zone.get('status'),
            'scene_overlap_ha': zone.get('area_ha'),
            'assessed_fraction': zone.get('coverage'),
            'scene_clipped': support.get('scene_clipped'),
            'scene_overlap_fraction': support.get('scene_overlap_fraction'),
            'scene_overlap_fraction_basis': support.get('fraction_basis'),
            'boundary_tolerance_pixels': support.get('boundary_tolerance_pixels'),
            'geometry_role': 'review_zone_boundary_not_water_mask',
            'area_scope': 'scene_overlap_pixel_centers',
            'area_notice': 'Measurements cover only scene overlap, not necessarily the full boundary. Zones may overlap; do not sum as unique affected land.',
            'zone_basis': report.get('zone_basis'),
            'review_gate': decision.get('level'),
            'review_next_step': decision.get('next_step'),
            'review_reasons': decision.get('reasons', []),
            'signal_reasons': zone.get('reasons', []),
            'withheld_claims': decision.get('withheld_claims', []),
            'decision_policy': decision.get('policy'),
            'pixel_policy': report['engine']['policy'],
            'source_sha256': report['source']['sha256'],
            'observed_on': report['source'].get('observed_on'),
            'reference_sha256': (report.get('reference') or {}).get('sha256'),
            'reference_on': (report.get('reference') or {}).get('observed_on'),
            'human_outcome': review.get('outcome'),
            'human_note': review.get('note'),
            'human_recorded_at': review.get('recorded_at'),
            'human_review_unverified': True,
        })
        features.append({'type': 'Feature', 'id': zone['id'],
                         'geometry': geographic_geometry(zone['geometry']), 'properties': properties})
    metadata = {key: report.get(key) for key in (
        'source', 'reference', 'engine', 'policy', 'reference_policy',
        'zone_basis', 'limitations', 'lab', 'context', 'temporal_support')}
    metadata.update({
        'schema_version': 'geojson-review-v3',
        'geometry_role': 'review_zone_boundaries_not_water_segmentation',
        'area_scope': 'scene_overlap_pixel_centers',
        'review_notice': 'Human annotations are unverified, not algorithmic findings. Locations and notes may be sensitive. Use the full review JSON to restore notes.',
    })
    return deepcopy({'type': 'FeatureCollection', 'watertrace': metadata, 'features': features})
