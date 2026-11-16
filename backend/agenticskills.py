"""Import skills from the AgenticSkills.io directory into NEXUS skill vault."""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from .database import connect, now, event
from .textutil import clip

SOURCE = 'https://agenticskills.io'
INDEX_URL = 'https://agenticskills.io/skills'


async def import_agenticskills():
    headers = {'User-Agent': 'NexusAI/0.5'}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as c:
        r = await c.get(INDEX_URL)
        r.raise_for_status()
        html = r.text
    soup = BeautifulSoup(html, 'html.parser')
    links = [a for a in soup.find_all('a', href=True) if 'agenticskills.io/skills/' in a['href']]
    imported = 0
    skipped = 0
    with connect() as db:
        for a in links:
            name = a.get_text(strip=True)
            url = a['href']
            slug = url.rstrip('/').split('/')[-1]
            skill_id = 'agenticskills_' + slug
            parent_txt = a.parent.get_text(' ', strip=True) if a.parent else ''
            desc = ''
            if '\u2014' in parent_txt:
                desc = parent_txt.split('\u2014', 1)[1].strip()
            desc = clip(desc, 500) if desc else name
            try:
                db.execute(
                    '''INSERT INTO skills(skill_id,name,description,category,tags,triggers,bundles,content,source,source_path,enabled,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (skill_id, name, desc, 'agenticskills', 'agenticskills,imported', name.lower(),
                     'agenticskills', desc, SOURCE, url, 1, now(), now()))
                imported += 1
            except Exception:
                skipped += 1
    event('skills', f'Imported {imported} skills from AgenticSkills.io ({skipped} skipped).')
    return {'imported': imported, 'skipped': skipped, 'source': SOURCE}