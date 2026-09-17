import unittest

from app.services.query_parser import StructuredQueryParser, should_use_generic_search


class QueryParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = StructuredQueryParser()

    def test_yellow_car_is_required_generic_evidence(self):
        query = self.parser.parse("A yellow car")
        self.assertTrue(should_use_generic_search(query))
        self.assertEqual(query.entities[0].entity_type, "car")
        self.assertEqual(query.entities[0].attributes[0].value, "yellow")
        self.assertEqual(query.required_evidence_ids, ["car", "car.color"])

    def test_relationship_and_temporal_action_retain_participants(self):
        query = self.parser.parse("A woman pushing a stroller near a building")
        self.assertEqual(query.actions[0].action, "pushing")
        self.assertTrue(query.actions[0].requires_temporal_evidence)
        self.assertEqual(query.relationships[0].predicate, "near")
        self.assertIn(query.actions[0].criterion_id, query.required_evidence_ids)

    def test_unknown_query_is_not_silently_mapped_to_clothing(self):
        query = self.parser.parse("a mysterious glowing orb")
        self.assertFalse(query.entities)
        self.assertEqual(query.unsupported_concepts, ["a mysterious glowing orb"])

    def test_person_with_secondary_object_stays_on_legacy_pipeline(self):
        query = self.parser.parse("person carrying a blue backpack")
        self.assertFalse(should_use_generic_search(query))

    def test_person_stroller_interaction_uses_generic_pipeline(self):
        query = self.parser.parse("person pushing a stroller")
        self.assertTrue(should_use_generic_search(query))


if __name__ == "__main__":
    unittest.main()
