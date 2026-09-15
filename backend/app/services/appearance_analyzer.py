"""Conservative attribute evidence; ranking values are not probabilities."""
from statistics import mean
from app.models.schemas import AttributeDetail, TrackResult
from app.services.visual_features import expected_colors


def select_evidence(detections, limit=6):
    """Limit repeated neighboring frames without requiring the person to move."""
    selected = []
    for det in sorted(detections, key=lambda d: d.confidence * d.quality_score, reverse=True):
        if all(abs(det.timestamp_seconds - other.timestamp_seconds) >= .75 for other in selected):
            selected.append(det)
        if len(selected) == limit:
            break
    return sorted(selected, key=lambda d: d.timestamp_seconds)


class AppearanceAnalyzer:
    @classmethod
    def evaluate_track(cls, session_id, track_id, detections, target_config, search_plan,
                       data_base_dir, detector=None):
        if not detections:
            raise ValueError(f'Track {track_id} has no detections.')
        detections = sorted(detections, key=lambda d: d.timestamp_seconds)
        samples = [d.model_copy(deep=True) for d in select_evidence(detections)]
        if detector:
            samples = [detector.refine_evidence(d) for d in samples]
        best = max(samples, key=lambda d: d.confidence * d.quality_score)
        strategy = search_plan.analysis_strategy
        trusted = [d for d in samples if d.detector_name == 'YOLO instance segmentation'
                   and d.model_version and d.confidence >= max(.5, strategy.minimum_person_confidence)
                   and d.quality_score >= .25]
        person_supported = len(trusted) >= strategy.minimum_track_observations
        attributes = {}
        requested = []
        for region, key, expected in (
            ('upper', 'upper_clothing', target_config.upper_clothing_color),
            ('lower', 'lower_clothing', target_config.lower_clothing_color),
            ('backpack', 'backpack', target_config.backpack),
        ):
            colors = expected_colors(expected)
            negated_color = (expected or '').lower().startswith('not ')
            if negated_color:
                colors = set()
            absent_bag = region == 'backpack' and (expected or '').lower().strip() in ('none', 'no backpack', 'without backpack')
            views = [d for d in trusted if d.color_features.get(region)
                     and d.attribute_visibility.get(region) in ('clear', 'partial')
                     and (region != 'backpack' or d.backpack_detected is True)]
            distribution = {color: mean(d.color_features[region].get(color, 0) for d in views)
                            for color in set().union(*(d.color_features[region] for d in views))}
            dominant = max(distribution, key=distribution.get) if distribution else None
            observed = 'Unknown'
            assessment, score = 'unknown', None
            if dominant:
                observed = f'{dominant if distribution[dominant] >= .45 else "Mixed colors"}; ' + ('detected backpack' if region == 'backpack' else 'approximate clothing region')
                if absent_bag:
                    score, assessment = 0., 'conflict'
                elif colors:
                    score = min(1., sum(distribution.get(c, 0) for c in colors))
                    # Require agreement across views; average colors cannot hide a conflict.
                    per_view = [sum(d.color_features[region].get(c, 0) for c in colors) for d in views]
                    if score >= .55 and min(per_view) >= .35:
                        assessment = 'match'
                    elif score <= .15 and distribution[dominant] >= .65 and len(views) >= 2:
                        assessment = 'conflict'
                elif region == 'backpack' and (expected or '').lower().strip() in ('backpack', 'a backpack', 'back pack'):
                    score, assessment = 1., 'match'
            attributes[key] = AttributeDetail(expected=expected or '', observed=observed,
                score=round(score, 3) if score is not None else None,
                visibility='partial' if views else 'not_visible', assessment=assessment,
                method='YOLO object masks; HSV color; approximate upright clothing bands',
                evidence_timestamps=[d.timestamp_seconds for d in views],
                evidence_paths=[d.crop_path for d in views if d.crop_path])
            if expected:
                requested.append(key)
        for key, expected in (
            ('hair', ' '.join(filter(None, [target_config.hair_color, target_config.hair_length]))),
            ('shoes', target_config.shoe_color), ('upper_clothing_type', target_config.upper_clothing_type),
            ('lower_clothing_type', target_config.lower_clothing_type), ('body_build', target_config.body_build),
            ('hat', target_config.hat), ('accessories', target_config.other_accessories),
            ('distinctive_features', target_config.distinctive_features),
        ):
            if expected:
                attributes[key] = AttributeDetail(expected=expected, observed='Not evaluated', visibility='not_visible')
        matching = [f'{key.replace("_", " ")}: {a.observed}' for key, a in attributes.items() if a.assessment == 'match']
        conflicts = [f'{key.replace("_", " ")}: {a.observed}' for key, a in attributes.items() if a.assessment == 'conflict']
        unknown = [key for key, a in attributes.items() if a.expected and a.assessment == 'unknown']
        constraints = target_config.required_attributes + target_config.negative_attributes
        unknown.extend(f'Unevaluated constraint: {item}' for item in constraints)
        # Unknown attributes receive no support, but remain distinct from conflicts.
        similarity = mean(attributes[key].score or 0. for key in requested) if requested else 0.
        ranking = similarity if person_supported else 0.
        enough_attributes = requested and any(attributes[key].assessment == 'match' for key in requested)
        if not person_supported:
            classification, explanation = 'insufficient_visibility', 'Too few clear, separated YOLO person observations; retained for manual inspection.'
        elif conflicts:
            classification, explanation = 'unlikely_match', 'Visible attributes conflict with the search description.'
        elif enough_attributes and ranking >= target_config.min_alert_confidence and not constraints:
            classification = 'strong_match' if ranking >= max(.8, target_config.min_alert_confidence) and not unknown else 'possible_match'
            explanation = 'Visible evidence supports the description. Review the listed crops and original footage.'
        else:
            classification, explanation = 'insufficient_visibility', 'Insufficient supported attributes to meet the configured alert threshold; retained for manual inspection.'
        return TrackResult(session_id=session_id, track_id=track_id,
            first_seen_seconds=detections[0].timestamp_seconds, last_seen_seconds=detections[-1].timestamp_seconds,
            best_timestamp_seconds=best.timestamp_seconds, classification=classification,
            person_detection_confidence=round(mean(d.confidence for d in samples), 3),
            appearance_similarity=round(similarity, 3), evidence_quality=round(mean(d.quality_score for d in samples), 3),
            final_ranking_score=round(ranking, 3), observations_analyzed=len(samples), attributes=attributes,
            matching_evidence=matching, conflicting_evidence=conflicts, unknown_attributes=unknown,
            requires_human_review=True, explanation=explanation, best_frame_path=best.crop_path or '',
            cropped_samples=[d.crop_path for d in samples if d.crop_path],
            model_version=best.model_version, evidence_timestamps=[d.timestamp_seconds for d in samples],
            evidence_observations=samples)
