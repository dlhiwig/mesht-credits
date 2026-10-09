# M2 Python governance and local CLI (prototype)

This branch extends the existing Python `ledger.py`. It does **not** introduce radio transport or credit issuance. Governance changes are signed Ed25519 events with an independently hash-chained journal.

Install: `python -m pip install -r requirements.txt`. Test: `python -m unittest discover -v -p 'test*.py'`.

Example local flow:

```sh
python mesht_cli.py keygen admin.key
python mesht_cli.py keygen alice.key
python mesht_cli.py keygen bob.key
python mesht_cli.py --db demo.sqlite bootstrap-admin board PUBLIC_ADMIN_KEY
python mesht_cli.py --db demo.sqlite member-add board admin.key alice PUBLIC_ALICE_KEY 100
python mesht_cli.py --db demo.sqlite member-add board admin.key bob PUBLIC_BOB_KEY 100
python mesht_cli.py --db demo.sqlite transfer alice.key alice bob 10
python mesht_cli.py --db demo.sqlite member-freeze board admin.key alice
python mesht_cli.py --db demo.sqlite verify
```

Replace uppercase placeholders with public keys printed by `keygen`. Private key files must never be committed.

**Security limitations:** Enrollment bootstrap is trusted and not part of the signed event chain. The existing ledger has unsigned direct `enroll` and `set_credit_limit` methods, so filesystem/DB access must remain trusted. Freeze checking occurs before the parent `submit` transaction and is not concurrency-safe; serialize writes at the application boundary before deployment. The original transfer hash chain does not bind signatures, and neither journal has independently anchored checkpoints; historical deletion and direct SQL modification remain risks. Governance verification currently checks event signatures/hash links but does not replay state to detect unauthorized state changes. This is not suitable for production or real value. Issuance is deferred to preserve pure zero-sum mutual credit.
