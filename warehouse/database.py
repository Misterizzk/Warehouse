"""Versioned demo storage. Never opens the legacy warehouse.db."""
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from .domain import location_code
from .runtime_paths import database_path

DEMO_PATH = database_path()
SCHEMA_VERSION = 7


def _backup_before_migration(db, path, version):
    """Keep a complete SQLite backup, including committed WAL content."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup_path = path.with_name(f'{path.name}.pre-v{version}-{stamp}.bak')
    backup = sqlite3.connect(backup_path)
    try:
        db.backup(backup)
    finally:
        backup.close()
    return backup_path


def _migrate_v4(db):
    """Replace the old 9-cell rack model, retaining batches and immutable history."""
    # SQLite cannot replace a table referenced by a foreign key while FK checks
    # are enabled. Disable them only for this transaction, then validate before
    # committing and restore the connection setting on every exit path.
    db.execute('PRAGMA foreign_keys=OFF')
    try:
        db.execute('BEGIN IMMEDIATE')
        old_locations = db.execute('SELECT code,area,rack,level,position FROM locations').fetchall()
        racks = sorted({(item['area'], item['rack']) for item in old_locations})
        for item in old_locations:
            if not (1 <= item['level'] <= 3 and 1 <= item['position'] <= 3):
                raise ValueError('Migrasi lokasi dibatalkan: ada tingkat atau posisi lama di luar 01–03.')

        db.execute('''CREATE TABLE locations_v4 (
            code TEXT PRIMARY KEY, area TEXT NOT NULL, rack TEXT NOT NULL,
            "column" INTEGER NOT NULL CHECK("column" BETWEEN 1 AND 3),
            "row" INTEGER NOT NULL CHECK("row" BETWEEN 1 AND 3),
            level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 3),
            UNIQUE(area,rack,"column","row",level))''')
        new_locations = [
            (location_code(area, rack, column, row, level), area, rack, column, row, level)
            for area, rack in racks
            for column in range(1, 4)
            for row in range(1, 4)
            for level in range(1, 4)
        ]
        db.executemany('''INSERT INTO locations_v4(code,area,rack,"column","row",level)
            VALUES(?,?,?,?,?,?)''', new_locations)

        db.execute('''CREATE TABLE batch_location_migration (
            batch_id TEXT PRIMARY KEY REFERENCES batches(id),
            old_location_code TEXT NOT NULL,
            new_location_code TEXT NOT NULL REFERENCES locations(code),
            migrated_at TEXT NOT NULL)''')
        old_batches = db.execute('''SELECT b.id,b.location_code,l.area,l.rack
            FROM batches b JOIN locations l ON l.code=b.location_code
            ORDER BY l.area,l.rack,b.id''').fetchall()
        total_batches = db.execute('SELECT COUNT(*) FROM batches').fetchone()[0]
        if len(old_batches) != total_batches:
            raise ValueError('Migrasi lokasi dibatalkan: ada batch tanpa lokasi lama yang valid.')
        migrated_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        rack_index = {}
        for item in old_batches:
            key = item['area'], item['rack']
            index = rack_index.get(key, 0)
            rack_index[key] = index + 1
            # Step 10 visits every section in the first nine batches, then
            # other tiers. 10 and 27 are coprime, so all addresses are visited.
            offset = (index * 10) % 27
            column, row, level = offset // 9 + 1, (offset % 9) // 3 + 1, offset % 3 + 1
            new_code = location_code(*key, column, row, level)
            db.execute('UPDATE batches SET location_code=? WHERE id=?', (new_code, item['id']))
            db.execute('''INSERT INTO batch_location_migration
                (batch_id,old_location_code,new_location_code,migrated_at) VALUES(?,?,?,?)''',
                (item['id'], item['location_code'], new_code, migrated_at))

        db.execute('DROP TABLE locations')
        db.execute('ALTER TABLE locations_v4 RENAME TO locations')
        db.execute('CREATE INDEX locations_area_rack ON locations(area,rack)')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Migrasi lokasi dibatalkan: relasi database tidak konsisten.')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Migrasi lokasi dibatalkan: integritas database gagal.')
        db.execute('PRAGMA user_version=4')
        db.execute('COMMIT')
    except Exception:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    finally:
        db.execute('PRAGMA foreign_keys=ON')


def _migrate_v7(db):
    """Add explicit site/customer decisions without losing completed v6 actions."""
    # SQLite cannot alter a CHECK constraint. Rebuild the constrained table
    # while its child completion rows remain in place, then validate every FK.
    db.execute('PRAGMA foreign_keys=OFF')
    try:
        db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE recommendation_decisions_v7 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                batch_id TEXT NOT NULL,
                physical_condition TEXT NOT NULL
                    CHECK(physical_condition IN ('Layak','Perlu evaluasi','Tidak layak')),
                choice TEXT NOT NULL CHECK(choice IN
                    ('Perlu dipindahkan','Prioritaskan pemakaian',
                     'Tunda evaluasi','Tidak perlu tindakan',
                     'Pindahkan ke site','Tawarkan ke customer')),
                reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000),
                officer TEXT NOT NULL CHECK(length(trim(officer)) BETWEEN 1 AND 100),
                decided_at TEXT NOT NULL,
                age_at_decision INTEGER NOT NULL CHECK(age_at_decision>=0),
                aging_status TEXT NOT NULL
                    CHECK(aging_status IN ('Normal','Warning','Melewati batas')),
                recommendation_snapshot TEXT NOT NULL CHECK(json_valid(recommendation_snapshot)),
                target_kind TEXT CHECK(target_kind IN ('site','customer')),
                target_code TEXT CHECK(target_code IS NULL OR length(trim(target_code)) BETWEEN 1 AND 100),
                CHECK(
                    (choice='Pindahkan ke site' AND target_kind='site' AND target_code IS NOT NULL)
                    OR (choice='Tawarkan ke customer' AND target_kind='customer' AND target_code IS NOT NULL)
                    OR (choice IN ('Perlu dipindahkan','Prioritaskan pemakaian',
                                  'Tunda evaluasi','Tidak perlu tindakan')
                        AND target_kind IS NULL AND target_code IS NULL)),
                UNIQUE(session_id,batch_id),
                FOREIGN KEY(session_id,batch_id) REFERENCES check_results(session_id,batch_id));
            INSERT INTO recommendation_decisions_v7
                (id,session_id,batch_id,physical_condition,choice,reason,officer,
                 decided_at,age_at_decision,aging_status,recommendation_snapshot)
                SELECT id,session_id,batch_id,physical_condition,choice,reason,officer,
                       decided_at,age_at_decision,aging_status,recommendation_snapshot
                FROM recommendation_decisions;
            DROP TABLE recommendation_decisions;
            ALTER TABLE recommendation_decisions_v7 RENAME TO recommendation_decisions;
            CREATE INDEX recommendation_decisions_batch
                ON recommendation_decisions(batch_id,decided_at DESC,id DESC);
            CREATE TRIGGER recommendation_draft_insert BEFORE INSERT ON recommendation_decisions
                WHEN (SELECT status FROM check_sessions WHERE id=NEW.session_id)!='Draft'
                BEGIN SELECT RAISE(ABORT,'Keputusan hanya dapat dibuat pada sesi Draft'); END;
            CREATE TRIGGER locked_recommendation_decision_update BEFORE UPDATE ON recommendation_decisions
                WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)!='Draft'
                  OR NEW.id!=OLD.id OR NEW.session_id!=OLD.session_id OR NEW.batch_id!=OLD.batch_id
                  OR EXISTS(SELECT 1 FROM recommendation_completions WHERE decision_id=OLD.id)
                BEGIN SELECT RAISE(ABORT,'Keputusan sesi selesai atau tindakan tuntas tidak dapat diubah'); END;
            CREATE TRIGGER locked_recommendation_decision_delete BEFORE DELETE ON recommendation_decisions
                BEGIN SELECT RAISE(ABORT,'Keputusan tidak dapat dihapus'); END;
        ''')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Migrasi keputusan dibatalkan: relasi database tidak konsisten.')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Migrasi keputusan dibatalkan: integritas database gagal.')
        db.execute('PRAGMA user_version=7')
        db.execute('COMMIT')
    except Exception:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    finally:
        db.execute('PRAGMA foreign_keys=ON')


def connect(path=DEMO_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError("Database berasal dari aplikasi yang lebih baru.")
        if version == 0:
            # Refuse to reinterpret an existing unrelated database.
            if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError("Database bukan database demo Warehouse Check.")
            db.executescript('''
                BEGIN;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE locations (
                    code TEXT PRIMARY KEY, area TEXT NOT NULL, rack TEXT NOT NULL,
                    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99),
                    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 99),
                    UNIQUE(area,rack,level,position));
                CREATE TABLE batches (
                    id TEXT PRIMARY KEY, material TEXT NOT NULL CHECK(length(trim(material))>0),
                    description TEXT NOT NULL, plant TEXT NOT NULL, storage_location TEXT NOT NULL,
                    location_code TEXT NOT NULL REFERENCES locations(code),
                    received_date TEXT NOT NULL, stock INTEGER NOT NULL CHECK(stock>=0));
                CREATE INDEX batches_location ON batches(location_code);
                INSERT INTO metadata VALUES ('mode','demo');
                PRAGMA user_version=1;
                COMMIT;
            ''')
        mode = db.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()
        if not mode or mode[0] != "demo":
            raise ValueError("File ini bukan database demo.")
        if 0 < version < SCHEMA_VERSION:
            _backup_before_migration(db, path, version)
        if version < 2:
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE check_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    officer TEXT NOT NULL CHECK(length(trim(officer)) BETWEEN 1 AND 100),
                    area TEXT NOT NULL CHECK(length(trim(area)) BETWEEN 1 AND 100),
                    started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft','Selesai')),
                    normal_max INTEGER NOT NULL CHECK(normal_max>=0),
                    age_limit INTEGER NOT NULL CHECK(age_limit>normal_max),
                    note TEXT NOT NULL DEFAULT '',
                    CHECK((status='Draft' AND finished_at IS NULL) OR (status='Selesai' AND finished_at IS NOT NULL)));
                CREATE TABLE check_results (
                    session_id INTEGER NOT NULL REFERENCES check_sessions(id),
                    batch_id TEXT NOT NULL REFERENCES batches(id),
                    checked_at TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    age INTEGER NOT NULL CHECK(age>=0),
                    status TEXT NOT NULL CHECK(status IN ('Normal','Warning','Melewati batas')),
                    note TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(session_id,batch_id));
                CREATE TRIGGER locked_session_update BEFORE UPDATE ON check_sessions
                    WHEN OLD.status='Selesai' BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_session_delete BEFORE DELETE ON check_sessions
                    WHEN OLD.status='Selesai' BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_result_insert BEFORE INSERT ON check_results
                    WHEN (SELECT status FROM check_sessions WHERE id=NEW.session_id)='Selesai'
                    BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_result_update BEFORE UPDATE ON check_results
                    WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)='Selesai'
                      OR (SELECT status FROM check_sessions WHERE id=NEW.session_id)='Selesai'
                    BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER locked_result_delete BEFORE DELETE ON check_results
                    WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)='Selesai'
                    BEGIN SELECT RAISE(ABORT,'Sesi sudah terkunci'); END;
                CREATE TRIGGER finish_requires_results BEFORE UPDATE OF status ON check_sessions
                    WHEN NEW.status='Selesai' AND NOT EXISTS(SELECT 1 FROM check_results WHERE session_id=OLD.id)
                    BEGIN SELECT RAISE(ABORT,'Sesi kosong belum dapat diselesaikan'); END;
                PRAGMA user_version=2;
                COMMIT;
            ''')
        if version < 3:
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE stock_movements (
                    id TEXT PRIMARY KEY CHECK(id GLOB 'OUT-*' AND length(id)=36),
                    batch_id TEXT NOT NULL REFERENCES batches(id),
                    occurred_on TEXT NOT NULL CHECK(length(occurred_on)=10),
                    recorded_at TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity BETWEEN 1 AND 999999999),
                    stock_before INTEGER NOT NULL CHECK(typeof(stock_before)='integer' AND stock_before>=0),
                    stock_after INTEGER NOT NULL CHECK(typeof(stock_after)='integer' AND stock_after>=0),
                    officer TEXT NOT NULL CHECK(length(trim(officer)) BETWEEN 1 AND 100),
                    note TEXT NOT NULL DEFAULT '' CHECK(length(note)<=2000),
                    snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
                    CHECK(stock_before-stock_after=quantity));
                CREATE INDEX stock_movements_batch ON stock_movements(batch_id);
                CREATE INDEX stock_movements_recorded ON stock_movements(recorded_at DESC);
                CREATE TRIGGER locked_movement_update BEFORE UPDATE ON stock_movements
                    BEGIN SELECT RAISE(ABORT,'Riwayat barang keluar tidak dapat diubah'); END;
                CREATE TRIGGER locked_movement_delete BEFORE DELETE ON stock_movements
                    BEGIN SELECT RAISE(ABORT,'Riwayat barang keluar tidak dapat dihapus'); END;
                PRAGMA user_version=3;
                COMMIT;
            ''')
        if version < 4:
            _migrate_v4(db)
        if version < 5:
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE recommendation_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    batch_id TEXT NOT NULL,
                    physical_condition TEXT NOT NULL
                        CHECK(physical_condition IN ('Layak','Perlu evaluasi','Tidak layak')),
                    choice TEXT NOT NULL CHECK(choice IN
                        ('Perlu dipindahkan','Prioritaskan pemakaian',
                         'Tunda evaluasi','Tidak perlu tindakan')),
                    reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000),
                    officer TEXT NOT NULL CHECK(length(trim(officer)) BETWEEN 1 AND 100),
                    decided_at TEXT NOT NULL,
                    age_at_decision INTEGER NOT NULL CHECK(age_at_decision>=0),
                    aging_status TEXT NOT NULL
                        CHECK(aging_status IN ('Normal','Warning','Melewati batas')),
                    recommendation_snapshot TEXT NOT NULL CHECK(json_valid(recommendation_snapshot)),
                    UNIQUE(session_id,batch_id),
                    FOREIGN KEY(session_id,batch_id) REFERENCES check_results(session_id,batch_id));
                CREATE INDEX recommendation_decisions_batch
                    ON recommendation_decisions(batch_id,decided_at DESC,id DESC);
                CREATE TABLE recommendation_completions (
                    decision_id INTEGER PRIMARY KEY REFERENCES recommendation_decisions(id),
                    officer TEXT NOT NULL CHECK(length(trim(officer)) BETWEEN 1 AND 100),
                    completed_at TEXT NOT NULL,
                    note TEXT NOT NULL CHECK(length(trim(note)) BETWEEN 1 AND 2000));
                CREATE TRIGGER recommendation_draft_insert BEFORE INSERT ON recommendation_decisions
                    WHEN (SELECT status FROM check_sessions WHERE id=NEW.session_id)!='Draft'
                    BEGIN SELECT RAISE(ABORT,'Keputusan hanya dapat dibuat pada sesi Draft'); END;
                CREATE TRIGGER locked_recommendation_decision_update BEFORE UPDATE ON recommendation_decisions
                    WHEN (SELECT status FROM check_sessions WHERE id=OLD.session_id)!='Draft'
                      OR NEW.id!=OLD.id OR NEW.session_id!=OLD.session_id OR NEW.batch_id!=OLD.batch_id
                      OR EXISTS(SELECT 1 FROM recommendation_completions WHERE decision_id=OLD.id)
                    BEGIN SELECT RAISE(ABORT,'Keputusan sesi selesai atau tindakan tuntas tidak dapat diubah'); END;
                CREATE TRIGGER locked_recommendation_decision_delete BEFORE DELETE ON recommendation_decisions
                    BEGIN SELECT RAISE(ABORT,'Keputusan tidak dapat dihapus'); END;
                CREATE TRIGGER locked_recommendation_completion_update BEFORE UPDATE ON recommendation_completions
                    BEGIN SELECT RAISE(ABORT,'Penyelesaian tidak dapat diubah'); END;
                CREATE TRIGGER locked_recommendation_completion_delete BEFORE DELETE ON recommendation_completions
                    BEGIN SELECT RAISE(ABORT,'Penyelesaian tidak dapat dihapus'); END;
                PRAGMA user_version=5;
                COMMIT;
            ''')
        if version < 6:
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE site_demand (
                    material TEXT NOT NULL CHECK(length(trim(material))>0),
                    site TEXT NOT NULL CHECK(site IN ('A','B','C')),
                    demand_prev INTEGER NOT NULL CHECK(typeof(demand_prev)='integer' AND demand_prev>=0),
                    demand_now INTEGER NOT NULL CHECK(typeof(demand_now)='integer' AND demand_now>=0),
                    open_demand INTEGER NOT NULL CHECK(typeof(open_demand)='integer' AND open_demand>=0),
                    site_stock INTEGER NOT NULL CHECK(typeof(site_stock)='integer' AND site_stock>=0),
                    PRIMARY KEY(material,site));
                CREATE TABLE material_unit_compatibility (
                    material TEXT NOT NULL CHECK(length(trim(material))>0),
                    unit_model TEXT NOT NULL CHECK(length(trim(unit_model))>0),
                    PRIMARY KEY(material,unit_model));
                CREATE TABLE customer_demand (
                    customer TEXT NOT NULL CHECK(customer IN ('A','B','C')),
                    unit_model TEXT NOT NULL CHECK(length(trim(unit_model))>0),
                    open_demand INTEGER NOT NULL CHECK(typeof(open_demand)='integer' AND open_demand>=0),
                    PRIMARY KEY(customer,unit_model));
                CREATE INDEX compatibility_unit_model ON material_unit_compatibility(unit_model);
                PRAGMA user_version=6;
                COMMIT;
            ''')
        if version < 7:
            _migrate_v7(db)
        return db
    except Exception:
        db.close()
        raise


def seed_demo(db, today=None):
    """Atomic and idempotent; dates never shift when the app is reopened."""
    today = today or date.today()
    names = ["LAMP ASSY", "HOSE ASSY", "MOTOR HOUSING", "SENSOR MODULE", "VALVE BODY",
             "OIL FILTER", "AIR FILTER", "BEARING", "SEAL KIT", "HYDRAULIC PUMP"]
    with db:
        if db.execute("SELECT value FROM metadata WHERE key='seed_date'").fetchone():
            return
        for area in ("A", "B"):
            for rack in ("B01", "B02", "B03"):
                for column in range(1, 4):
                    for row in range(1, 4):
                        for level in range(1, 4):
                            code = location_code(area, rack, column, row, level)
                            db.execute('''INSERT INTO locations(code,area,rack,"column","row",level)
                                VALUES(?,?,?,?,?,?)''', (code,area,rack,column,row,level))
        locations = [r[0] for r in db.execute("SELECT code FROM locations ORDER BY code")]
        ages = [i % 31 for i in range(25)] + [31 + i * 4 for i in range(15)] + [91 + i * 17 for i in range(10)]
        for i, age in enumerate(ages):
            db.execute("INSERT INTO batches VALUES(?,?,?,?,?,?,?,?)", (
                f"DEMO-{i+1:04d}", f"MAT-{i%10+1:03d}", names[i%10], "BHT", "PBHT",
                locations[(i*7)%len(locations)], (today-timedelta(days=age)).isoformat(), 1+(i*3)%20))
        db.execute("INSERT INTO metadata VALUES('seed_date',?)", (today.isoformat(),))
