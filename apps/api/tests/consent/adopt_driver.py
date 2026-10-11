"""Independent-process adopter for the P26 cross-process idempotency check.

It opens its own engine against the run-labelled database and adopts one reviewed
meaning through the owned public seam. It makes no provider, wallet or network
call.
"""

from __future__ import annotations

import argparse
import json
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from edge_os_api.consent.service import ConsentService
from edge_os_api.consent.types import AdoptionRequest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_url")
    parser.add_argument("owner_id")
    parser.add_argument("review_id")
    parser.add_argument("expected_review_hash")
    args = parser.parse_args()
    engine = create_engine(args.db_url)
    try:
        service = ConsentService(sessionmaker(engine, expire_on_commit=False))
        view = service.adopt(uuid.UUID(args.owner_id),
                             AdoptionRequest(review_id=args.review_id, expected_review_hash=args.expected_review_hash))
        print(json.dumps({"consent_hash": view.consent_hash, "status": view.status,
                          "adoption_id": str(view.adoption_id)}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
