"""`/applications` — saved jobs and application tracking.

What this pins down:

* the endpoints are private: no bearer token, no rows, and one candidate can
  never see or touch another's;
* saving is idempotent by `posting_id`, and re-saving can never reset a stage the
  candidate has already advanced past;
* the row is a *snapshot* — every field the Jobs page showed is stored and read
  back, because the live posting it came from can vanish;
* the stage vocabulary in `services.application_service` and the literal in the
  request schema agree, so a status cannot be storage-valid but API-invalid.

Isolation (throwaway SQLite) comes from `tests.harness`.
"""
import unittest
from typing import get_args

from tests.harness import client, signup  # noqa: F401  (isolation first)

from app import schemas  # noqa: E402
from database import db  # noqa: E402
from services import application_service  # noqa: E402


def posting(**overrides) -> dict:
    """A posting snapshot exactly as the Jobs page would send it."""
    payload = {
        "posting_id": "arbeitnow:kubernetes-platform-engineer",
        "title": "Kubernetes Platform Engineer",
        "company": "Conflux",
        "location": "Berlin, Germany",
        "remote": False,
        "employment_type": "full-time",
        "salary_text": "EUR 80000-100000 / annual",
        "published": "2026-10-01",
        "url": "https://arbeitnow.com/jobs/kubernetes-platform-engineer",
        "source": "arbeitnow",
    }
    payload.update(overrides)
    return payload


def save(headers: dict, **overrides):
    return client.post("/applications", json=posting(**overrides), headers=headers)


def backdate(application_id: int, when: str) -> None:
    """Moves a row's `updated_at` into the past, so ordering is testable."""
    conn = db.get_connection()
    with conn:
        conn.execute(
            "UPDATE saved_jobs SET updated_at = ? WHERE id = ?;", (when, application_id)
        )
    conn.close()


class AuthRequiredTests(unittest.TestCase):
    def test_every_endpoint_is_private(self):
        self.assertEqual(client.get("/applications").status_code, 401)
        self.assertEqual(client.post("/applications", json=posting()).status_code, 401)
        self.assertEqual(
            client.patch("/applications/1", json={"status": "applied"}).status_code, 401
        )
        self.assertEqual(client.delete("/applications/1").status_code, 401)


