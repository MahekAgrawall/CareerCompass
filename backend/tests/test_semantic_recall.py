"""Semantic recall: the vector index decides *which* roles get scored.

The contract these tests pin down:

* embeddings are deterministic and hermetic (no key, no network, stable across
  processes, so an index built by one process stays valid for another);
* the index is optional — with no index the matcher behaves exactly as before;
* when an index exists it can only ever *add* candidates, never remove one;
* scoring and explanation stay untouched, so a role found purely by meaning
  still has to earn a non-zero score on real skills.

Isolation (throwaway database) comes from `tests.harness`.
"""
import contextlib
import hashlib
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.harness import client  # noqa: F401  (isolation must load first)

from scripts import ingest_roles  # noqa: E402
from services import career_service, embeddings, vector_store  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = "Semantic search over the role catalog"

DETERMINISM_SCRIPT = """
import hashlib, struct, sys
sys.path.insert(0, sys.argv[1])
from services import embeddings
vector = embeddings.embed_query(sys.argv[2])
print(hashlib.sha256(struct.pack(f"<{len(vector)}f", *vector)).hexdigest())
"""


def digest_of(vector):
    return hashlib.sha256(struct.pack(f"<{len(vector)}f", *vector)).hexdigest()


def fixture_role(role_id, title, interests, skills, description=""):
    """A minimal role that satisfies both the matcher and the index document."""
    return {
        "id": role_id,
        "title": title,
        "category": "Test",
        "niche_category": "Test",
        "description": description or f"{title} works on {', '.join(skills)}.",
        "responsibilities": [f"Work all day with {skill}" for skill in skills],
        "growth_path": [title, f"Senior {title}"],
        "skills": {"must_have": list(skills), "good_to_have": [], "can_have": []},
        "matching_interests": list(interests),
        "matching_skills": list(skills),
    }


DEVOPS_FIXTURE = fixture_role(
    "fixture_devops",
    "Cloud DevOps Engineer",
    ["Cloud, DevOps & Linux"],
    ["Docker", "Kubernetes", "Linux", "AWS"],
    "Runs container platforms and deployment pipelines on cloud infrastructure.",
)
DESIGN_FIXTURE = fixture_role(
    "fixture_designer",
    "Product Designer",
    ["UI/UX & Frontend Experiences"],
    ["Figma", "Problem Solving"],
    "Runs user interviews, usability studies and Figma wireframes for product teams.",
)
EMBEDDED_FIXTURE = fixture_role(
    "fixture_embedded",
    "Embedded Firmware Engineer",
    ["Coding & Problem Solving"],
    ["C", "C++", "Linux"],
    "Writes bare-metal C firmware and RTOS drivers for microcontroller boards.",
)


class _IndexBackedTest(unittest.TestCase):
    """Runs the test against a throwaway vector index, then puts the env back."""

    def setUp(self):
        self._previous = {
            key: os.environ.get(key)
            for key in ("QDRANT_PATH", "QDRANT_URL", "EMBEDDING_PROVIDER", "GEMINI_API_KEY")
        }
        self._tmp = tempfile.mkdtemp(prefix="careercompass_qdrant_")
        os.environ["EMBEDDING_PROVIDER"] = "local"
        os.environ["QDRANT_PATH"] = os.path.join(self._tmp, "index")
        os.environ.pop("QDRANT_URL", None)
        vector_store.reset_clients()
        self.addCleanup(self._restore)

    def _restore(self):
        vector_store.reset_clients()
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)


