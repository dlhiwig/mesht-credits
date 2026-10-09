use ed25519_dalek::{Signer, SigningKey};
use mesht_credits::{canonical_message, Ledger, Transfer};
use tempfile::tempdir;

fn signed(
    key: &SigningKey,
    sender: &str,
    recipient: &str,
    amount: i64,
    sequence: i64,
    id: String,
) -> Transfer {
    let mut tx = Transfer {
        tx_id: id,
        sender: sender.into(),
        recipient: recipient.into(),
        amount,
        sequence,
        timestamp: "2026-10-09T16:00:00Z".into(),
        signature: [0; 64],
    };
    tx.signature = key.sign(&canonical_message(&tx)).to_bytes();
    tx
}
#[test]
fn hundred_transfers_and_recovery() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("ledger.sqlite");
    let a = SigningKey::from_bytes(&[7; 32]);
    let b = SigningKey::from_bytes(&[8; 32]);
    {
        let mut db = Ledger::open(&path).unwrap();
        db.enroll("alice", &a.verifying_key().to_bytes(), 1000)
            .unwrap();
        db.enroll("bob", &b.verifying_key().to_bytes(), 1000)
            .unwrap();
        for n in 1..=100 {
            let (key, sender, recipient, seq) = if n % 2 == 1 {
                (&a, "alice", "bob", (n + 1) / 2)
            } else {
                (&b, "bob", "alice", n / 2)
            };
            let tx = signed(key, sender, recipient, 5, seq, format!("transfer-{n}"));
            db.apply(&tx).unwrap();
            assert!(db.apply(&tx).is_err(), "duplicate accepted");
        }
        assert_eq!(db.balance("alice").unwrap(), 0);
        assert_eq!(db.balance("bob").unwrap(), 0);
        assert_eq!(db.count().unwrap(), 100);
        let over = signed(&a, "alice", "bob", 1001, 51, "overlimit".into());
        assert!(db.apply(&over).is_err());
        let invalid = signed(&b, "alice", "bob", 5, 51, "forged".into());
        assert!(db.apply(&invalid).is_err());
        assert_eq!(db.count().unwrap(), 100);
        db.verify().unwrap();
    }
    let db = Ledger::open(&path).unwrap();
    assert_eq!(db.count().unwrap(), 100);
    assert_eq!(db.balance("alice").unwrap() + db.balance("bob").unwrap(), 0);
    db.verify().unwrap();
}
#[test]
fn rollback_on_constraint_failure() {
    let mut db = Ledger::open(":memory:").unwrap();
    let key = SigningKey::from_bytes(&[9; 32]);
    db.enroll("a", &key.verifying_key().to_bytes(), 100)
        .unwrap();
    db.enroll("b", &key.verifying_key().to_bytes(), 100)
        .unwrap();
    let first = signed(&key, "a", "b", 10, 1, "same".into());
    db.apply(&first).unwrap();
    let second = signed(&key, "a", "b", 10, 2, "same".into());
    assert!(db.apply(&second).is_err());
    assert_eq!(db.count().unwrap(), 1);
    assert_eq!(db.balance("a").unwrap(), -10);
    db.verify().unwrap();
}
