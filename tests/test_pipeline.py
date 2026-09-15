import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import numpy as np
from app.models.schemas import DetectionItem, TargetConfiguration
from app.services.appearance_analyzer import AppearanceAnalyzer
from app.services.search_agent import SearchPlanAgent
from app.services.detector import PersonDetector, _bag_owner
from app.services.tracker import compute_iou, PersonTracker
from app.services.visual_features import masked_regions
from app.services.visual_features import color_match_score


def detection(t=0, **changes):
    values = dict(detection_id=f'd{t}', frame_idx=int(t*30), timestamp_seconds=t,
        bbox=[0,0,100,200], confidence=.9, quality_score=.8,
        detector_name='YOLO instance segmentation', model_version='test', crop_path=f'/crops/test/{t}.jpg',
        color_features={'upper': {'green': .9, 'black': .1}, 'lower': {'black': .9}},
        attribute_visibility={'upper': 'partial', 'lower': 'partial'})
    values.update(changes)
    return DetectionItem(**values)


def evaluate(dets=None, **config):
    target = TargetConfiguration(upper_clothing_color='green', **config)
    return AppearanceAnalyzer.evaluate_track('test', 1, dets or [detection(), detection(1)],
        target, SearchPlanAgent.create_search_plan(target), '.', detector=None)