class EmbeddingTests(unittest.TestCase):
    """The local embedder is what CI and offline development run on."""

    def test_embeddings_are_deterministic_and_normalised(self):
        first = embeddings.embed_query("Kubernetes, Docker and Linux")
        second = embeddings.embed_query("Kubernetes, Docker and Linux")
        self.assertEqual(len(first), embeddings.EMBEDDING_DIM)
        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(value * value for value in first), 1.0, places=6)

    def test_vectors_are_identical_in_another_process(self):
        """A salted `hash()` would silently invalidate every stored vector."""
        expected = digest_of(embeddings.embed_query(TEXT))
        result = subprocess.run(
            [sys.executable, "-c", DETERMINISM_SCRIPT, ROOT, TEXT],
            capture_output=True, text=True, cwd=ROOT,
            env={**os.environ, "EMBEDDING_PROVIDER": "local"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)

    def test_related_text_is_closer_than_unrelated_text(self):
        query = embeddings.embed_query("cloud infrastructure, containers and linux servers")
        related = embeddings.embed_query("Kubernetes, Docker, Linux, AWS, Terraform")
        unrelated = embeddings.embed_query("user interviews, usability studies and Figma wireframes")
        self.assertGreater(
            embeddings.cosine(query, related),
            embeddings.cosine(query, unrelated),
        )

    def test_unrelated_text_falls_below_the_local_recall_floor(self):
        """The floor is calibrated against this embedder, so it must separate."""
        cloud = embeddings.embed_query("Kubernetes, Docker, Linux, AWS, Terraform")
        design = embeddings.embed_query("user interviews, usability studies, Figma wireframes")
        self.assertLess(
            embeddings.cosine(cloud, design),
            career_service.SEMANTIC_FLOOR["local"],
        )

    def test_signature_names_the_provider_and_dimension(self):
        self.assertEqual(embeddings.active_provider(), "local", "tests must never call Gemini")
        self.assertEqual(embeddings.signature(), f"local-{embeddings.EMBEDDING_DIM}")


class ProviderResolutionTests(unittest.TestCase):
    """Which embedding space gets used is decided, and recorded, on purpose.

    A collection is only comparable with vectors from the same provider *and*
    model, so the API has to read whichever one the migration actually built.
    """

    def setUp(self):
        self._previous = {
            key: os.environ.get(key)
            for key in ("QDRANT_PATH", "QDRANT_URL", "EMBEDDING_PROVIDER", "GEMINI_API_KEY")
        }
        self._tmp = tempfile.mkdtemp(prefix="careercompass_provider_")
        os.environ["QDRANT_PATH"] = self._tmp
        os.environ.pop("QDRANT_URL", None)
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_a_gemini_key_alone_selects_gemini(self):
        os.environ.pop("EMBEDDING_PROVIDER", None)
        os.environ["GEMINI_API_KEY"] = "not-a-real-key"
        self.assertEqual(embeddings.active_provider(), "gemini")

    def test_the_ingested_index_outranks_a_later_key(self):
        """Adding a key after an offline ingest must not orphan the index."""
        os.environ.pop("EMBEDDING_PROVIDER", None)
        os.environ["GEMINI_API_KEY"] = "not-a-real-key"
        embeddings.record_provider("local")
        self.assertEqual(embeddings.active_provider(), "local")

    def test_an_explicit_setting_beats_the_recorded_index(self):
        embeddings.record_provider("local")
        os.environ["GEMINI_API_KEY"] = "not-a-real-key"
        os.environ["EMBEDDING_PROVIDER"] = "gemini"
        self.assertEqual(embeddings.active_provider(), "gemini")

    def test_a_recorded_gemini_index_without_a_key_falls_back_to_local(self):
        embeddings.record_provider("gemini")
        os.environ.pop("EMBEDDING_PROVIDER", None)
        os.environ.pop("GEMINI_API_KEY", None)
        self.assertEqual(embeddings.active_provider(), "local")

    def test_each_gemini_model_gets_its_own_vector_space(self):
        os.environ.pop("EMBEDDING_PROVIDER", None)
        os.environ["GEMINI_API_KEY"] = "not-a-real-key"
        os.environ["GEMINI_EMBEDDING_MODEL"] = "models/gemini-embedding-001"
        self.addCleanup(os.environ.pop, "GEMINI_EMBEDDING_MODEL", None)
        first = embeddings.signature()
        os.environ["GEMINI_EMBEDDING_MODEL"] = "models/text-embedding-004"
        second = embeddings.signature()
        self.assertNotEqual(first, second, "two models must never share a collection")
        self.assertIn("gemini", first)
        self.assertIn(str(embeddings.EMBEDDING_DIM), first)


class DocumentTests(unittest.TestCase):
    def test_role_document_carries_the_signals_a_candidate_would_use(self):
        document = vector_store.role_document(DEVOPS_FIXTURE)
        for expected in ("Cloud DevOps Engineer", "Kubernetes", "Cloud, DevOps & Linux"):
            self.assertIn(expected, document)

    def test_profile_query_includes_skills_and_the_free_text_goal(self):
        query = vector_store.profile_query({
            "interests": ["Cloud, DevOps & Linux"],
            "current_skills": ["Docker"],
            "career_goal": "Build self-driving car software",
        })
        self.assertIn("Docker", query)
        self.assertIn("self-driving", query)


class SemanticIndexTests(_IndexBackedTest):
    def test_search_returns_nothing_without_an_index(self):
        self.assertFalse(vector_store.is_available())
        self.assertEqual(vector_store.semantic_search("cloud infrastructure"), [])

    def test_indexing_makes_the_closest_role_win(self):
        written = vector_store.upsert_roles([DEVOPS_FIXTURE, DESIGN_FIXTURE, EMBEDDED_FIXTURE])
        self.assertEqual(written, 3)
        hits = vector_store.semantic_search(
            "cloud infrastructure, containers and deployment pipelines", limit=3
        )
        self.assertEqual(hits[0][0], "fixture_devops")
        self.assertGreater(hits[0][1], hits[-1][1])

    def test_reindexing_updates_instead_of_duplicating(self):
        vector_store.upsert_roles([DEVOPS_FIXTURE, DESIGN_FIXTURE])
        vector_store.upsert_roles([DEVOPS_FIXTURE, DESIGN_FIXTURE])
        status = vector_store.index_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["points"], 2)

    def test_rebuild_starts_from_a_clean_collection(self):
        vector_store.upsert_roles([DEVOPS_FIXTURE, DESIGN_FIXTURE, EMBEDDED_FIXTURE])
        vector_store.rebuild([DEVOPS_FIXTURE])
        self.assertEqual(vector_store.index_status()["points"], 1)

    def test_status_reports_the_embedding_space_it_belongs_to(self):
        status = vector_store.index_status()
        self.assertEqual(status["provider"], "local")
        self.assertIn(embeddings.signature(), status["collection"])


