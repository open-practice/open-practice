#!/usr/bin/env python3
"""Render supporting pages, the illustrated library and shared footer links; no network."""
from pathlib import Path
import html,json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'hub'))
import social
R=Path(__file__).resolve().parent.parent;P=R/'apps/web/public';BASE='https://open-practice.open-practice.workers.dev';e=lambda s:html.escape(str(s),quote=True)
pages=json.loads((R/'curriculum/site-pages.json').read_text());template=(P/'library.html').read_text();head=template.split('<main>')[0];footer='<footer>'+template.split('<footer>',1)[1].split('</footer>',1)[0]+'</footer>'
def page_art(page):
 # 0.11.6: an info page with its own illustration (apps/web/public/brand/pages/<slug>.webp, made by
 # scripts/prepare-cover-art.py) shows it; until then it keeps the course cover named in site-pages.json.
 if (P/'brand/pages'/(page['slug']+'.webp')).exists():
  return f'<img src="/brand/pages/{page["slug"]}.webp?v=cover-20261029" alt="{e(page["label"])}: original illustrated cover for this page" width="720" height="864">'
 return f'<img src="/brand/covers/{page["cover"]}.svg?v=illustrated-20261021" alt="{e(page["label"])} — original AI-generated editorial illustration" width="410" height="520">'
for page in pages:
 slug=page['slug'];h=re.sub(r'<title>.*?</title>','<title>'+e(page['label'])+' · Open Practice</title>',head);h=h.replace(' aria-current="page"','');h=h.replace('</head>',f'<meta name="description" content="{e(page["intro"])}"><link rel="canonical" href="{BASE}/{slug}.html"></head>')
 body=f'<article class="reading-page"><section class="info-hero"><div><div class="eyebrow">OPEN PRACTICE / {e(page["label"].upper())}</div><h1>{e(page["title"])}</h1><p>{e(page["intro"])}</p><p class="info-updated">Published 21 October 2026 · current independent pilot</p></div>{page_art(page)}</section>'
 for i,(title,text) in enumerate(page['sections']):
  body+='<section><h2>'+e(title)+'</h2>'+('<div>'+text+'</div>' if '<' in text else '<p>'+e(text)+'</p>')+'</section>'
  # Contact: social icons right after the public feedback route (links live in curriculum/social-links.json).
  if slug=='contact' and i==0:body+='<section class="contact-social"><h2>Find Open Practice on social media</h2><p>Follow along, join a free community or send a message where you already are. Greyed icons are opening soon.</p>'+social.social_icons()+'<p class="social-note">Never send passwords, API keys or recovery codes in a message on any platform.</p></section>'
 body+='</article>'
 (P/f'{slug}.html').write_text(h+'<main>'+body+'</main>'+footer+'<script type="module" src="/learner.js"></script><script type="module" src="/growth.js"></script></body></html>')
# The library is usable without JavaScript; filtering progressively enhances it.
resources=json.loads((P/'resources.json').read_text());cards=''
# Fail the build rather than publishing duplicate cards or repeated download destinations.
for key in ['id','title','url']:
 values=[str(r[key]).strip().casefold() for r in resources]
 assert len(values)==len(set(values)), 'Duplicate library '+key
files=[f['url'] for r in resources for f in r.get('downloads',[{'url':r['url']}])]
assert len(files)==len(set(files)), 'Repeated library download'

for item in resources:
 image=item.get('image');assert image,'Every resource must have a cover: '+item['id']
 downloads=item.get('downloads',[dict(label='Download free',format=item['format'],url=item['url'])])
 actions='<div class="library-downloads">'+''.join(f'<a class="primary" href="{e(f["url"])}" download>{e(f["label"] + " · " + f["format"] if item.get("downloads") else f["label"])} ↓</a>' for f in downloads)+'</div>'
 preview=f'<details class="resource-preview"><summary>Preview the downloadable diagram</summary><img src="{e(item["previewImage"])}" alt="{e(item["title"])} — downloadable diagram" loading="lazy"></details>' if item.get('previewImage') else ''
 cards+=f'<article class="resource-card"><a class="resource-art" href="{e(item["url"])}" download aria-label="Download {e(item["title"])}"><img class="resource-cover" src="{e(image)}" alt="{e(item["title"])} — illustrated resource cover" width="410" height="520" loading="lazy"></a><div class="resource-body"><div class="eyebrow">{e(item["kind"])} · {e(item["format"])}</div><h3>{e(item["title"])}</h3><p>{e(item["description"])}</p>{preview}<p>Licence: {e(item["licence"])}</p>{actions}</div></article>'
p=P/'library.html';s=p.read_text();start=s.index('<div id="hub-items"');end=s.index('</main>',start);s=s[:start]+'<div id="hub-items" class="cards hub-grid">'+cards+'</div>'+s[end:]
if 'id="hub-results"' not in s:s=s.replace('<div id="hub-items"',f'<p id="hub-results" role="status">{len(resources)} illustrated resources</p><div id="hub-items"')
s=re.sub(r'(<p id="hub-results"[^>]*>).*?(</p>)',lambda m:m[1]+str(len(resources))+' resources · download formats grouped together'+m[2],s)
s=s.replace('<section class="hub-hero">','<section class="hub-hero library-intro">',1);p.write_text(s)
# Add policy/help links once to every public page, including rendered activity guides.
links=[('about','About'),('help','Help & FAQ'),('privacy','Privacy policy'),('cookies','Cookies & storage'),('terms','Terms of use'),('licensing','Licensing'),('accessibility','Accessibility'),('contact','Contact')]
nav='<div class="policy-links" role="navigation" aria-label="Policies and help">'+''.join(f'<a href="/{slug}.html">{label}</a>' for slug,label in links)+'</div>'
files=list(P.glob('*.html'))+list((P/'activities').glob('*.html'))+list((P/'demonstrations').glob('*.html'))+list((P/'builds').glob('*.html'))
for p in files:
 s=p.read_text();s=re.sub(r'<div class="policy-links"[^>]*>.*?</div>','',s,flags=re.S);s=s.replace('</footer>',nav+'</footer>');p.write_text(s)
# Extend the generated sitemap without duplicates.
p=P/'sitemap.xml';s=p.read_text();paths=['/privacy.html']+['/'+page['slug']+'.html' for page in pages]
for path in paths:
 if BASE+path not in s:s=s.replace('</urlset>','<url><loc>'+BASE+path+'</loc></url></urlset>')
p.write_text(s)
print(f'Built {len(pages)} supporting pages, {len(resources)} illustrated library cards, and shared policy/help navigation.')
