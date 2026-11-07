import sqlite3
from datetime import datetime, timezone
from .config import DB_PATH

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    return db

SCHEMA = '''
CREATE TABLE IF NOT EXISTS knowledge(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,content TEXT NOT NULL,source_url TEXT,topic TEXT,confidence REAL DEFAULT .5,created_at TEXT NOT NULL,embedding TEXT,verification_status TEXT DEFAULT 'unverified',source_domain TEXT,embedding_kind TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,objective TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,notes TEXT DEFAULT '',priority INTEGER DEFAULT 5,parent_id INTEGER,mode TEXT DEFAULT 'assisted',attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY AUTOINCREMENT,url TEXT UNIQUE NOT NULL,title TEXT,visited_at TEXT NOT NULL,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims(id INTEGER PRIMARY KEY AUTOINCREMENT,claim TEXT NOT NULL,task_id INTEGER,created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',support_count INTEGER DEFAULT 0,details TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS evaluations(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER,score REAL NOT NULL,coverage REAL,source_diversity REAL,verification REAL,issues TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,patch TEXT DEFAULT '',status TEXT DEFAULT 'proposed',test_result TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(id INTEGER PRIMARY KEY AUTOINCREMENT,proposal_id INTEGER,name TEXT,result TEXT,passed INTEGER DEFAULT 0,log TEXT DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,content TEXT NOT NULL,importance REAL DEFAULT .5,created_at TEXT NOT NULL,embedding TEXT,embedding_kind TEXT);
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER,step TEXT NOT NULL,status TEXT DEFAULT 'pending',position INTEGER,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS repos(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,source TEXT NOT NULL,kind TEXT DEFAULT 'github',branch TEXT,status TEXT DEFAULT 'queued',file_count INTEGER DEFAULT 0,chunk_count INTEGER DEFAULT 0,languages TEXT DEFAULT '',summary TEXT DEFAULT '',architecture TEXT DEFAULT '',meta TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS repo_files(id INTEGER PRIMARY KEY AUTOINCREMENT,repo_id INTEGER NOT NULL,path TEXT NOT NULL,language TEXT,size INTEGER DEFAULT 0,sha TEXT,content TEXT,summary TEXT,symbols TEXT,created_at TEXT NOT NULL,UNIQUE(repo_id,path));
CREATE TABLE IF NOT EXISTS repo_chunks(id INTEGER PRIMARY KEY AUTOINCREMENT,repo_id INTEGER NOT NULL,file_id INTEGER,path TEXT NOT NULL,start_line INTEGER,end_line INTEGER,content TEXT NOT NULL,embedding TEXT,embedding_kind TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL DEFAULT 'New conversation',provider TEXT,model TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id INTEGER NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,meta TEXT DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,detail TEXT DEFAULT '',allowed INTEGER DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tool_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,tool TEXT NOT NULL,args TEXT DEFAULT '',result TEXT DEFAULT '',status TEXT DEFAULT 'ok',created_at TEXT NOT NULL);
'''

INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge(topic);
CREATE INDEX IF NOT EXISTS idx_claims_task ON claims(task_id);
CREATE INDEX IF NOT EXISTS idx_repo_files_repo ON repo_files(repo_id);
CREATE INDEX IF NOT EXISTS idx_repo_chunks_repo ON repo_chunks(repo_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(id);
'''

# Every value used by the UI/backend. Keeping them in one place makes upgrades safe.
DEFAULTS = {
    'model': 'qwen2.5:3b',
    'embedding_model': 'nomic-embed-text',
    'mode': 'assisted',
    'max_pages_per_task': '8',
    'request_delay_seconds': '3',
    'allowed_domains': '',
    'autonomous_enabled': 'false',
    'research_interval_seconds': '45',
    'num_ctx': '8192',
    'num_predict': '900',
    'num_thread': '0',
    'keep_alive': '10m',
    'auto_resume': 'true',
    'resume_on_boot': 'false',
    'verification_sources': '2',
    'deep_research_pages': '15',
    # providers -----------------------------------------------------------------
    'provider': 'nexus',
    'embedding_provider': 'auto',
    'ollama_url': 'http://localhost:11434',
    'llamacpp_model_path': '',
    'llamacpp_n_ctx': '4096',
    'llamacpp_n_gpu_layers': '0',
    'openai_base_url': 'http://localhost:1234/v1',
    'openai_api_key': '',
    'openai_model': '',
    # repository learning -------------------------------------------------------
    'max_repo_files': '1500',
    'max_repo_file_kb': '256',
    'max_repo_mb': '300',
    'repo_chunk_lines': '80',
    'repo_chunk_overlap': '12',
    # permissions (default closed) ---------------------------------------------
    'permission_internet': 'false',
    'permission_pc_read': 'false',
    'permission_pc_write': 'false',
    'permission_shell': 'false',
    'allowed_roots': '',
    'allowed_commands': '',
    # chat ----------------------------------------------------------------------
    'chat_history': '14',
    'system_name': 'NEXUS',
}

def init_db():
    with connect() as db:
        db.executescript(SCHEMA)
        db.executescript(INDEXES)
        # Migrate databases created by earlier NEXUS builds.
        for table, columns in {
            'knowledge': [('embedding', 'TEXT'), ('verification_status', "TEXT DEFAULT 'unverified'"),
                          ('source_domain', 'TEXT'), ('embedding_kind', 'TEXT')],
            'tasks': [('priority', 'INTEGER DEFAULT 5'), ('parent_id', 'INTEGER'),
                      ('mode', "TEXT DEFAULT 'assisted'"), ('attempts', 'INTEGER DEFAULT 0')],
            'memories': [('embedding_kind', 'TEXT')],
        }.items():
            existing = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
            for name, typ in columns:
                if name not in existing:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {typ}')
        for k, v in DEFAULTS.items():
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))

def event(kind, message):
    with connect() as db:
        db.execute('INSERT INTO events(kind,message,created_at) VALUES(?,?,?)', (kind, message, now()))

def setting(key, default=None):
    with connect() as db:
        r = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if r is not None:
            return r['value']
    return DEFAULTS.get(key, default)

def set_setting(key, value):
    with connect() as db:
        db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

def get_settings(keys=None):
    if keys is None:
        return dict(DEFAULTS)
    return {k: setting(k) for k in keys}

def read_bool(key, default=False):
    return setting(key, 'true' if default else 'false').lower() == 'true'

def read_int(key, default=0):
    try:
        return int(setting(key, str(default)))
    except (TypeError, ValueError):
        return default

def audit(action, detail='', allowed=True):
    with connect() as db:
        db.execute('INSERT INTO audit_log(action,detail,allowed,created_at) VALUES(?,?,?,?)',
                   (action, detail[:4000], 1 if allowed else 0, now()))