class SemanticRecallTests(_IndexBackedTest):
    """Recall may add candidates; it must never change a score.

    These run against real catalog roles (indexed into a throwaway index), so
    the matcher resolves them exactly as it does in production.
    """

    def index_catalog_roles(self, *role_ids):
        roles = [r for r in career_service.get_all_roles() if r["id"] in role_ids]
        self.assertEqual(len(roles), len(role_ids), "unknown role id in the fixture")
        vector_store.upsert_roles(roles)
        return roles

    def test_meaning_only_roles_join_the_results(self):
        """A role matching on skill but not on a single interest chip still lands."""
        self.index_catalog_roles("sre_platform_engineer")
        profile = {
            "interests": ["UI/UX & Frontend Experiences"],
            "current_skills": ["Docker", "Kubernetes", "Linux"],
        }
        by_id = {m["role"]["id"]: m for m in career_service.match_roles_smart(profile)}

        frontend = by_id["frontend_dev"]
        self.assertEqual(frontend["recalled_by"], ["keyword"])
        self.assertIsNone(frontend["semantic_similarity"], "not in the index, so no similarity")

        infra = by_id["sre_platform_engineer"]
        self.assertEqual(infra["recalled_by"], ["semantic"], "found by meaning, not by chip overlap")
        self.assertEqual(infra["matched_interests"], [])
        self.assertEqual(infra["interest_score"], 0)
        self.assertGreater(infra["score"], 0, "a meaning-only role still has to score on skills")
        self.assertGreater(infra["semantic_similarity"], 0)

    def test_meaning_only_suggestions_are_capped_and_saturated(self):
        """When the index has more to offer than the cap allows, the cap bites."""
        vector_store.upsert_roles(career_service.get_all_roles())
        profile = {
            "interests": ["Quantum Computing Hardware"],  # no catalog chip overlaps this
            "current_skills": ["Python", "SQL / MySQL / PostgreSQL", "Docker", "Excel Modeling"],
        }
        results = career_service.match_roles_smart(profile)
        meaning_only = [m for m in results if m["recalled_by"] == ["semantic"]]

        self.assertEqual(
            len(meaning_only), career_service.SEMANTIC_EXTRA_LIMIT,
            "the index offered more neighbours than the cap, so exactly the cap should surface",
        )

    def test_index_entries_missing_from_the_catalog_are_ignored(self):
        """A stale index must not resurrect a role that no longer exists."""
        vector_store.upsert_roles([
            fixture_role("fixture_ghost", "Ghost Role", ["Cloud, DevOps & Linux"], ["Docker"])
        ])
        profile = {"interests": ["Cybersecurity & Ethical Hacking"], "current_skills": ["Docker"]}
        ids = [m["role"]["id"] for m in career_service.match_roles_smart(profile)]
        self.assertNotIn("fixture_ghost", ids)

    def test_without_an_index_matching_stays_keyword_only(self):
        profile = {"interests": ["UI/UX & Frontend Experiences"], "current_skills": ["Figma"]}
        results = career_service.match_roles_smart(profile)
        self.assertTrue(results, "the catalog must still match on keywords alone")
        self.assertTrue(all(m["recalled_by"] == ["keyword"] for m in results))
        self.assertTrue(all(m["semantic_similarity"] is None for m in results))

    def test_recall_does_not_disturb_the_arithmetic(self):
        vector_store.upsert_roles(career_service.get_all_roles())
        profile = {
            "interests": ["UI/UX & Frontend Experiences", "Cloud, DevOps & Linux"],
            "current_skills": ["Docker", "Kubernetes", "Linux"],
        }
        matches = career_service.match_roles_smart(profile)
        self.assertTrue(any(m["recalled_by"] == ["semantic"] for m in matches))
        for match in matches:
            expected = (
                match["interest_score"] * career_service.INTEREST_WEIGHT
                + match["skill_score"] * career_service.SKILL_WEIGHT
                + 50
            ) // 100
            with self.subTest(role=match["role"]["id"]):
                self.assertEqual(match["score"], max(0, min(100, expected)))


