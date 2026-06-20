import sqlite3

db = r'C:\Users\82102\AppData\Local\MYBOX\Accounts\folder_sync.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT id, sync_type, sync_on_off, local_base_path, server_base_prefix_path FROM sync_info_table")
rows = cur.fetchall()
print("MYBOX 동기화 폴더 설정:")
for r in rows:
    print(f"  id={r[0]}, type={r[1]}, on={r[2]}")
    print(f"  로컬 경로: {r[3]}")
    print(f"  서버 경로: {r[4]}")
    print()
conn.close()
