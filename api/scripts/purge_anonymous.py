"""Delete everything owned by the anonymous fallback user.

Run once now that real auth is live. Idempotent — prints how many rows went.

    docker exec folio-api-1 python3 /app/scripts/purge_anonymous.py

Children are deleted before parents (note_link -> note_block -> note_session)
via subqueries joined on user_id, so no uuid[] array cast is needed.
"""

import os

import psycopg2

ANON = "00000000-0000-0000-0000-000000000001"


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM note_link WHERE block_id IN ("
                "  SELECT b.id FROM note_block b"
                "  JOIN note_session s ON s.id = b.note_id"
                "  WHERE s.user_id = %s"
                ")",
                (ANON,),
            )

            cur.execute(
                "DELETE FROM note_block WHERE note_id IN ("
                "  SELECT id FROM note_session WHERE user_id = %s"
                ")",
                (ANON,),
            )

            cur.execute("DELETE FROM note_session WHERE user_id = %s", (ANON,))
            notes = cur.rowcount

            cur.execute("DELETE FROM coverage_event WHERE user_id = %s", (ANON,))
            coverage = cur.rowcount

            cur.execute("DELETE FROM qa_message WHERE user_id = %s", (ANON,))
            qa = cur.rowcount

        conn.commit()
        print(
            f"deleted anonymous rows: notes={notes} coverage_events={coverage} qa_messages={qa}"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
