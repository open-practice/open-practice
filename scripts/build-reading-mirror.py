#!/usr/bin/env python3
"""A clearly labelled static GitHub Pages reading/download fallback, not an account host."""
from pathlib import Path
import argparse,re,shutil
R=Path(__file__).resolve().parent.parent;P=R/'apps/web/public';MAIN='https://open-practice.open-practice.workers.dev'
a=argparse.ArgumentParser();a.add_argument('--output',default='.output/reading-mirror');args=a.parse_args();out=Path(args.output).resolve();base='/open-practice'
if not out.is_relative_to(R/'.output') or out==R/'.output':raise SystemExit('Output must be a subdirectory of .output')
if out.exists():shutil.rmtree(out)
out.mkdir(parents=True)
for folder in ['brand','resources','activities','demonstrations','builds']:
 shutil.copytree(P/folder,out/folder)
for name in ['style.css','practice.html','starter.html','facilitators.html','demonstrations.html','about.html','help.html','privacy.html','cookies.html','terms.html','licensing.html','accessibility.html','contact.html']:
 shutil.copy2(P/name,out/name)
shutil.copy2(P/'practice.html',out/'index.html')
# Only generated learning pages are altered. Downloadable examples retain their own code.
nav=f'<nav aria-label="Reading navigation"><a href="{base}/">50 guides</a><a href="{base}/starter.html">Starter</a><a href="{base}/facilitators.html">Pilot kit</a><a href="{base}/demonstrations.html">Demonstrations</a><a href="{base}/builds/index.html">build guides</a></nav>'
banner='<aside style="padding:16px;background:#f4dfaf;border-bottom:3px solid #7c1f16"><strong>Alternate reading &amp; download site.</strong> No accounts, cloud saving, browser progress or analytics run here. Editable workspaces remain on <a href="'+MAIN+'">the main site</a>. If that host is blocked on your network, read the guides and download the offline kit here; do not bypass certificate warnings.</aside>'
allowed={'practice.html','starter.html','facilitators.html','demonstrations.html','about.html','help.html','privacy.html','cookies.html','terms.html','licensing.html','accessibility.html','contact.html','index.html'}
for p in out.rglob('*.html'):
 rel=p.relative_to(out)
 if rel.parts[0]=='resources':continue
 if len(rel.parts)==1 and p.name not in allowed:continue
 s=p.read_text();s=re.sub(r'<script\b[^>]*>[\s\S]*?</script>','',s,flags=re.I)
 s=re.sub(r'<nav\b[\s\S]*?</nav>',lambda m:nav,s,count=1)
 s=s.replace('<body>', '<body>'+banner)
 s=re.sub(r'<body ([^>]*)>',lambda m:'<body '+m[1]+'>'+banner,s,count=1) if banner not in s else s
 s=s.replace('Loading browser self-review status…','Read-only guide; progress is not measured here.').replace('Self-review status loads from this browser when JavaScript is available.','Read-only starter. Download the kit and keep your own evidence.')
 s=re.sub(r'<footer>[\s\S]*?</footer>', '<footer><p>Open Practice · Independent, non-accredited learning · Code MIT / Original lessons CC BY 4.0</p><a href="https://github.com/king-kunta-cpu/open-practice">Source repository</a></footer>',s)
 # Static guide/workspace links remain honest: interactive destinations point to the main host.
 def link(m):
  attribute,path=m[1],m[2]
  if path=='/':target=base+'/'
  elif path.split('?',1)[0] in ['/activities.html','/dashboard.html','/curriculum.html','/library.html','/tools.html','/news.html']:target=MAIN+path
  else:target=base+path
  return attribute+'="'+target+'"'
 s=re.sub(r'(href|src)="(/(?!/)[^"]*)"',link,s)
 # The replacement navigation already has its prefix; don't prefix it twice.
 s=s.replace(base+base+'/',base+'/')
 p.write_text(s)
(out/'.nojekyll').write_text('')
(out/'robots.txt').write_text('User-agent: *\nAllow: /\n')
print('Built read-only mirror:',len(list(out.rglob('*'))),'entries; no account API or tracking scripts.')
