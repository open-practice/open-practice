#!/usr/bin/env python3
"""Build indexable guides, starter challenge and facilitator assets. No network or AI calls."""
from pathlib import Path
import html,json,zipfile,io
R=Path(__file__).resolve().parent.parent;P=R/'apps/web/public';BASE='https://open-practice.open-practice.workers.dev';E=lambda x:html.escape(str(x),quote=True)
activities=sorted([json.loads(p.read_text()) for p in (P/'activities').glob('*.json')],key=lambda a:a['number']);A={a['id']:a for a in activities};starter=['bounded-editor','json-data','contrast-check']
base=(P/'activities.html').read_text();header=base.split('<main>')[0];header=header.replace('<a href="/activities.html" aria-current="page">','<a href="/activities.html">');footer='<footer>'+base.split('<footer>')[1].split('<script')[0];footer=footer.replace('<a href="/tools.html">Tool field desk</a>','<a href="/tools.html">Tool field desk</a><a href="/practice.html">Practice guides</a><a href="/starter.html">Starter challenge</a><a href="/facilitators.html">Facilitator kit</a>')

def page(path,title,description,body,script='/growth.js',image=None,noindex=False,activity=None):
 head=header;start=head.index('<title>');end=head.index('</title>')+8;head=head[:start]+'<title>'+E(title)+' · Open Practice</title>'+head[end:]
 meta=f'<meta name="description" content="{E(description)}"><link rel="canonical" href="{BASE+path}"><meta property="og:type" content="article"><meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(description)}"><meta property="og:url" content="{BASE+path}"><meta name="twitter:card" content="summary_large_image">'
 if image:meta+=f'<meta property="og:image" content="{BASE+image}"><meta property="og:image:alt" content="{E(title)} — original AI-generated activity illustration">'
 if noindex:meta+='<meta name="robots" content="noindex,nofollow">'
 head=head.replace('</head>',meta+'</head>')
 if activity:head=head.replace('<body>',f'<body data-growth-activity="{E(activity)}">')
 target=P/path.lstrip('/');target.parent.mkdir(exist_ok=True,parents=True);target.write_text(head+'<main>'+body+'</main>'+footer+(f'<script type="module" src="{script}"></script>' if script else '')+('</body></html>'))

def activity_card(a,status=False):
 id=a['id'];return f'<article><a href="/activities/{id}.html"><img src="{a["cover"]}" width="600" height="720" loading="lazy" alt="{E(a["title"])} — original illustrated cover"></a><div><div class="eyebrow">ACTIVITY {a["number"]:02d} / {E(a["collectionTitle"])}</div><h2><a href="/activities/{id}.html">{E(a["title"])}</a></h2><p>{E(a["goal"])}</p><p>{a["estimatedMinutes"]} minutes estimated · free materials</p>'+ (f'<span class="starter-status" data-starter-status="{id}">Loading browser self-review status…</span>' if status else '')+f'<a class="primary" data-carry-source href="/activities.html?activity={id}">Make, test & keep evidence →</a></div></article>'

