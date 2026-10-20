"""Operational commands: python -m app.cli <command>"""

import argparse
import json
import sys

from sqlalchemy import func, select

from app.db import session_factory
from app.models import User
from app.seed.loader import load_seed
from app.services.catalog import index_books
from app.services.embeddings import embedder_status, get_embedder


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shelfsense")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="load the bundled catalog (idempotent)")
    rb = sub.add_parser("rebuild-index", help="(re)compute embeddings")
    rb.add_argument("--force", action="store_true", help="re-embed every book")
    sub.add_parser("download-model", help="download/load the embedding model and report status")
    sub.add_parser("status", help="print embedding status")
    ma = sub.add_parser("make-admin", help="grant admin rights to an existing user")
    ma.add_argument("email")
    ev = sub.add_parser("evaluate", help="run retrieval evaluation and print metrics")
    ev.add_argument("-k", type=int, default=5)
    args = ap.parse_args(argv)

    if args.cmd == "download-model":
        e = get_embedder()
        st = embedder_status()
        print(json.dumps({"available": e is not None, "model": st.model, "reason": st.reason}, indent=2))
        return 0 if e else 1
    if args.cmd == "status":
        st = embedder_status()
        print(json.dumps(st.__dict__, indent=2))
        return 0
    with session_factory()() as db:
        if args.cmd == "seed":
            print(f"seeded {load_seed(db)} books")
            print(json.dumps(index_books(db)))
        elif args.cmd == "rebuild-index":
            res = index_books(db, force=args.force)
            print(json.dumps(res, indent=2))
            return 0 if res["status"] == "ok" else 1
        elif args.cmd == "make-admin":
            u = db.scalar(select(User).where(func.lower(User.email) == args.email.lower()))
            if not u:
                print("no such user", file=sys.stderr)
                return 1
            u.is_admin = True
            db.commit()
            print("ok")
        elif args.cmd == "evaluate":
            from app.services.evaluation import run_evaluation

            r = run_evaluation(db, k=args.k)
            for mode, v in r["modes"].items():
                print(mode, v["mean"])
            print("skipped:", r["skipped_modes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
