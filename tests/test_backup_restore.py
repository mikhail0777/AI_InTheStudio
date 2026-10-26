import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app import database
from app.services import backup_restore,governance

class MemoryProtector:
    def protect(self,value):return json.dumps(value).encode()
    def unprotect(self,value):return json.loads(value.decode())

class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p1=patch.object(database,"DB_DIR",self.temp.name);self.p2=patch.object(database,"DB_PATH",str(Path(self.temp.name)/"lottrace.db"))
        self.p1.start();self.p2.start();self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop);database.init_db()
        _,self.user=governance.bootstrap("Backup Dealer","admin@example.com","Admin","correct horse battery staple")

    def test_encrypted_online_backup_is_validated_and_audited(self):
        evidence=Path(self.temp.name)/"evidence"/"case"/"frame.jpg";evidence.parent.mkdir(parents=True);evidence.write_bytes(b"evidence")
        result=backup_restore.create_backup(self.user,encrypt=True,protector=MemoryProtector())
        self.assertTrue(Path(result["path"]).is_file());self.assertTrue(result["encrypted"]);self.assertEqual(result["manifest"]["schema_version"],1)
        with database.get_db_connection() as conn:self.assertEqual(conn.execute("SELECT count(*) FROM audit_events WHERE action='backup.created'").fetchone()[0],1)

    def test_restore_stages_then_activates_with_rollback(self):
        backup=backup_restore.create_backup(self.user,encrypt=True,protector=MemoryProtector())
        with database.get_db_connection() as conn:conn.execute("UPDATE dealerships SET name='Changed' WHERE dealership_id=?",(self.user["dealership_id"],))
        staged=backup_restore.stage_restore(self.user,backup["path"],protector=MemoryProtector());self.assertEqual(staged["status"],"staged")
        applied=backup_restore.apply_pending_restore();self.assertTrue(Path(applied["rollback_database"]).is_file())
        with database.get_db_connection() as conn:
            self.assertEqual(conn.execute("SELECT name FROM dealerships").fetchone()[0],"Backup Dealer")
            self.assertEqual(conn.execute("SELECT count(*) FROM audit_events WHERE action='restore.activated'").fetchone()[0],1)

    def test_tampered_archive_is_rejected_without_pending_activation(self):
        backup=backup_restore.create_backup(self.user,encrypt=True,protector=MemoryProtector());path=Path(backup["path"]);path.write_bytes(path.read_bytes()[:-7]+b"garbage")
        with self.assertRaises(Exception):backup_restore.stage_restore(self.user,path,protector=MemoryProtector())
        self.assertFalse((Path(self.temp.name)/"pending_restore.json").exists())

if __name__=="__main__":unittest.main()
