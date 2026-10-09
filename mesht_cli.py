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
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--out", required=True, help="New private key file; created with mode 0600")
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
    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--out", required=True, help="Write checkpoint JSON to file")
    sub.add_parser("reconcile")
    args = parser.parse_args()

    if args.command == "keygen":
        import os
        sk = SigningKey.generate()
        fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(sk.encode())
        print(json.dumps({
            "public_key": sk.verify_key.encode(encoder=Base64Encoder).decode(),
            "private_key_file": args.out,
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
        elif args.command == "checkpoint":
            import os
            cp = ledger.export_checkpoint()
            with open(args.out, "x", encoding="utf-8") as output:
                json.dump(cp, output, sort_keys=True, indent=2)
                output.write("\\n")
            print(json.dumps({"checkpoint_file": args.out, "checkpoint_hash": cp["checkpoint_hash"]}))
        elif args.command == "reconcile":
            print(json.dumps(ledger.reconcile(), indent=2))
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
