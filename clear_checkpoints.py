"""One-time script: clear stale autoloop checkpoints from Postgres."""
from dotenv import load_dotenv; load_dotenv()
from psycopg import Connection
from psycopg.rows import dict_row
import os

conn = Connection.connect(os.environ["POSTGRES_URI"], autocommit=True, row_factory=dict_row)
with conn.cursor() as cur:
    for tbl in ["ai.checkpoints", "ai.checkpoint_writes", "ai.checkpoint_blobs"]:
        try:
            cur.execute(f"DELETE FROM {tbl} WHERE thread_id LIKE 'autoloop%'")
            print(f"Cleared {tbl}: {cur.rowcount} rows")
        except Exception as e:
            print(f"Skip {tbl}: {e}")
conn.close()
print("Done.")
