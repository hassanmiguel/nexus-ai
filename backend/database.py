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
CREATE TABLE IF NOT EXISTS web_sources(id INTEGER PRIMARY KEY AUTOINCREMENT,url TEXT NOT NULL,final_url TEXT,title TEXT,topic TEXT DEFAULT 'web',status TEXT DEFAULT 'queued',depth INTEGER DEFAULT 0,root_id INTEGER,char_count INTEGER DEFAULT 0,chunk_count INTEGER DEFAULT 0,summary TEXT DEFAULT '',meta TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS web_chunks(id INTEGER PRIMARY KEY AUTOINCREMENT,source_id INTEGER NOT NULL,url TEXT,title TEXT,ordinal INTEGER DEFAULT 0,content TEXT NOT NULL,embedding TEXT,embedding_kind TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skills(id INTEGER PRIMARY KEY AUTOINCREMENT,skill_id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,description TEXT DEFAULT '',category TEXT DEFAULT 'general',tags TEXT DEFAULT '',triggers TEXT DEFAULT '',bundles TEXT DEFAULT '',content TEXT DEFAULT '',source TEXT DEFAULT '',source_path TEXT DEFAULT '',enabled INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skill_imports(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,status TEXT DEFAULT 'queued',imported INTEGER DEFAULT 0,skipped INTEGER DEFAULT 0,detail TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,topic TEXT NOT NULL,mode TEXT DEFAULT 'topic',status TEXT DEFAULT 'running',started_at TEXT NOT NULL,updated_at TEXT NOT NULL,finished_at TEXT,pages_visited INTEGER DEFAULT 0,pages_learned INTEGER DEFAULT 0,knowledge_added INTEGER DEFAULT 0,errors INTEGER DEFAULT 0,detail TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS learning_topics(id INTEGER PRIMARY KEY AUTOINCREMENT,topic TEXT UNIQUE NOT NULL,status TEXT DEFAULT 'pending',priority INTEGER DEFAULT 5,source TEXT DEFAULT 'curated',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,last_learned_at TEXT,attempts INTEGER DEFAULT 0,detail TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS programs(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,slug TEXT NOT NULL,request TEXT NOT NULL,language TEXT DEFAULT 'python',kind TEXT DEFAULT 'script',summary TEXT DEFAULT '',directory TEXT NOT NULL,entry TEXT DEFAULT '',files TEXT DEFAULT '[]',source TEXT DEFAULT 'recipe',generator TEXT DEFAULT '',status TEXT DEFAULT 'generated',verified INTEGER DEFAULT 0,verification TEXT DEFAULT '',last_run TEXT DEFAULT '',last_output TEXT DEFAULT '',last_exit INTEGER DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS concept_progress(id INTEGER PRIMARY KEY AUTOINCREMENT,language TEXT NOT NULL,concept TEXT NOT NULL,difficulty TEXT DEFAULT 'beginner',status TEXT DEFAULT 'queued',mastery REAL DEFAULT 0,confidence REAL DEFAULT 0.3,attempts INTEGER DEFAULT 0,successes INTEGER DEFAULT 0,last_studied_at TEXT,source_url TEXT DEFAULT '',summary TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(language,concept));
CREATE TABLE IF NOT EXISTS exercises(id INTEGER PRIMARY KEY AUTOINCREMENT,language TEXT NOT NULL,concept TEXT DEFAULT '',difficulty TEXT DEFAULT 'beginner',kind TEXT DEFAULT 'generated',title TEXT NOT NULL,prompt TEXT DEFAULT '',starter TEXT DEFAULT '',solution TEXT DEFAULT '',tests TEXT DEFAULT '',status TEXT DEFAULT 'draft',verified INTEGER DEFAULT 0,score REAL DEFAULT 0,runtime_ms INTEGER DEFAULT 0,output TEXT DEFAULT '',notes TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY AUTOINCREMENT,language TEXT NOT NULL,concept TEXT DEFAULT '',difficulty TEXT DEFAULT 'beginner',question TEXT NOT NULL,solution TEXT DEFAULT '',alternative TEXT DEFAULT '',tests TEXT DEFAULT '',status TEXT DEFAULT 'open',score REAL DEFAULT 0,efficiency REAL DEFAULT 0,runtime_ms INTEGER DEFAULT 0,alt_runtime_ms INTEGER DEFAULT 0,output TEXT DEFAULT '',explanation TEXT DEFAULT '',created_at TEXT NOT NULL,finished_at TEXT);
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,slug TEXT NOT NULL,request TEXT NOT NULL,archetype TEXT DEFAULT 'static-site',stack TEXT DEFAULT '',status TEXT DEFAULT 'planned',directory TEXT NOT NULL,entry TEXT DEFAULT '',files TEXT DEFAULT '[]',architecture TEXT DEFAULT '',plan TEXT DEFAULT '',dependencies TEXT DEFAULT '',test_output TEXT DEFAULT '',review_score REAL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_files(id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER NOT NULL,path TEXT NOT NULL,language TEXT DEFAULT '',content TEXT DEFAULT '',created_at TEXT NOT NULL,UNIQUE(project_id,path));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,target_kind TEXT NOT NULL,target_id INTEGER,title TEXT DEFAULT '',scores TEXT DEFAULT '{}',overall REAL DEFAULT 0,issues TEXT DEFAULT '[]',summary TEXT DEFAULT '',model TEXT DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,agent TEXT NOT NULL,task TEXT NOT NULL,status TEXT DEFAULT 'running',input TEXT DEFAULT '',output TEXT DEFAULT '',steps TEXT DEFAULT '[]',score REAL DEFAULT 0,created_at TEXT NOT NULL,finished_at TEXT);
CREATE TABLE IF NOT EXISTS knowledge_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,knowledge_id INTEGER NOT NULL,version INTEGER DEFAULT 1,title TEXT DEFAULT '',content TEXT DEFAULT '',source_url TEXT DEFAULT '',topic TEXT DEFAULT '',confidence REAL DEFAULT 0,verification_status TEXT DEFAULT '',change TEXT DEFAULT 'created',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS explored_sites(id INTEGER PRIMARY KEY AUTOINCREMENT,url TEXT NOT NULL,domain TEXT DEFAULT '',title TEXT DEFAULT '',category TEXT DEFAULT 'general',status TEXT DEFAULT 'discovered',value_score REAL DEFAULT 0,summary TEXT DEFAULT '',discovered_at TEXT NOT NULL,learned_at TEXT,UNIQUE(url));
CREATE TABLE IF NOT EXISTS automation_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,status TEXT DEFAULT 'running',detail TEXT DEFAULT '',stats TEXT DEFAULT '{}',started_at TEXT NOT NULL,finished_at TEXT);
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
CREATE INDEX IF NOT EXISTS idx_web_sources_status ON web_sources(status);
CREATE INDEX IF NOT EXISTS idx_web_sources_root ON web_sources(root_id);
CREATE INDEX IF NOT EXISTS idx_web_chunks_source ON web_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
CREATE INDEX IF NOT EXISTS idx_skills_enabled ON skills(enabled);
CREATE INDEX IF NOT EXISTS idx_learning_sessions_status ON learning_sessions(status);
CREATE INDEX IF NOT EXISTS idx_learning_topics_status ON learning_topics(status);
CREATE INDEX IF NOT EXISTS idx_programs_created ON programs(id);
CREATE INDEX IF NOT EXISTS idx_concept_language ON concept_progress(language);
CREATE INDEX IF NOT EXISTS idx_concept_status ON concept_progress(status);
CREATE INDEX IF NOT EXISTS idx_exercises_language ON exercises(language);
CREATE INDEX IF NOT EXISTS idx_assessments_language ON assessments(language);
CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files(project_id);
CREATE INDEX IF NOT EXISTS idx_reviews_target ON reviews(target_kind,target_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent);
CREATE INDEX IF NOT EXISTS idx_knowledge_versions_item ON knowledge_versions(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_explored_domain ON explored_sites(domain);
CREATE INDEX IF NOT EXISTS idx_automation_kind ON automation_runs(kind);
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
    # url learning --------------------------------------------------------------
    'learn_depth': '0',
    'learn_max_links': '8',
    'web_chunk_chars': '1200',
    'web_chunk_overlap': '180',
    'max_web_pages': '40',
    # autonomous learning -------------------------------------------------------
    'learning_enabled': 'false',
    'learning_resume': 'true',
    'learning_speed': 'normal',
    'learning_pages_per_session': '5',
    'learning_topics': '',
    'learning_random': 'true',
    'learning_session_interval_seconds': '120',
    'learning_auto_verify': 'true',
    # program forge -------------------------------------------------------------
    'codegen_provider': 'auto',
    'code_exec_timeout': '20',
    # skills (antigravity vault) ------------------------------------------------
    'skills_auto_context': 'true',
    'skills_seed_version': '',
    'skills_repo': 'https://github.com/rmyndharis/antigravity-skills',
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
    # autonomous programming ----------------------------------------------------
    'autoprogramming_enabled': 'false',
    'autoprogramming_languages': 'python,javascript,typescript,sql,html,css',
    'autoprogramming_difficulty': 'beginner',
    'autoprogramming_interval_seconds': '90',
    'autoprogramming_concepts_per_cycle': '1',
    'autoprogramming_use_internet': 'true',
    'autoprogramming_auto_assess': 'true',
    # exploration ---------------------------------------------------------------
    'exploration_categories': 'programming,ai,ml,cybersecurity,science,mathematics,webdev,gamedev,robotics,general',
    'exploration_interval_seconds': '120',
    'exploration_sites_per_cycle': '3',
    # review studio -------------------------------------------------------------
    'review_auto': 'true',
    'review_min_score': '70',
    'review_provider': 'auto',
    # projects ------------------------------------------------------------------
    'project_root': '',
    'project_auto_test': 'true',
}

def init_db():
    with connect() as db:
        db.executescript(SCHEMA)
        db.executescript(INDEXES)
        # Migrate databases created by earlier NEXUS builds.
        for table, columns in {
            'knowledge': [('embedding', 'TEXT'), ('verification_status', "TEXT DEFAULT 'unverified'"),
                          ('source_domain', 'TEXT'), ('embedding_kind', 'TEXT'), ('session_id', 'INTEGER'),
                          ('version', 'INTEGER DEFAULT 1'), ('supersedes_id', 'INTEGER'),
                          ('category', "TEXT DEFAULT ''"), ('last_verified_at', 'TEXT')],
            'tasks': [('priority', 'INTEGER DEFAULT 5'), ('parent_id', 'INTEGER'),
                      ('mode', "TEXT DEFAULT 'assisted'"), ('attempts', 'INTEGER DEFAULT 0'),
                      ('progress', 'INTEGER DEFAULT 0'), ('category', "TEXT DEFAULT ''"),
                      ('agent', "TEXT DEFAULT ''"), ('result', "TEXT DEFAULT ''"),
                      ('started_at', 'TEXT'), ('finished_at', 'TEXT')],
            'memories': [('embedding_kind', 'TEXT')],
            'web_sources': [('root_id', 'INTEGER'), ('depth', 'INTEGER DEFAULT 0'), ('summary', "TEXT DEFAULT ''"),
                            ('char_count', 'INTEGER DEFAULT 0'), ('chunk_count', 'INTEGER DEFAULT 0'),
                            ('session_id', 'INTEGER'), ('category', "TEXT DEFAULT ''")],
            'skills': [('bundles', "TEXT DEFAULT ''"), ('enabled', 'INTEGER DEFAULT 1'), ('triggers', "TEXT DEFAULT ''")],
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
