import asyncio
from .database import connect,now,event,setting,set_setting
from .research import research_objective
from .providers import generate
from .memory import retrieve_experiences,save_experience

class Agent:
    def __init__(self):self.running=False;self.paused=False;self.worker=None;self.current_task=None;self.mode='assisted'
    async def start(self,autonomous=False,mode=None):
        if self.running:return
        self.running=True;self.paused=False;self.mode=mode or ('autonomous' if autonomous else 'assisted')
        set_setting('mode',self.mode);set_setting('autonomous_enabled',str(self.mode in ('autonomous','deep')).lower());set_setting('resume_on_boot','true')
        self.worker=asyncio.create_task(self._loop());event('agent',f'NEXUS AI started in {self.mode} mode.')
    async def pause(self):self.paused=True;event('agent','Agent paused; current request will finish safely.')
    async def resume(self):
        if not self.running:return await self.start(mode=setting('mode','assisted'))
        self.paused=False;event('agent','Agent resumed.')
    async def stop(self):
        self.running=False;self.paused=False;set_setting('resume_on_boot','false');set_setting('autonomous_enabled','false')
        if self.worker:self.worker.cancel()
        event('agent','Agent stopped; unfinished work will be recovered on next start.')
    async def add_task(self,objective,priority=5,parent_id=None,mode=None):
        with connect() as db:
            cur=db.execute('INSERT INTO tasks(objective,status,created_at,updated_at,priority,parent_id,mode) VALUES(?,?,?,?,?,?,?)',(objective,'queued',now(),now(),priority,parent_id,mode or self.mode))
            tid=cur.lastrowid
        event('task',f'Queued research objective: {objective}')
        return tid
    async def recover(self):
        with connect() as db:
            db.execute("UPDATE tasks SET status='queued',updated_at=?,notes=CASE WHEN notes='' THEN 'Recovered after application restart' ELSE notes||' | recovered after restart' END WHERE status IN ('running','interrupted')",(now(),))
        event('recovery','Recovered interrupted research tasks from the previous session.')
    async def _autoplan(self):
        with connect() as db:recent=db.execute('SELECT topic,title FROM knowledge ORDER BY id DESC LIMIT 18').fetchall()
        known='\n'.join(f"{x['topic']}: {x['title']}" for x in recent)
        experiences=await retrieve_experiences('successful and failed research strategies',4)
        exp='\n'.join(x['content'][:300] for x in experiences)
        prompt=f'''Create ONE novel, useful research objective to expand this knowledge, prioritizing gaps and avoiding repetition. Return only the objective under 25 words. Existing knowledge:\n{known or 'No prior knowledge.'}\nPast lessons:\n{exp}'''
        objective=(await generate(prompt)).strip().strip('"')
        if len(objective)>12 and objective.lower() not in known.lower():await self.add_task(objective,priority=7,mode=self.mode)
    async def _loop(self):
        try:
            while self.running:
                if self.paused:await asyncio.sleep(1);continue
                with connect() as db:task=db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY priority DESC,id LIMIT 1").fetchone()
                if task:
                    self.current_task=task['objective'];mode=task['mode'] or self.mode
                    with connect() as db:db.execute("UPDATE tasks SET status='running',updated_at=?,attempts=attempts+1 WHERE id=?",(now(),task['id']))
                    try:
                        pages=int(setting('deep_research_pages','15')) if mode=='deep' else int(setting('max_pages_per_task','8'))
                        result=await research_objective(task['id'],task['objective'],pages,mode)
                        await save_experience('success',f"Objective: {task['objective']}; result: {result}",.8)
                    except Exception as e:
                        await save_experience('failure',f"Objective: {task['objective']}; failure: {e}",.9)
                        with connect() as db:
                            latest=db.execute('SELECT attempts FROM tasks WHERE id=?',(task['id'],)).fetchone()
                            if latest and latest['attempts']<3: db.execute("UPDATE tasks SET status='queued',updated_at=?,notes=? WHERE id=?",(now(),f'Retrying after error: {str(e)[:250]}',task['id']))
                            else: db.execute("UPDATE tasks SET status='failed',updated_at=?,notes=? WHERE id=?",(now(),str(e)[:500],task['id']))
                    self.current_task=None;continue
                if self.mode in ('autonomous','deep'):
                    try:await self._autoplan()
                    except Exception as e:event('warning',f'Automatic research planning failed: {e}')
                await asyncio.sleep(max(10,int(setting('research_interval_seconds','45'))))
        except asyncio.CancelledError:pass
        finally:self.running=False;self.current_task=None
