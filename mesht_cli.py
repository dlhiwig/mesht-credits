"""Operator CLI for the Phase 4 Python node. Not a Meshtastic radio client."""

import argparse
import json

from ledger import Ledger, make_keypair, sign_governance, sign_tx
from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey


def load_key(path: str) -> SigningKey:
    raw = open(path, "rb").read().strip()
    return SigningKey(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="mesht-credits Phase 4 operator CLI")
    parser.add_argument("--db", default="mesht.db")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("keygen")
    enroll = sub.add_parser("enroll")
    enroll.add_argument("--id", required=True)
    enroll.add_argument("--public-key", required=True)
    enroll.add_argument("--limit", type=int, default=0)
    xfer = sub.add_parser("transfer")
    xfer.add_argument("--key", required=True)
    xfer.add_argument("--sender", required=True)
    xfer.add_argument("--recipient", required=True)
    xfer.add_argument("--amount", type=int, required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--admin-key", required=True)
    freeze.add_argument("--admin-id", required=True)
    freeze.add_argument("--member", required=True)
    sub.add_parser("reconcile")
    args = parser.parse_args()

    if args.command == "keygen":
        sk = SigningKey.generate()
        print(json.dumps({
            "public_key": sk.verify_key.encode(encoder=Base64Encoder).decode(),
            "private_key_b64": Base64Encoder.encode(sk.encode()).decode(),
        }))
        return

    ledger = Ledger(args.db)
    try:
        if args.command == "enroll":
            ledger.enroll(args.id, args.public_key, args.limit)
            print(f"enrolled {args.id}")
        elif args.command == "transfer":
            sk = load_key(args.key)
            seq = ledger.next_sequence(args.sender)
            tx = sign_tx(sk, args.sender, args.recipient, args.amount, seq)
            print(json.dumps(ledger.submit(tx)))
        elif args.command == "freeze":
            sk = load_key(args.admin_key)
            seq = ledger._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM governance_events WHERE admin_id = ?",
                (args.admin_id,),
            ).fetchone()["n"]
            event = sign_governance(sk, args.admin_id, "freeze", args.member, "", int(seq))
            pk = sk.verify_key.encode(encoder=Base64Encoder).decode()
            print(json.dumps(ledger.apply_governance(event, pk)))
        elif args.command == "reconcile":
            print(json.dumps(ledger.reconcile(), indent=2))
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
