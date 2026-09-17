import unittest

from app.models.open_vocabulary import EntityDetection, EntityTrack, ModelProvenance
from app.services.query_parser import StructuredQueryParser
from app.services.temporal_verifier import MultiFrameEvidenceVerifier


PROVENANCE = ModelProvenance(provider="test", model_name="test", model_version="1")


def track(track_id, label, boxes):
    detections = [EntityDetection(
        detection_id=f"{track_id}-{index}", frame_idx=index, timestamp_seconds=float(index),
        label=label, bbox=box, confidence=.9, provenance=PROVENANCE,
    ) for index, box in enumerate(boxes)]
    return EntityTrack(track_id=track_id, label=label, start_seconds=0,
                       end_seconds=float(len(boxes) - 1), detections=detections)


class TemporalVerifierTests(unittest.TestCase):
    def setUp(self):
        self.verifier = MultiFrameEvidenceVerifier()

    def test_unrelated_entities_do_not_become_an_interaction(self):
        query = StructuredQueryParser().parse("a dog near a bicycle")
        dog = track("dog:1", "dog", [[0, 0, 20, 20], [2, 0, 22, 20]])
        bike = track("bicycle:1", "bicycle", [[200, 0, 240, 40], [205, 0, 245, 40]])
        evidence = self.verifier.verify(query, [dog, bike])
        self.assertEqual(evidence[0].assessment, "conflicting")

    def test_repeated_proximity_supports_spatial_relationship(self):
        query = StructuredQueryParser().parse("a dog beside a bicycle")
        dog = track("dog:1", "dog", [[0, 0, 20, 20], [2, 0, 22, 20]])
        bike = track("bicycle:1", "bicycle", [[22, 0, 62, 40], [24, 0, 64, 40]])
        evidence = self.verifier.verify(query, [dog, bike])
        self.assertEqual(evidence[0].assessment, "supported")
        self.assertGreaterEqual(len(evidence[0].timestamps), 2)

    def test_single_frame_cannot_establish_temporal_action(self):
        query = StructuredQueryParser().parse("a dog running")
        evidence = self.verifier.verify(query, [track("dog:1", "dog", [[0, 0, 20, 20]])])
        self.assertEqual(evidence[0].assessment, "uncertain")

    def test_sustained_motion_can_support_running(self):
        query = StructuredQueryParser().parse("a dog running")
        dog = track("dog:1", "dog", [[0, 0, 20, 20], [20, 0, 40, 20], [40, 0, 60, 20]])
        evidence = self.verifier.verify(query, [dog])
        self.assertEqual(evidence[0].assessment, "supported")


if __name__ == "__main__":
    unittest.main()
