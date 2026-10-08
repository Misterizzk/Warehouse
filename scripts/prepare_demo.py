"""Prepare the provided demo master without overwriting an existing user database."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_windows import create_clean_install_database


def main():
    target = ROOT / 'data' / 'warehouse_demo.db'
    seed = ROOT / 'data_uji' / 'warehouse_demo_seed.db'
    if target.exists():
        print('Database sudah ada; data tetap dipertahankan:', target)
        return 0
    if not seed.is_file():
        raise SystemExit('Seed demo belum tersedia: ' + str(seed))
    create_clean_install_database(seed, target)
    print('Demo siap: 200 batch, 324 lokasi, riwayat petugas kosong.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
