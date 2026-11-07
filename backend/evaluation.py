import json
from .database import connect,now,event
from .providers import generate

async def evaluate_task(task_id,objective,page_count,domain_count,claims):
    with connect() as db:
        rows=db.execute('SELECT status,support_count FROM claims WHERE task_id=?',(task_id,)).fetchall()
    corroborated=sum(1 for r in rows if r['status']=='corroborated')
    disputed=sum(1 for r in rows if r['status']=='disputed')
    coverage=min(1.0,page_count/ max(3, min(8,page_count or 3)))
    diversity=min(1.0,domain_count/3)
    verification=corroborated/max(1,len(rows))
    score=round(100*(.25*coverage+.25*diversity+.4*verification+.1*(1-min(1,disputed/max(1,len(rows))))),1)
    issues=[]
    if domain_count<2:issues.append('Insufficient independent source diversity')
    if disputed:issues.append(f'{disputed} disputed claims need follow-up')
    if not corroborated:issues.append('No claims met the configured corroboration threshold')
    with connect() as db:
        db.execute('INSERT INTO evaluations(task_id,score,coverage,source_diversity,verification,issues,created_at) VALUES(?,?,?,?,?,?,?)',(task_id,score,coverage,diversity,verification,json.dumps(issues),now()))
        previous=db.execute('SELECT score FROM evaluations WHERE task_id<>? ORDER BY id DESC LIMIT 1',(task_id,)).fetchone()
    delta=round(score-previous['score'],1) if previous else None
    event('evaluation',f'Research quality score {score}/100'+(f' ({delta:+} vs previous)' if delta is not None else ' (baseline)'))
    if issues:
        await create_improvement_proposal(objective,issues,score,delta)
    return {'score':score,'issues':issues,'delta':delta}

async def create_improvement_proposal(context,issues,score=None,delta=None):
    prompt=f'''Suggest one safe, measurable improvement to NEXUS AI research quality. Distinguish memory, prompt, tool, or model-training improvement. Do not propose automatic production source modification. Context: {context}. Issues: {issues}. Score: {score}; change vs previous: {delta}. Return JSON with title,category (memory/prompt/tool/model-training),description, and optional unified_diff patch text. Prefer prompt/memory/process changes; any patch must be review-only and require user approval.'''
    raw=await generate(prompt)
    try:
        m=__import__('re').search(r'\{.*\}',raw,__import__('re').S); data=json.loads(m.group(0)) if m else {}
    except Exception:data={}
    title=str(data.get('title','Improve evidence diversity'))[:180]
    category=str(data.get('category','prompt'))[:40]
    desc=str(data.get('description',raw))[:4000]
    patch=str(data.get('patch',''))[:12000]
    with connect() as db:
        cur=db.execute('INSERT INTO proposals(title,category,description,patch,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(title,category,desc,patch,'proposed',now(),now()))
        pid=cur.lastrowid
    event('proposal',f'Improvement proposal created: {title} (approval required)')
    return pid