for a in activities:
 id=a['id'];body=f'<article class="reading-page"><section class="discovery-hero"><div><div class="eyebrow">FREE PRACTICAL AI EXERCISE / {a["number"]:02d}</div><h1>{E(a["title"])}</h1><p>{E(a["goal"])}</p><p>{a["estimatedMinutes"]} minutes estimated—not learner-validated. Original learning materials are free; optional external AI access may require an account, credits or payment.</p><a class="primary" data-carry-source data-practice-start href="/activities.html?activity={id}">Start the editable activity →</a><p>No account needed to begin. Explicit account saving and editable offline export are available in the workspace.</p><a href="/starter.html">New here? Try the three-activity starter ↗</a></div><img src="{a["cover"]}" width="600" height="720" alt="{E(a["title"])} — original AI-generated editorial illustration"></section>'
 body+=f'<section><h2>Why this matters</h2><p>{E(a["explanation"])}</p><h3>Before you start</h3><p>{E(a["providerNote"])}</p></section><section><h2>Your illustrated field guide</h2><img src="{a["guide"]}" width="1100" height="1220" loading="lazy" alt="'+E('; '.join(s['title']+': '+s['text'] for s in a['visualSteps']))+'"><p>Conceptual illustration, not a provider screenshot. Artwork is AI-generated; instructional labels are authored text.</p></section>'
 for title,key in [('Start with fictional input','sampleInput'),('Copy and adapt this prompt','prompt'),('Worked reference—not proof of correctness','workedExample')]:body+='<section><h2>'+title+'</h2><pre>'+E(a[key])+'</pre></section>'
 body+='<section><h2>Five practical steps</h2><ol>'+''.join('<li><h3>'+E(s['title'])+'</h3><p>'+E(s['text'])+'</p></li>' for s in a['steps'])+'</ol></section>'
 for title,key in [('Test your result','checks'),('Mistakes to watch for','commonMistakes')]:body+='<section><h2>'+title+'</h2><ul>'+''.join('<li>'+E(t)+'</li>' for t in a[key])+'</ul></section>'
 body+='<section><h2>Offline / no-key route</h2><p>'+E(a['offline'])+'</p><h3>Reflect</h3><p>'+E(a['reflection'])+'</p><a data-carry-source class="primary" href="/activities.html?activity='+id+'">Keep your notes, tests and self-review →</a><p>Self-reported practice is not independent assessment or a qualification. <a href="/practice.html">Browse all 50 guides</a> · <a href="/tools.html">Choose a tool</a></p></section></article>'
 page('/activities/'+id+'.html',a['title']+' — free AI practice',a['goal']+' Includes a fictional input, reusable prompt, illustrated guide and human checks.',body,'/discovery.js','/brand/social/'+id+'.jpg',activity=id)

page('/practice.html','50 free learn-by-doing AI exercises','Full illustrated beginner activities in prompting, data, research, creative media and verification.', '<section class="hub-hero"><div class="eyebrow">READ IT / MAKE IT / TEST IT</div><h1>Fifty ways to practice AI.</h1><p>Full instructions you can read without JavaScript. Start with fictional inputs, test the output, and keep the evidence. Free materials; external-tool limits apply.</p><a class="primary" href="/starter.html">Try the three-activity starter →</a></section><div class="guide-directory">'+''.join(activity_card(a) for a in activities)+'</div>','/discovery.js')
page('/starter.html','Three practical AI wins — free starter challenge','Edit with boundaries, structure fictional data and measure contrast. Keep evidence from three beginner AI activities.', '<section class="hub-hero"><div class="eyebrow">A STARTER, NOT ANOTHER SUBSCRIPTION</div><h1>Make. Structure. Verify.</h1><p>Three practical activities: build a bounded editor, convert fictional book notes into JSON, and measure actual colour contrast. No private data or new platform subscription is needed to start.</p><p>About 120 minutes for the full guided sequence, estimated—not learner-tested. Go at your own pace. Manual fixtures and design-only routes are labelled honestly; they are not live AI runs.</p><p id="starter-progress" role="status">Self-review status loads from this browser when JavaScript is available.</p></section><div class="guide-directory">'+''.join(activity_card(A[id],True) for id in starter)+'</div><section class="lab-section"><h2>What you will keep</h2><p>An editing test log, a checked JSON artifact and measured contrast results. Keep a remaining limitation for each. Self-reviews do not award a certificate or qualification.</p><a href="/facilitators.html">Run a facilitated taster ↗</a></section>','/starter.js','/brand/social/bounded-editor.jpg')

