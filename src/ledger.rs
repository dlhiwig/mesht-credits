use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, path::Path};

#[derive(Debug)]
pub enum LedgerError {
    Database(rusqlite::Error),
    Invalid(&'static str),
    Signature,
    Corrupt,
}
impl From<rusqlite::Error> for LedgerError {
    fn from(e: rusqlite::Error) -> Self {
        Self::Database(e)
    }
}
pub type Result<T> = std::result::Result<T, LedgerError>;

#[derive(Clone, Debug)]
pub struct Transfer {
    pub tx_id: String,
    pub sender: String,
    pub recipient: String,
    pub amount: i64,
    pub sequence: i64,
    pub timestamp: String,
    pub signature: [u8; 64],
}

// Versioned, unambiguous length-prefixed encoding. Never sign JSON serialization.
fn field(out: &mut Vec<u8>, value: &str) {
    out.extend_from_slice(&(value.len() as u32).to_be_bytes());
    out.extend_from_slice(value.as_bytes());
}
pub fn canonical_message(t: &Transfer) -> Vec<u8> {
    let mut out = b"mesht-credits/transfer/v1\0".to_vec();
    for v in [&t.tx_id, &t.sender, &t.recipient, &t.timestamp] {
        field(&mut out, v);
    }
    out.extend_from_slice(&t.amount.to_be_bytes());
    out.extend_from_slice(&t.sequence.to_be_bytes());
    out
}

pub struct Ledger {
    db: Connection,
}
impl Ledger {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let db = Connection::open(path)?;
        db.pragma_update(None, "foreign_keys", "ON")?;
        db.pragma_update(None, "journal_mode", "WAL")?;
        db.pragma_update(None, "synchronous", "FULL")?;
        db.execute_batch("
            CREATE TABLE IF NOT EXISTS members (
                id TEXT PRIMARY KEY, public_key BLOB NOT NULL CHECK(length(public_key)=32),
                credit_limit INTEGER NOT NULL CHECK(credit_limit>=0), frozen INTEGER NOT NULL DEFAULT 0 CHECK(frozen IN (0,1))
            );
            CREATE TABLE IF NOT EXISTS transfers (
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT, tx_id TEXT NOT NULL UNIQUE,
                sender TEXT NOT NULL REFERENCES members(id),
                recipient TEXT NOT NULL REFERENCES members(id),
                amount INTEGER NOT NULL CHECK(amount>0),
                sequence INTEGER NOT NULL CHECK(sequence>0),
                timestamp TEXT NOT NULL, signature BLOB NOT NULL CHECK(length(signature)=64),
                prev_hash BLOB NOT NULL CHECK(length(prev_hash)=32),
                entry_hash BLOB NOT NULL UNIQUE CHECK(length(entry_hash)=32),
                UNIQUE(sender,sequence), CHECK(sender<>recipient)
            );
        ")?;
        Ok(Self { db })
    }
    // Administrative enrollment is out-of-band in M1. Restrict access to the ledger database.
    pub fn enroll(&self, id: &str, key: &[u8; 32], credit_limit: i64) -> Result<()> {
        if id.is_empty() || credit_limit < 0 {
            return Err(LedgerError::Invalid("invalid member"));
        }
        self.db.execute(
            "INSERT INTO members(id,public_key,credit_limit) VALUES (?1,?2,?3)",
            params![id, key.as_slice(), credit_limit],
        )?;
        Ok(())
    }
    pub fn balance(&self, member: &str) -> Result<i64> {
        let exists: bool = self.db.query_row(
            "SELECT EXISTS(SELECT 1 FROM members WHERE id=?1)",
            [member],
            |r| r.get(0),
        )?;
        if !exists {
            return Err(LedgerError::Invalid("unknown member"));
        }
        let outgoing: i64 = self.db.query_row(
            "SELECT COALESCE(SUM(amount),0) FROM transfers WHERE sender=?1",
            [member],
            |r| r.get(0),
        )?;
        let incoming: i64 = self.db.query_row(
            "SELECT COALESCE(SUM(amount),0) FROM transfers WHERE recipient=?1",
            [member],
            |r| r.get(0),
        )?;
        incoming
            .checked_sub(outgoing)
            .ok_or(LedgerError::Invalid("balance overflow"))
    }
    pub fn apply(&mut self, t: &Transfer) -> Result<()> {
        if t.amount <= 0 || t.sequence <= 0 || t.sender == t.recipient || t.tx_id.is_empty() {
            return Err(LedgerError::Invalid("invalid transfer"));
        }
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let sender: Option<(Vec<u8>, i64, i64)> = tx
            .query_row(
                "SELECT public_key,credit_limit,frozen FROM members WHERE id=?1",
                [&t.sender],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .optional()?;
        let (key, limit, frozen) = sender.ok_or(LedgerError::Invalid("unknown sender"))?;
        let recipient_frozen: Option<i64> = tx
            .query_row(
                "SELECT frozen FROM members WHERE id=?1",
                [&t.recipient],
                |r| r.get(0),
            )
            .optional()?;
        if frozen != 0 || recipient_frozen != Some(0) {
            return Err(LedgerError::Invalid("frozen or unknown recipient"));
        }
        let key: [u8; 32] = key.try_into().map_err(|_| LedgerError::Corrupt)?;
        let vk = VerifyingKey::from_bytes(&key).map_err(|_| LedgerError::Signature)?;
        vk.verify(&canonical_message(t), &Signature::from_bytes(&t.signature))
            .map_err(|_| LedgerError::Signature)?;
        let prior: i64 = tx.query_row(
            "SELECT COALESCE(MAX(sequence),0) FROM transfers WHERE sender=?1",
            [&t.sender],
            |r| r.get(0),
        )?;
        if t.sequence
            != prior
                .checked_add(1)
                .ok_or(LedgerError::Invalid("sequence overflow"))?
        {
            return Err(LedgerError::Invalid("sequence mismatch"));
        }
        let balance = |id: &str| -> Result<i64> {
            let incoming: i64 = tx.query_row(
                "SELECT COALESCE(SUM(amount),0) FROM transfers WHERE recipient=?1",
                [id],
                |r| r.get(0),
            )?;
            let outgoing: i64 = tx.query_row(
                "SELECT COALESCE(SUM(amount),0) FROM transfers WHERE sender=?1",
                [id],
                |r| r.get(0),
            )?;
            incoming
                .checked_sub(outgoing)
                .ok_or(LedgerError::Invalid("balance overflow"))
        };
        let next_sender = balance(&t.sender)?
            .checked_sub(t.amount)
            .ok_or(LedgerError::Invalid("balance overflow"))?;
        balance(&t.recipient)?
            .checked_add(t.amount)
            .ok_or(LedgerError::Invalid("balance overflow"))?;
        if next_sender < -limit {
            return Err(LedgerError::Invalid("credit limit exceeded"));
        }
        let previous: Option<Vec<u8>> = tx
            .query_row(
                "SELECT entry_hash FROM transfers ORDER BY ordinal DESC LIMIT 1",
                [],
                |r| r.get(0),
            )
            .optional()?;
        let prev_hash = previous.unwrap_or_else(|| vec![0; 32]);
        let mut digest = Sha256::new();
        digest.update(b"mesht-credits/entry/v1\0");
        digest.update(&prev_hash);
        digest.update(canonical_message(t));
        digest.update(t.signature);
        let entry_hash = digest.finalize().to_vec();
        tx.execute("INSERT INTO transfers(tx_id,sender,recipient,amount,sequence,timestamp,signature,prev_hash,entry_hash) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
            params![t.tx_id,t.sender,t.recipient,t.amount,t.sequence,t.timestamp,t.signature.as_slice(),prev_hash,entry_hash])?;
        tx.commit()?;
        Ok(())
    }
    pub fn verify(&self) -> Result<()> {
        let mut stmt = self.db.prepare("SELECT tx_id,sender,recipient,amount,sequence,timestamp,signature,prev_hash,entry_hash FROM transfers ORDER BY ordinal")?;
        let mut rows = stmt.query([])?;
        let mut previous = vec![0u8; 32];
        let mut balances: BTreeMap<String, i128> = BTreeMap::new();
        let mut sequences: BTreeMap<String, i64> = BTreeMap::new();
        while let Some(row) = rows.next()? {
            let sig: Vec<u8> = row.get(6)?;
            let signature: [u8; 64] = sig.try_into().map_err(|_| LedgerError::Corrupt)?;
            let t = Transfer {
                tx_id: row.get(0)?,
                sender: row.get(1)?,
                recipient: row.get(2)?,
                amount: row.get(3)?,
                sequence: row.get(4)?,
                timestamp: row.get(5)?,
                signature,
            };
            let prev: Vec<u8> = row.get(7)?;
            let hash: Vec<u8> = row.get(8)?;
            if prev != previous || t.amount <= 0 || t.sender == t.recipient {
                return Err(LedgerError::Corrupt);
            }
            let key: Vec<u8> = self
                .db
                .query_row(
                    "SELECT public_key FROM members WHERE id=?1",
                    [&t.sender],
                    |r| r.get(0),
                )
                .map_err(|_| LedgerError::Corrupt)?;
            let key: [u8; 32] = key.try_into().map_err(|_| LedgerError::Corrupt)?;
            let vk = VerifyingKey::from_bytes(&key).map_err(|_| LedgerError::Corrupt)?;
            vk.verify(&canonical_message(&t), &Signature::from_bytes(&t.signature))
                .map_err(|_| LedgerError::Corrupt)?;
            let next = sequences
                .get(&t.sender)
                .copied()
                .unwrap_or(0)
                .checked_add(1)
                .ok_or(LedgerError::Corrupt)?;
            if t.sequence != next {
                return Err(LedgerError::Corrupt);
            }
            sequences.insert(t.sender.clone(), next);
            let mut digest = Sha256::new();
            digest.update(b"mesht-credits/entry/v1\0");
            digest.update(&previous);
            digest.update(canonical_message(&t));
            digest.update(t.signature);
            if digest.finalize().as_slice() != hash {
                return Err(LedgerError::Corrupt);
            }
            *balances.entry(t.sender).or_default() -= i128::from(t.amount);
            *balances.entry(t.recipient).or_default() += i128::from(t.amount);
            previous = hash;
        }
        if balances.values().sum::<i128>() != 0 {
            return Err(LedgerError::Corrupt);
        }
        Ok(())
    }
    pub fn count(&self) -> Result<i64> {
        Ok(self
            .db
            .query_row("SELECT COUNT(*) FROM transfers", [], |r| r.get(0))?)
    }
}
