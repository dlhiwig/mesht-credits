"""Local operator CLI. Signing keys remain in user-controlled files."""
import argparse
import base64
import json
from pathlib import Path
from nacl.signing import SigningKey
from ledger import make_keypair, sign_tx
from governance import GovernedLedger, sign_event

def key(path):
    return SigningKey(base64.b64decode(Path(path).read_text().strip(), validate=True))

def main():
    parser = argparse.ArgumentParser(description="mesht-credits local prototype CLI")
    parser.add_argument("--db", default="credits.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("keygen")
    p.add_argument("file")
    p = sub.add_parser("bootstrap-admin")
    p.add_argument("admin"); p.add_argument("public_key")
    p = sub.add_parser("member-add")
    p.add_argument("admin"); p.add_argument("keyfile"); p.add_argument("member")
    p.add_argument("public_key"); p.add_argument("limit", type=int)
    p = sub.add_parser("member-limit")
    p.add_argument("admin"); p.add_argument("keyfile"); p.add_argument("member")
    p.add_argument("limit", type=int)
    for command in ("member-freeze", "member-unfreeze"):
        p = sub.add_parser(command)
        p.add_argument("admin"); p.add_argument("keyfile"); p.add_argument("member")
    p = sub.add_parser("transfer")
    p.add_argument("keyfile"); p.add_argument("sender"); p.add_argument("recipient")
    p.add_argument("amount", type=int)
    p = sub.add_parser("balance"); p.add_argument("member")
    sub.add_parser("verify")
    sub.add_parser("history")
    args = parser.parse_args()
    if args.command == "keygen":
        signing_key, public_key = make_keypair()
        path = Path(args.file)
        with path.open("x") as out:
            out.write(base64.b64encode(bytes(signing_key)).decode() + "\n")
        path.chmod(0o600)
        print(public_key)
        return
    db = GovernedLedger(args.db)
    try:
        if args.command == "bootstrap-admin":
            db.bootstrap_admin(args.admin, args.public_key)
            print("admin bootstrapped")
        elif args.command.startswith("member-"):
            action = {"member-add": "enroll", "member-limit": "limit",
                      "member-freeze": "freeze", "member-unfreeze": "unfreeze"}[args.command]
            value = (f"{args.public_key},{args.limit}" if action == "enroll"
                     else str(args.limit) if action == "limit" else "")
            event = sign_event(key(args.keyfile), args.admin, action, args.member, value)
            print(db.admin_apply(event))
        elif args.command == "transfer":
            tx = sign_tx(key(args.keyfile), args.sender, args.recipient,
                         args.amount, db.next_sequence(args.sender))
            print(json.dumps(db.submit(tx), indent=2))
        elif args.command == "balance":
            print(db.get_balance(args.member))
        elif args.command == "verify":
            result = {"ledger": db.verify_chain(), "governance": db.verify_governance(),
                      "zero_sum": db.system_sum() == 0}
            print(json.dumps(result))
            if not all(result.values()):
                raise SystemExit(1)
        elif args.command == "history":
            rows = db._conn.execute("SELECT tx_id,sender,recipient,amount,sequence,timestamp FROM transactions ORDER BY rowid").fetchall()
            print(json.dumps([dict(r) for r in rows], indent=2))
    finally:
        db.close()

if __name__ == "__main__":
    main()
