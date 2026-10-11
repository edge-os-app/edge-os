"""Independent-process reader for the P26 consent durability check.

It opens its own engine against the run-labelled database and reads one adoption
row directly. It is read-only and makes no provider, wallet or network call.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import create_engine, text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_url")
    parser.add_argument("owner_id")
    parser.add_argument("review_id")
    args = parser.parse_args()
    engine = create_engine(args.db_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT consent_hash, status, review_hash FROM consent_local.consent_adoptions "
                "WHERE owner_id = CAST(:owner AS uuid) AND review_id = CAST(:review AS uuid)"),
                {"owner": args.owner_id, "review": args.review_id}).one()
        print(json.dumps({"consent_hash": row.consent_hash, "status": row.status, "review_hash": row.review_hash}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