class SavingTests(unittest.TestCase):
    def setUp(self):
        self.headers = signup()

    def test_a_saved_posting_comes_back_with_its_snapshot(self):
        response = save(self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["posting_id"], "arbeitnow:kubernetes-platform-engineer")
        self.assertEqual(body["title"], "Kubernetes Platform Engineer")
        self.assertEqual(body["company"], "Conflux")
        self.assertEqual(body["location"], "Berlin, Germany")
        self.assertFalse(body["remote"])
        self.assertEqual(body["employment_type"], "full-time")
        self.assertEqual(body["salary_text"], "EUR 80000-100000 / annual")
        self.assertEqual(body["published"], "2026-10-01")
        self.assertTrue(body["url"].startswith("https://"))
        self.assertEqual(body["source"], "arbeitnow")
        self.assertEqual(body["status"], "saved")
        self.assertEqual(body["note"], "")
        self.assertTrue(body["created_at"])

    def test_the_remote_flag_survives_the_round_trip(self):
        body = save(self.headers, remote=True).json()
        self.assertIs(body["remote"], True)
        self.assertIs(client.get("/applications", headers=self.headers).json()["results"][0]["remote"], True)

    def test_saving_twice_is_a_no_op_that_answers_200(self):
        first = save(self.headers)
        again = save(self.headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200, "an existing row is not a new resource")
        self.assertEqual(first.json()["id"], again.json()["id"])
        listed = client.get("/applications", headers=self.headers).json()
        self.assertEqual(listed["count"], 1, "saving twice must not duplicate the row")

    def test_saving_again_cannot_reset_an_advanced_stage(self):
        application_id = save(self.headers).json()["id"]
        client.patch(
            f"/applications/{application_id}",
            json={"status": "interview", "note": "Second round on Tuesday."},
            headers=self.headers,
        )

        again = save(self.headers)

        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["status"], "interview", "the candidate's stage is theirs")
        self.assertEqual(again.json()["note"], "Second round on Tuesday.")

    def test_a_posting_can_be_filed_directly_at_a_stage(self):
        body = save(self.headers, status="applied").json()
        self.assertEqual(body["status"], "applied")

    def test_the_snapshot_is_required_to_be_a_posting(self):
        self.assertEqual(
            client.post("/applications", json={}, headers=self.headers).status_code, 422
        )
        self.assertEqual(save(self.headers, title="").status_code, 422)
        self.assertEqual(save(self.headers, posting_id="").status_code, 422)
        self.assertEqual(save(self.headers, status="dreaming").status_code, 422)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.headers = signup()
        self.application_id = save(self.headers).json()["id"]
        self.url = f"/applications/{self.application_id}"

    def patch(self, **payload):
        return client.patch(self.url, json=payload, headers=self.headers)

    def test_a_status_change_moves_the_stage_and_restamps_the_row(self):
        backdate(self.application_id, "2020-01-01 00:00:00")
        created_at = client.get("/applications", headers=self.headers).json()["results"][0][
            "created_at"
        ]

        body = self.patch(status="applied").json()

        self.assertEqual(body["status"], "applied")
        self.assertNotEqual(body["updated_at"], "2020-01-01 00:00:00", "a move is activity")
        self.assertEqual(body["created_at"], created_at, "the filing date is history, not state")

    def test_the_stages_run_the_whole_way_to_rejected(self):
        for stage in ("applied", "interview", "offer", "rejected"):
            body = self.patch(status=stage).json()
            self.assertEqual(body["status"], stage)

    def test_a_note_edit_leaves_the_stage_alone(self):
        self.patch(status="interview")
        body = self.patch(note="They asked for salary expectations.").json()
        self.assertEqual(body["note"], "They asked for salary expectations.")
        self.assertEqual(body["status"], "interview", "editing a note is not a stage change")

    def test_a_note_can_be_cleared_again(self):
        self.patch(note="Typo'd note")
        body = self.patch(note="").json()
        self.assertEqual(body["note"], "", "an empty note is a real edit, not a missing field")

    def test_status_and_note_can_move_together(self):
        body = self.patch(status="offer", note="Verbal offer, written to follow.").json()
        self.assertEqual((body["status"], body["note"]), ("offer", "Verbal offer, written to follow."))

    def test_sending_nothing_to_change_is_a_400(self):
        response = self.patch()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.patch(status="decided").status_code, 422)

    def test_an_unknown_row_is_a_404(self):
        self.assertEqual(
            client.patch(
                "/applications/999999", json={"status": "applied"}, headers=self.headers
            ).status_code,
            404,
        )


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.mine = signup()
        self.theirs = signup()

    def test_two_candidates_can_save_the_same_posting(self):
        ours = save(self.mine)
        yours = save(self.theirs)

        self.assertEqual(ours.status_code, 201)
        self.assertEqual(yours.status_code, 201, "each candidate files their own row")
        self.assertNotEqual(ours.json()["id"], yours.json()["id"])
        self.assertEqual(client.get("/applications", headers=self.theirs).json()["count"], 1)

    def test_a_list_never_carries_someone_elses_rows(self):
        save(self.theirs, posting_id="himalayas:product-designer", title="Product Designer")
        save(self.mine)

        listed = client.get("/applications", headers=self.mine).json()

        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["results"][0]["title"], "Kubernetes Platform Engineer")

    def test_another_candidates_row_cannot_be_moved(self):
        theirs = save(self.theirs).json()["id"]

        response = client.patch(
            f"/applications/{theirs}", json={"status": "offer"}, headers=self.mine
        )

        self.assertEqual(response.status_code, 404, "not 403: existence itself is private")
        still_theirs = client.get("/applications", headers=self.theirs).json()["results"][0]
        self.assertEqual(still_theirs["status"], "saved")

    def test_another_candidates_row_cannot_be_deleted(self):
        theirs = save(self.theirs).json()["id"]

        self.assertEqual(client.delete(f"/applications/{theirs}", headers=self.mine).status_code, 404)
        self.assertEqual(client.get("/applications", headers=self.theirs).json()["count"], 1)


class DeleteTests(unittest.TestCase):
    def test_deleting_removes_the_row_and_a_second_delete_is_a_404(self):
        headers = signup()
        application_id = save(headers).json()["id"]

        self.assertEqual(client.delete(f"/applications/{application_id}", headers=headers).status_code, 204)
        self.assertEqual(client.get("/applications", headers=headers).json()["count"], 0)
        self.assertEqual(client.delete(f"/applications/{application_id}", headers=headers).status_code, 404)


class OrderingTests(unittest.TestCase):
    def test_the_page_puts_the_most_recently_touched_row_first(self):
        """`updated_at` drives the order, so a just-moved application rises."""
        headers = signup()
        old = save(headers, posting_id="a:old", title="Old Role").json()["id"]
        new = save(headers, posting_id="b:new", title="New Role").json()["id"]

        backdate(old, "2020-01-01 00:00:00")
        titles = [row["title"] for row in client.get("/applications", headers=headers).json()["results"]]
        self.assertEqual(titles, ["New Role", "Old Role"])

        backdate(new, "2019-01-01 00:00:00")
        titles = [row["title"] for row in client.get("/applications", headers=headers).json()["results"]]
        self.assertEqual(titles, ["Old Role", "New Role"], "the order follows activity, not id")


class VocabularyTests(unittest.TestCase):
    def test_the_request_schema_accepts_every_status_the_service_stores(self):
        self.assertEqual(
            set(get_args(schemas.ApplicationStatus)),
            set(application_service.STATUSES),
            "a status must not be storable but unaskable, or vice versa",
        )

    def test_every_stage_is_accepted_end_to_end(self):
        headers = signup()
        for index, stage in enumerate(application_service.STATUSES):
            response = save(
                headers, posting_id=f"arbeitnow:role-{index}", title=f"Role {index}", status=stage
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["status"], stage)

    def test_the_service_refuses_a_status_it_does_not_know(self):
        with self.assertRaises(ValueError):
            application_service.save_application(1, posting(status="dreaming"))
        with self.assertRaises(ValueError):
            application_service.update_application(1, 1, status="dreaming")


if __name__ == "__main__":
    unittest.main()
