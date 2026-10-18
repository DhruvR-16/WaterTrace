"""Shared strict parsing for local geographic inputs, before raster work."""
import json
import math

from watertrace.engine import InvalidRaster

MAX_ZONE_BYTES = 200_000
MAX_JSON_DEPTH = 32


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate object key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Non-finite JSON constant')


def load_zones(content):
    """Reject ambiguous/nonportable JSON; geometry validation follows in the engine."""
    try:
        raw = content.encode('utf-8') if isinstance(content, str) else content
        if len(raw) > MAX_ZONE_BYTES:
            raise InvalidRaster('Zone GeoJSON exceeds 200 KB.')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
        if not isinstance(value, dict) or value.get('type') != 'FeatureCollection':
            raise ValueError('Not a FeatureCollection')
        # Iterative traversal bounds nesting without recursively validating metadata.
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError('Excessive nesting')
            if isinstance(item, dict):
                pending.extend((child, depth+1) for pair in item.items() for child in pair)
            elif isinstance(item, list):
                pending.extend((child, depth+1) for child in item)
            elif isinstance(item, str):
                item.encode('utf-8')  # Reject escaped lone surrogates too.
            elif isinstance(item, float) and not math.isfinite(item):
                raise ValueError('Non-finite numeric value')
        return value
    except InvalidRaster:
        raise
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        raise InvalidRaster('Zones must be UTF-8 GeoJSON with unique keys, finite values and nesting of at most 32 levels.') from None
