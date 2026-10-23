"""Check Windows Python -> WSL PostgreSQL -> pgvector without storing real chunks.

Uses a temporary table with synthetic vectors. This tests connectivity and vector
operations, not the accuracy of an embedding model. Connection settings are read
only from this sandbox's .env, leaving the main application's configuration alone.
"""

import argparse
import json
from pathlib import Path


def check_database(env_file: Path) -> dict:
    import psycopg
    from psycopg.types.json import Jsonb
    from pgvector import Vector
    from pgvector.psycopg import register_vector
    from dotenv import dotenv_values

    if not env_file.is_file():
        raise ValueError("Sandbox .env is missing. See .env.example for the database settings.")
    config = dotenv_values(env_file)
    required = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]
    if any(not config.get(key) for key in required):
        raise ValueError("Sandbox .env must contain host, port, database, user and password.")
    try:
        with psycopg.connect(
            host=config["PGHOST"], port=int(config["PGPORT"]),
            dbname=config["PGDATABASE"], user=config["PGUSER"], password=config["PGPASSWORD"],
            connect_timeout=int(config.get("PGCONNECT_TIMEOUT", "5")),
            application_name="santio-vector-database-check",
        ) as connection:
            register_vector(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user, version()")
                database, user, server = cursor.fetchone()
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                extension = cursor.fetchone()
                if extension is None:
                    raise RuntimeError("pgvector is not enabled in this database.")
                cursor.execute("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user")
                superuser, create_db, create_role = cursor.fetchone()
                cursor.execute("SELECT current_schema()")
                schema = cursor.fetchone()[0]
                cursor.execute("""
                    CREATE TEMP TABLE santio_vector_check (
                        id text PRIMARY KEY,
                        embedding vector(384) NOT NULL,
                        metadata jsonb NOT NULL
                    ) ON COMMIT DROP
                """)
                query = [1.0] + [0.0] * 383
                orthogonal = [0.0, 1.0] + [0.0] * 382
                opposite = [-1.0] + [0.0] * 383
                metadata = {"purpose": "synthetic database check", "pages": [1],
                            "source_refs": ["#/texts/0"]}
                for name, values in [("same", query), ("orthogonal", orthogonal), ("opposite", opposite)]:
                    cursor.execute("INSERT INTO santio_vector_check VALUES (%s, %s, %s)",
                                   (name, Vector(values), Jsonb(metadata)))
                cursor.execute("""
                    SELECT id, embedding <=> %s AS cosine_distance, metadata,
                           vector_dims(embedding)
                    FROM santio_vector_check ORDER BY cosine_distance
                """, (Vector(query),))
                rows = cursor.fetchall()
                if [row[0] for row in rows] != ["same", "orthogonal", "opposite"]:
                    raise RuntimeError("Synthetic cosine-distance ranking did not match expectations.")
                if any(row[2] != metadata or row[3] != 384 for row in rows):
                    raise RuntimeError("Vector dimension or JSON metadata round-trip failed.")
                expected_distances = [0.0, 1.0, 2.0]
                if any(abs(row[1] - value) > 1e-6 for row, value in zip(rows, expected_distances)):
                    raise RuntimeError("Synthetic cosine distances did not match expectations.")
            report = {
                "status": "PASS", "host": config["PGHOST"], "port": int(config["PGPORT"]),
                "database": database, "user": user, "default_schema": schema,
                "server": server, "pgvector_version": extension[0],
                "application_role": {"superuser": superuser, "create_database": create_db,
                                     "create_role": create_role},
                "checks": ["Windows Python TCP connection to WSL PostgreSQL",
                           "384-dimensional vector insert/read", "JSON source metadata round-trip",
                           "exact cosine-distance ranking with known synthetic vectors"],
                "test_rows": [{"id": row[0], "cosine_distance": row[1]} for row in rows],
                "temporary_test_table_only": True, "real_chunks_indexed": 0,
                "embedding_model_loaded": False,
            }
        # The transaction commits here, dropping the ON COMMIT DROP test table.
        return report
    except Exception as exc:
        # Connection strings/passwords never appear in normal output or reports.
        message = str(exc).replace(config["PGPASSWORD"], "[redacted]")
        raise RuntimeError(message) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).parent / ".env")
    parser.add_argument("--report", type=Path, help="Optional path for a report without credentials")
    args = parser.parse_args()
    try:
        report = check_database(args.env_file)
    except Exception as exc:
        print(f"Database check failed: {exc}", flush=True)
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
