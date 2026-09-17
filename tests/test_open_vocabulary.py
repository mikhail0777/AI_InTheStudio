import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.models.legacy_adapters import target_to_search_query, track_to_search_result
from app.models.open_vocabulary import (
    ActionConstraint, AttributeConstraint, EntityMention, EventStep, RelationshipConstraint,
    SearchQuery,
)
from app.models.schemas import AttributeDetail, DetectionItem, TargetConfiguration, TrackResult


class OpenVocabularySchemaTests(unittest.TestCase):
    def test_multi_entity_temporal_query_round_trip(self):
        query = SearchQuery(
            original_text="A woman approaches a blue car, opens the door, and enters it",
            entities=[
                EntityMention(entity_id="person", name="woman", entity_type="person"),
                EntityMention(entity_id="car", name="car", entity_type="vehicle", attributes=[
                    AttributeConstraint(criterion_id="car.color", entity_id="car", name="color", value="blue")
                ]),
            ],
            relationships=[RelationshipConstraint(
                criterion_id="person.near.car", subject_entity_id="person", predicate="near", object_entity_id="car"
            )],
            actions=[ActionConstraint(
                criterion_id="person.enters.car", actor_entity_id="person", action="entering", object_entity_id="car"
            )],
            event_sequence=[
                EventStep(step_id="approach", order=0, description="approaches car", actor_entity_id="person", object_entity_id="car"),
                EventStep(step_id="enter", order=1, description="enters car", actor_entity_id="person", action="entering", object_entity_id="car"),
            ],
            required_evidence_ids=["person", "car", "car.color", "person.enters.car"],
            optional_evidence_ids=["person.near.car"],
        )
        restored = SearchQuery.model_validate_json(query.model_dump_json())
        self.assertEqual(restored.entities[1].attributes[0].value, "blue")
        self.assertTrue(restored.actions[0].requires_temporal_evidence)
        self.assertEqual([step.order for step in restored.event_sequence], [0, 1])

    def test_negative_constraint_is_explicit(self):
        query = SearchQuery(
            original_text="A person without a backpack",
            entities=[EntityMention(entity_id="person", name="person", attributes=[
                AttributeConstraint(criterion_id="person.backpack", entity_id="person", name="backpack",
                                    value="backpack", negative=True)
            ])],
            required_evidence_ids=["person", "person.backpack"],
        )
        self.assertTrue(query.entities[0].attributes[0].negative)

    def test_unknown_references_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown entity"):
            SearchQuery(
                original_text="dog beside bicycle",
                entities=[EntityMention(entity_id="dog", name="dog")],
                relationships=[RelationshipConstraint(
                    criterion_id="beside", subject_entity_id="dog", predicate="beside", object_entity_id="bicycle"
                )],
            )

    def test_legacy_clothing_query_uses_generic_evidence(self):
        query = target_to_search_query(TargetConfiguration(
            free_text_description="Person wearing a green shirt without a blue backpack",
            upper_clothing_color="green", backpack="without blue backpack",
        ))
        attributes = {item.name: item for item in query.entities[0].attributes}
        self.assertEqual(attributes["upper_clothing_color"].value, "green")
        self.assertTrue(attributes["backpack"].negative)
        self.assertIn("person.upper_clothing_color", query.required_evidence_ids)
        self.assertIn("person.backpack", query.required_evidence_ids)

    def test_legacy_track_maps_to_generic_result(self):
        observation = DetectionItem(
            detection_id="d1", frame_idx=10, timestamp_seconds=1, bbox=[0, 0, 10, 20],
            confidence=.9, quality_score=.8, detector_name="test-detector", model_version="1",
        )
        track = TrackResult(
            session_id="s", track_id=2, first_seen_seconds=1, last_seen_seconds=2,
            best_timestamp_seconds=1.5, classification="possible_match",
            person_detection_confidence=.9, appearance_similarity=.7, evidence_quality=.8,
            final_ranking_score=.75, observations_analyzed=1,
            attributes={"upper_clothing": AttributeDetail(
                expected="green", observed="green", score=.8, visibility="clear", assessment="match"
            )}, matching_evidence=["green"], conflicting_evidence=[], unknown_attributes=[],
            requires_human_review=True, explanation="Visible support", best_frame_path="/frame.jpg",
            model_version="1", evidence_observations=[observation],
        )
        result = track_to_search_result(track, "search-1")
        self.assertEqual(result.entities[0].label, "person")
        self.assertEqual(result.evidence[0].assessment, "supported")
        self.assertEqual(result.component_scores["attribute_agreement"], .7)


class OpenVocabularyMigrationTests(unittest.TestCase):
    def test_additive_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "test.db")
            with patch.object(database, "DB_DIR", directory), patch.object(database, "DB_PATH", path):
                database.init_db()
                database.init_db()
                with database.get_db_connection() as conn:
                    session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
                    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
                self.assertIn("search_query", session_columns)
                self.assertTrue({"searches", "search_results", "media_assets", "video_indexes",
                                 "scenes", "indexed_frames", "indexed_clips"}.issubset(tables))
                self.assertIn("results_by_rank", indexes)


if __name__ == "__main__":
    unittest.main()