kit='''# Open Practice / facilitator pilot kit

Independent, non-accredited practical learning. This pilot is for adults 18+; accounts are optional. No endorsement or partnership is implied.

## Two formats
- Full self-paced starter: approximately 120 minutes, estimated, not learner-tested.
- Facilitated taster: 60 minutes, not completion of the three full activities.

## 60-minute agenda
0–8: Consent/privacy boundaries, choose manual or hosted route, use fictional inputs.
8–20: Bounded editor: compare a correct sentence and a messy sentence; log one boundary failure.
20–32: JSON: inspect the supplied three-book input; distinguish syntax, shape and factual checks. Keep unknown year as null.
32–44: Contrast: measure the supplied colour pairs, rather than trusting an attractive mockup.
44–54: Keep one result and limitation; optional local-only share card. No posting requirement.
54–60: Anonymous discussion of friction and a realistic next step. Invite voluntary continuation.

## Before the session
Confirm a consenting host, named facilitator, date, venue, expected adult cohort and connectivity. Do not announce a session before agreement. Test fixtures, download files, and prepare a projector/manual fallback. No attendee contact list is needed. Avoid collecting names or personal recordings. Never request provider credentials from participants. Company tutor usage is limited, not an unlimited event resource.

## Evidence and evaluation
Count attendance manually without names. Count participants who keep a first artifact; record aggregate usability problems and limitations. Do not equate registration, a taster, or synthetic feedback with mastery. Optional web counts cover consenting browsers only, not total attendance. Share only with explicit participant permission. Delete identifiable facilitator working notes when no longer needed.

## After the session
Record: date, host permission, aggregate attendance, first artifacts kept, biggest friction, next improvement and whether a follow-up was invited. No real session is claimed until a host and participants actually run it.

Starter: https://open-practice.open-practice.workers.dev/starter.html?src=facilitator
Full guides: https://open-practice.open-practice.workers.dev/practice.html
Original materials: CC BY 4.0.
'''
invitation='''Subject: Would a free 60-minute practical AI taster fit your adult community?

Hello [named community/team],

I run Open Practice, an independent, non-accredited collection of free practical AI learning materials. I noticed [specific relevant programme from your public site]. Would a small, optional 60-minute taster for adult learners be useful as a complement—not a replacement—to your work?

Participants use fictional inputs to test an editor, inspect structured data and measure contrast. They keep an artifact and a limitation rather than just watching a presentation. No paid AI plan, account signup, public sharing or mailing-list enrolment is required. Hosted AI availability and limits are disclosed; manual fixtures are available.

The facilitator kit and starter are here:
https://open-practice.open-practice.workers.dev/facilitators.html

If relevant, may we discuss a suitable facilitator, cohort size and date? If not, no follow-up is needed. I will not add you to an automated sequence.

[Your real name and reply address]
'''
res=P/'resources/growth';res.mkdir(parents=True,exist_ok=True);(res/'facilitator-kit.md').write_text(kit);(res/'invitation-template.txt').write_text(invitation);(res/'pilot-observation.csv').write_text('date,host_permission_confirmed,adult_attendance,first_artifacts_kept,main_friction,limitation,next_improvement,followup_invited\n')
entries={'README.md':kit.encode(),'invitation-template.txt':invitation.encode(),'pilot-observation.csv':(res/'pilot-observation.csv').read_bytes()}
for id in starter:
 a=A[id]
 for folder,key in [('handbooks','handbook'),('inputs','fixture'),('guides','guide')]:entries[folder+'/'+Path(a[key]).name]=(P/a[key].lstrip('/')).read_bytes()
with zipfile.ZipFile(res/'starter-pilot.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name,value in sorted(entries.items()):info=zipfile.ZipInfo(name,(2026,10,21,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,value)
page('/facilitators.html','Run a free practical AI pilot','A ready-to-run adult learner taster with fictional inputs, offline materials and an honest evaluation plan.', '''<article class="reading-page"><section><div class="eyebrow">FOR COMMUNITY HOSTS / LIBRARIES / ADULT LEARNING GROUPS</div><h1>Host a small, useful AI taster.</h1><p>A 60-minute facilitated taster, not a claim that learners completed the three full activities. The complete self-paced starter is estimated at 120 minutes. Materials are free, independent and non-accredited; no partner or session is claimed before agreement.</p><div class="actions"><a class="primary" href="/resources/growth/starter-pilot.zip" download>Download the complete pilot kit ZIP ↓</a><a href="/resources/growth/facilitator-kit.md" download>Facilitator plan ↓</a><a href="/resources/growth/pilot-observation.csv" download>Anonymous observation sheet ↓</a></div></section><section><h2>60-minute session</h2><ol><li>8 minutes: boundaries, fictional data, privacy and available tool routes.</li><li>12 minutes: test a bounded editor against correct and messy sentences.</li><li>12 minutes: distinguish valid JSON, agreed field types and true source values.</li><li>12 minutes: measure the supplied contrast pairs.</li><li>10 minutes: save one artifact and limitation; sharing is optional.</li><li>6 minutes: collect aggregate friction and choose one next step.</li></ol></section><section><h2>What a host needs</h2><p>A consenting adult cohort, a named facilitator, an agreed date and venue, and a tested offline fallback. Accounts are optional and this account pilot is 18+. Never ask participants for AI keys, passwords or private documents. Do not upload attendee lists. Download fixtures before relying on connectivity.</p><h2>What to measure</h2><p>Attendance, first artifacts kept, the biggest usability obstacle and one improvement. Keep aggregate notes without names. Website counts only include opted-in browsers; do not confuse them with total attendance or mastery.</p></section><section><h2>Invite a host, without a spam sequence</h2><p>Use the template only after researching a relevant public programme and selecting a named recipient. This kit is not proof of an invitation, booking, partnership or completed session.</p><a href="/resources/growth/invitation-template.txt" download>Download the personal invitation template ↓</a><p><a href="/starter.html?src=facilitator">Open the participant starter link →</a></p></section></article>''','/discovery.js','/brand/social/contrast-check.jpg')
page('/operator-metrics.html','Private acquisition counts','Operator-only aggregate counts for consenting browser identifiers.', '<article class="reading-page"><section><h1>Private funnel counts.</h1><p>No data is shown without the operator key. The key is used for this request only, not stored in the browser or placed in a URL. This page is not a public audience-size claim.</p><form id="metrics-form"><label for="operator-key">Operator key</label><input id="operator-key" type="password" autocomplete="off" required><button class="primary">Load last 30 days</button></form><p id="metrics-status" role="status"></p><pre id="metrics-output" class="metrics-output"></pre></section></article>','/metrics.js',noindex=True)
urls=['/','/practice.html','/starter.html','/facilitators.html','/demonstrations.html','/tools.html','/curriculum.html','/library.html']+['/activities/'+a['id']+'.html' for a in activities]
(P/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+BASE+u+'</loc></url>' for u in urls)+'</urlset>')
(P/'robots.txt').write_text('User-agent: *\nAllow: /\nDisallow: /operator-metrics.html\nDisallow: /api/\nSitemap: '+BASE+'/sitemap.xml\n')
print('Built 50 rendered guide pages, guide directory, starter challenge, facilitator kit, operator dashboard and sitemap.')

