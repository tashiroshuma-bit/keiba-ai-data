import datetime as dt
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from forward_integrity import audit
from validation import Ledger, canonical


class ForwardIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.sqlite"
        self.ledger = Ledger(str(self.path))

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def insert(self, *, late=False, wrong_hash=False):
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = now + dt.timedelta(minutes=(-1 if late else 10))
        off = now + dt.timedelta(minutes=20)
        p = dict(race_id="r1", deployment_status="experimental_rank_shadow",
                 cutoff_timestamp=cutoff.isoformat(), off_timestamp=off.isoformat(),
                 created_at=now.isoformat(), runners=[{"horse_number": 1}],
                 inputs={"runners": [{"horse_number": 1, "features_asof": now.isoformat()}]},
                 allocation={"bets": [], "stake_yen": 0}, model_artifact={"test": 1})
        raw = canonical(p)
        model_hash = hashlib.sha256(canonical(p["model_artifact"]).encode()).hexdigest()
        key = hashlib.sha256(("forward" + model_hash + raw).encode()).hexdigest()
        with self.ledger.db:
            self.ledger.db.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?)",
                                   (key if not wrong_hash else "bad", "r1", model_hash,
                                    "forward", now.isoformat(), raw))

    def test_valid_evidence(self):
        self.insert()
        self.assertEqual(audit(self.path)["eligible_forward_races"], 1)

    def test_late_is_rejected(self):
        self.insert(late=True)
        self.assertEqual(len(audit(self.path)["rejected"]), 1)

    def test_forged_hash_is_rejected(self):
        self.insert(wrong_hash=True)
        self.assertEqual(len(audit(self.path)["rejected"]), 1)

    def test_empty_is_not_forward(self):
        self.assertEqual(audit(self.path)["eligible_forward_races"], 0)


if __name__ == "__main__":
    unittest.main()
