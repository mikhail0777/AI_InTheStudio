"""One worker entrypoint with optional specialized verification modules."""
import json
import uuid

from app import database
from app.models.legacy_adapters import target_to_search_query, track_to_search_result
from app.models.schemas import TargetConfiguration
from app.services.agentic_loop import AgenticLoopManager, load_tracks
from app.services.generic_search import OpenVocabularySearchManager
from app.services.query_parser import StructuredQueryParser, should_use_generic_search


class UnifiedSearchManager:
    """Route providers behind one generic search/result contract."""

    @classmethod
    def execute_analysis(cls, session_id: str, target: TargetConfiguration, *, run_id: str, checkpoint):
        parsed = StructuredQueryParser().parse(target.free_text_description or "Locate a person.")
        if should_use_generic_search(parsed):
            return OpenVocabularySearchManager.execute_analysis(
                session_id, target, run_id=run_id, checkpoint=checkpoint,
            )
        # Person appearance remains a replaceable specialist verifier. Its detections and
        # evidence are adapted into the same SearchQuery/SearchResult persistence contract.
        AgenticLoopManager.execute_analysis(
            session_id, target, run_id=run_id, checkpoint=checkpoint,
        )
        return cls.publish_person_results(session_id)

    @staticmethod
    def publish_person_results(session_id: str):
        with database.get_db_connection() as conn:
            session = conn.execute(
                "SELECT target_config,status,search_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        if not session or session["status"] != "completed":
            raise RuntimeError("Person appearance analysis did not complete before result adaptation.")
        if session["search_id"]:
            from app.services.generic_search import load_search_results
            return load_search_results(session_id)
        target = TargetConfiguration(**json.loads(session["target_config"]))
        query = target_to_search_query(target)
        search_id = f"search_{uuid.uuid4().hex}"
        results = [track_to_search_result(track, search_id) for track in load_tracks(session_id)]
        with database.get_db_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO searches(search_id,session_id,status,processing_mode,query_json,
                   parser_provenance,started_at,finished_at) VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
                (search_id, session_id, "completed", query.processing_mode, query.model_dump_json(),
                 query.parser_provenance.model_dump_json() if query.parser_provenance else None),
            )
            conn.executemany(
                """INSERT INTO search_results(search_id,result_id,start_seconds,end_seconds,
                   classification,overall_score,payload,human_feedback,human_notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [(search_id, result.result_id, result.start_seconds, result.end_seconds,
                  result.classification, result.overall_score, result.model_dump_json(),
                  result.human_feedback, result.human_notes) for result in results],
            )
            conn.execute(
                "UPDATE sessions SET search_id=?,search_query=? WHERE session_id=?",
                (search_id, query.model_dump_json(), session_id),
            )
        AgenticLoopManager.log_agent_event(
            session_id, "RESULT_ADAPTER",
            f"Published {len(results)} person-appearance tracks through the generic result contract.",
            "action",
        )
        return results