class IngestMigrationTests(_IndexBackedTest):
    def test_the_migration_indexes_the_whole_catalog(self):
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = ingest_roles.main([])
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            vector_store.index_status()["points"],
            len(career_service.get_all_roles()),
        )
        self.assertTrue(vector_store.search_titles("deployment pipelines and containers", limit=5))

    def test_the_migration_falls_back_to_the_offline_embedder(self):
        """A configured but broken Gemini must not leave the app with no index.

        The fallback is only worth anything if the API reads the result, so the
        choice has to be recorded and the resolver has to honour it.
        """
        os.environ.pop("EMBEDDING_PROVIDER", None)
        os.environ["GEMINI_API_KEY"] = "not-a-real-key"

        def unavailable(*args, **kwargs):
            raise embeddings.EmbeddingError("quota exceeded")

        with mock.patch.object(embeddings, "_gemini_vectors", side_effect=unavailable):
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                exit_code = ingest_roles.main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("Falling back", captured.getvalue())
        self.assertEqual(embeddings.active_provider(), "local")
        self.assertEqual(
            vector_store.index_status()["points"],
            len(career_service.get_all_roles()),
        )


class SemanticApiTests(_IndexBackedTest):
    """The API has to publish how each role was recalled, honestly."""

    def test_match_publishes_the_recall_stage(self):
        response = client.post("/match", json={
            "interests": ["Coding & Problem Solving"],
            "current_skills": ["Python"],
            "explain": False,
        })
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(results)
        for match in results:
            self.assertIn("recalled_by", match)
            self.assertIn("semantic_similarity", match)
            self.assertIn("keyword", match["recalled_by"])

    def test_health_reports_the_semantic_index(self):
        status = client.get("/health").json()["semantic_index"]
        self.assertEqual(status["provider"], "local")
        self.assertIn("collection", status)
        self.assertIn("points", status)


if __name__ == "__main__":
    unittest.main()