# Original useful demonstrations: constructed examples, no fabricated model-run claims.
demos=[]
for file in sorted((R/'curriculum/demonstrations').glob('*.json')):
 d=json.loads(file.read_text());a=A[d['activity']];body='<article class="reading-page"><section><div class="eyebrow">MAKE / BREAK / CHECK</div><h1>'+E(d['title'])+'</h1><p>'+E(d['summary'])+'</p><img src="/brand/social/'+a['id']+'.jpg" width="1200" height="630" alt="'+E(a['title'])+' — original AI-generated illustration"></section>';md='# '+d['title']+'\n\n'
 for b in d['blocks']:
  body+='<section>'
  if b.get('heading'):body+='<h2>'+E(b['heading'])+'</h2>';md+='## '+b['heading']+'\n\n'
  if b.get('text'):body+='<p>'+E(b['text'])+'</p>';md+=b['text']+'\n\n'
  if b.get('code'):body+='<pre>'+E(b['code'])+'</pre>';md+='```json\n'+b['code']+'\n```\n\n'
  if b.get('list'):body+='<ul>'+''.join('<li>'+E(t)+'</li>' for t in b['list'])+'</ul>';md+=''.join('- '+t+'\n' for t in b['list'])+'\n'
  body+='</section>'
 body+='<section><a class="primary" data-carry-source href="/activities/'+a['id']+'.html">Try the illustrated exercise →</a><p><a href="/starter.html">Three-activity starter</a> · <a href="/demonstrations.html">More useful demonstrations</a></p></section></article>'
 path='/demonstrations/'+d['slug']+'.html';page(path,d['title'],d['summary'],body,'/discovery.js','/brand/social/'+a['id']+'.jpg',activity=d['id']);md+='\nTry the complete exercise: '+BASE+'/activities/'+a['id']+'.html?src=devto\n\nOriginal source: '+BASE+path+'\n';(res/(d['slug']+'.md')).write_text(md);demos.append(d);urls.append(path)
page('/demonstrations.html','Useful AI demonstrations, not repeated adverts','Small examples of what can fail, how to test it and what to try next.', '<article class="reading-page"><section><div class="eyebrow">USEFUL BEFORE YOU CLICK AWAY</div><h1>Make it. Break it. Check it.</h1><p>Original demonstrations with fictional or public test inputs. No invented learner results, model benchmarks or promises of perfect AI.</p></section>'+''.join('<section><h2><a href="/demonstrations/'+d['slug']+'.html">'+E(d['title'])+'</a></h2><p>'+E(d['summary'])+'</p></section>' for d in demos)+'</article>','/discovery.js')
(P/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+BASE+u+'</loc></url>' for u in urls)+'</urlset>')
