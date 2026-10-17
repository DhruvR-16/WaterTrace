"""Review gates separate a measured signal from a defensible field-level claim.

These gates do not change the frozen v1 pixel classifier or its benchmark scores.
Context is provided by the user, not inferred from a place name.
"""

WITHHELD = ["crop damage", "water depth", "continuous flood duration", "field access safety"]


def review_decision(zone, paired):
    reasons = []
    if zone['pixels'] < 25:
        reasons.append('This zone has fewer than 25 pixels; do not interpret a field-level area estimate.')
    # Engine reasons use unrounded coverage; display rounding must not clear a gate.
    if zone['coverage'] < .7 or any('More than 30%' in reason for reason in zone['reasons']):
        reasons.append('More than 30% is uncertain; obtain another observation or independent evidence.')
    if any('outside the scene' in reason for reason in zone['reasons']):
        reasons.append('Only part of this zone is covered by the image.')
    if reasons:
        level, next_step = 'insufficient_evidence', 'Resolve coverage or resolution before prioritizing this as a whole field.'
    elif zone['crop'].strip().lower() in ('rice', 'paddy'):
        level, next_step = 'context_required', 'Confirm crop stage and intentional inundation with a local reviewer.'
        reasons.append('A water signal in a paddy is not by itself an abnormal flood.')
    elif paired and zone['repeat_water_observed_ha'] > 0 and zone['new_water_candidate_ha'] == 0:
        level, next_step = 'repeat_observation', 'Check a longer-term water baseline; two observations do not establish permanent water.'
        reasons.append('Water was seen at both endpoints without a detected new-water candidate in this zone.')
    elif zone['water_fraction'] >= .05:
        level, next_step = 'water_candidate', 'Cross-check local land use and acquisition conditions before requesting human inspection.'
    else:
        level, next_step = 'low_signal', 'Retain the observation; investigate reported impacts even if this screen shows little water.'
    if not paired:
        reasons.append('Without an earlier matched observation, flood onset is not established.')
    return {'level':level, 'next_step':next_step, 'reasons':reasons,
            'withheld_claims':list(WITHHELD), 'policy':'review-gates-v1'}