class PipelineTests(unittest.TestCase):
    def test_missing_model_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'model missing'):
                PersonDetector(directory, Path(directory) / 'missing.pt')

    def test_zero_people_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(PersonDetector, '_init_yolo'):
                detector = PersonDetector(directory)
            with patch.object(detector, '_predict', return_value=[]):
                self.assertEqual(detector.detect_in_frame(np.zeros((100,100,3), np.uint8), 'test', 0, 0), [])

    def test_inference_error_has_no_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(PersonDetector, '_init_yolo'):
                detector = PersonDetector(directory)
            detector.yolo_model = unittest.mock.Mock()
            detector.yolo_model.predict.side_effect = ValueError('bad inference')
            with self.assertRaisesRegex(RuntimeError, 'without a fallback'):
                detector.detect_in_frame(np.zeros((100,100,3), np.uint8), 'test', 0, 0)

    def test_black_bag_excluded_from_green_clothing(self):
        image = np.zeros((200,100,3), np.uint8)
        image[:120] = (0,160,0)
        person = np.full((200,100), 255, np.uint8)
        bag = np.zeros((200,100), np.uint8)
        bag[35:115,25:75] = 255
        image[bag>0] = 0
        features, visibility = masked_regions(image, person, bag)
        self.assertGreater(features['upper']['green'], .95)
        self.assertEqual(features['backpack']['black'], 1.)
        self.assertEqual(visibility['upper'], 'partial')

    def test_no_bag_mask_cannot_establish_backpack(self):
        result = evaluate(backpack='black backpack')
        self.assertEqual(result.attributes['backpack'].assessment, 'unknown')
        self.assertIsNone(result.attributes['backpack'].score)
        self.assertEqual(result.classification, 'insufficient_visibility')

    def test_short_silhouette_keeps_clothing_unknown(self):
        features, _ = masked_regions(np.zeros((50,100,3),np.uint8), np.full((50,100),255,np.uint8))
        self.assertEqual(features, {})

    def test_stationary_person_can_match(self):
        self.assertEqual(evaluate().classification, 'strong_match')
        tracker = PersonTracker()
        tracker.process_detections([detection()])
        tracker.process_detections([detection(1)])
        self.assertEqual(len(tracker.finalize()), 1)

    def test_untrusted_detector_cannot_be_promoted(self):
        result = evaluate([detection(detector_name='HOG'), detection(1, detector_name='HOG')])
        self.assertEqual(result.classification, 'insufficient_visibility')
        self.assertEqual(result.final_ranking_score, 0)

    def test_neighboring_frames_do_not_count_as_confirmation(self):
        result = evaluate([detection(t/10) for t in range(6)])
        self.assertEqual(result.observations_analyzed, 1)
        self.assertEqual(result.classification, 'insufficient_visibility')

    def test_threshold_applies_to_strong_matches_too(self):
        self.assertEqual(evaluate(min_alert_confidence=.95).classification, 'insufficient_visibility')

    def test_labels_and_scores_use_same_views(self):
        result = evaluate([detection(), detection(1, color_features={'upper': {'red': 1}})])
        attr = result.attributes['upper_clothing']
        self.assertEqual(attr.score, .45)
        self.assertEqual(attr.assessment, 'unknown')
        self.assertEqual(attr.evidence_timestamps, [0,1])
        self.assertEqual(len(attr.evidence_paths), 2)

    def test_visible_conflict_blocks_candidate(self):
        result = evaluate([detection(t, color_features={'upper': {'red': 1}}) for t in (0,1)])
        self.assertEqual(result.classification, 'unlikely_match')
        self.assertTrue(result.conflicting_evidence)

    def test_unsupported_constraints_remain_explicit(self):
        result = evaluate(required_attributes=['long sleeves'])
        self.assertEqual(result.classification, 'insufficient_visibility')
        self.assertIn('Unevaluated constraint: long sleeves', result.unknown_attributes)

    def test_iou_and_expiry(self):
        self.assertAlmostEqual(compute_iou([0,0,10,10], [5,0,15,10]), 1/3)
        self.assertEqual(compute_iou([0,0,0,0], [0,0,0,0]), 0)
        tracker = PersonTracker()
        tracker.process_detections([detection()])
        tracker.process_detections([], timestamp_seconds=4)
        self.assertFalse(tracker.active_tracks)

    def test_ambiguous_bag_not_assigned(self):
        self.assertIsNone(_bag_owner({'bbox':[10,20,30,80]}, [{'bbox':[0,0,100,200]}]*2))

    def test_original_description_extracted_without_defaults(self):
        target = SearchPlanAgent.normalize_target(TargetConfiguration(free_text_description='Locate a male with dark hair, green long sleeve top with black bottoms and a black back pack'))
        self.assertEqual((target.upper_clothing_color, target.lower_clothing_color, target.backpack), ('green', 'black', 'black backpack'))
        self.assertIsNone(TargetConfiguration().upper_clothing_color)

    def test_negated_description_not_extracted_as_positive(self):
        target = SearchPlanAgent.normalize_target(TargetConfiguration(free_text_description='green shirt without a black backpack'))
        self.assertEqual(target.backpack, 'not black backpack')

    def test_unsupported_backpack_color_is_not_presence_match(self):
        dets = [detection(t, backpack_detected=True,
                    color_features={'upper': {'green': .9}, 'backpack': {'black': 1}},
                    attribute_visibility={'upper':'partial','backpack':'partial'}) for t in (0,1)]
        self.assertEqual(evaluate(dets, backpack='khaki backpack').attributes['backpack'].assessment, 'unknown')

    def test_refined_observations_are_retained_for_audit(self):
        result = evaluate()
        self.assertEqual(result.evidence_observations[0].color_features['upper']['green'], .9)

    def test_parses_dark_blue_button_up_and_khaki_shorts(self):
        target = SearchPlanAgent.normalize_target(TargetConfiguration(
            free_text_description='look for someone with khaki shorts and dark blue button up shirt'))
        self.assertEqual(target.upper_clothing_color, 'dark blue')
        self.assertEqual(target.upper_clothing_type, 'button-up')
        self.assertEqual(target.lower_clothing_color, 'khaki')
        self.assertEqual(target.lower_clothing_type, 'shorts')

    def test_dark_blue_and_khaki_color_families(self):
        dark_blue, dark_blue_raw = color_match_score('dark blue', {'blue': .37, 'black': .16, 'white': .16, 'grey': .11})
        khaki, khaki_raw = color_match_score('khaki', {'beige': .49, 'brown': .07, 'white': .32, 'grey': .10})
        self.assertGreater(dark_blue, .65)
        self.assertGreater(khaki, .9)
        self.assertAlmostEqual(dark_blue_raw, .53)
        self.assertAlmostEqual(khaki_raw, .56)

    def test_khaki_request_is_evaluated_even_as_a_color_family(self):
        dets = [detection(t, color_features={
            'upper': {'blue': .45, 'black': .15, 'white': .15, 'grey': .1},
            'lower': {'beige': .49, 'brown': .08, 'white': .3, 'grey': .1},
        }) for t in (0, 1)]
        target = TargetConfiguration(upper_clothing_color='dark blue', lower_clothing_color='khaki')
        result = AppearanceAnalyzer.evaluate_track('test', 1, dets, target,
            SearchPlanAgent.create_search_plan(target), '.', detector=None)
        self.assertEqual(result.attributes['upper_clothing'].assessment, 'match')
        self.assertEqual(result.attributes['lower_clothing'].assessment, 'match')
        self.assertIn(result.classification, ('possible_match', 'strong_match'))

if __name__ == '__main__':
    unittest.main()
