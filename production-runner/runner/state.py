from __future__ import annotations
import csv
import io
import json
import sqlite3
from pathlib import Path
from .util import now, atomic_bytes

class Store:
    """Only the supervisor writes SQLite. Worker results are independent recoverable files."""
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'state.sqlite3',timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=DELETE'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks(case_id TEXT PRIMARY KEY, family TEXT NOT NULL, ordinal INTEGER, status TEXT NOT NULL, attempt TEXT, attempts INTEGER NOT NULL DEFAULT 0, detail TEXT, updated TEXT)')
        self.db.commit()
    def seed(self,tasks):
        with self.db:
            for i,t in enumerate(tasks):
                self.db.execute('INSERT OR IGNORE INTO tasks(case_id,family,ordinal,status,updated) VALUES(?,?,?,?,?)',
                                (t['case_id'],t['family'],i,'PENDING',now()))
    def set(self,case,status,attempt=None,attempts=None,detail=None):
        updates={'status':status,'updated':now()}
        if attempt is not None: updates['attempt']=attempt
        if attempts is not None: updates['attempts']=attempts
        if detail is not None: updates['detail']=json.dumps(detail,ensure_ascii=False)
        with self.db:
            self.db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in updates)+' WHERE case_id=?',tuple(updates.values())+(case,))
    def rows(self): return [dict(r) for r in self.db.execute('SELECT * FROM tasks ORDER BY ordinal')]
    def export(self):
        rows=self.rows()
        if not rows: return
        out=io.StringIO(newline=''); w=csv.DictWriter(out,rows[0].keys(),delimiter='\t',lineterminator='\n')
        w.writeheader(); w.writerows(rows); atomic_bytes(self.root/'tasks_status.tsv',out.getvalue().encode())
    def close(self): self.db.close()
