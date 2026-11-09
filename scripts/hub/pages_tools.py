"""Free tool workshops (39) + index. Also reused for the kids and seniors tool sets."""
import json
from layout import page, hero, card, grid, faq_html, faq_ld, e, BASE

CATS = [('build', 'Build apps', 'Generate a working project, read every file, deploy it free.'),
        ('writing', 'Writing', 'Brief → draft → check against editor rules → ship.'),
        ('social', 'Social & video', 'Hooks, scripts and descriptions that keep their promise.'),
        ('business', 'Business', 'Plans and documents that end in decisions.'),
        ('developer', 'Developer', 'Pure-browser utilities, each with a practice challenge.'),
        ('ai', 'AI skills', 'Prompts, workflows and choosing the right tool.')]
CAT_NAME = {c: n for c, n, _ in CATS}
SHARED_FAQ = [
    ('Do I need an AI key to use this?', 'No. The guided template teaches the same skill with no AI at all. If you add your own free key (Groq, Google Gemini, OpenRouter, Mistral or Cerebras), the tool can also draft and revise. The key stays in your browser and requests go straight to that provider.'),
    ('Where is my work saved?', 'In this browser only (local storage), until you copy or download it. Nothing you type is sent to Open Practice.'),
]

from covers import tool_cover, tool_og

def field_html(f):
    req = ' required' if f['required'] else ''
    label = e(f['label']) + ('' if f['required'] or 'optional' in f['label'].lower() else ' <small>(optional)</small>')
    hid = f'f-{f["id"]}'
    if f['kind'] == 'textarea':
        ctl = f'<textarea id="{hid}" name="{f["id"]}" rows="{f["rows"]}" maxlength="4000" placeholder="{e(f["ph"])}"{req}></textarea>'
    elif f['kind'] == 'select':
        ctl = f'<select id="{hid}" name="{f["id"]}"{req}>' + ''.join(f'<option>{e(o)}</option>' for o in f['opts']) + '</select>'
    else:
        ctl = f'<input id="{hid}" name="{f["id"]}" type="text" maxlength="600" placeholder="{e(f["ph"])}"{req}>'
    help_ = f'<small class="ws-help">{e(f["help"])}</small>' if f.get('help') else ''
    return f'<div class="ws-field"><label for="{hid}">{label}</label>{help_}{ctl}</div>'

def config_json(cfg):
    return '<script type="application/json" id="ws-config">' + json.dumps(cfg, ensure_ascii=False).replace('</', '<\\/') + '</script>'

def workshop_write(t):
    cfg = dict(slug=t['slug'], name=t['name'], kind='write', fields=t['fields'], prompt=t['prompt'], template=t['template'], checks=t['checks'], ext=t.get('ext', 'txt'), system=t.get('system'), noAI=bool(t.get('noAI')))
    selfs = ''.join(f'<label><input type="checkbox"> {e(s)}</label>' for s in t.get('selfcheck', []))
    noai = bool(t.get('noAI'))
    keybar = '<p><b>Template only — made for young learners.</b> No AI and no signup: your ideas fill the blanks. Best with a grown-up nearby.</p>' if noai else '<p><b>No AI key needed.</b> The guided template works for everyone.</p>'
    routes = '<div class="ws-routes"><button type="button" id="ws-run-template" class="primary">Start with the template</button></div>' if noai else '<div class="ws-routes"><button type="button" id="ws-run-template" class="primary">Use the guided template (no AI)</button><button type="button" id="ws-run-ai" class="secondary" disabled>Draft with my AI key</button></div><details class="ws-prompt"><summary>See the exact prompt — copy it into any AI chat you already use</summary><pre id="ws-prompt"></pre><button type="button" id="ws-copy-prompt">Copy prompt</button></details>'
    revise = '' if noai else '<button type="button" id="ws-revise" class="secondary" disabled>Fix failing items with my AI key</button>'
    return (f'<section class="ws" id="workshop" aria-label="{e(t["name"])} workshop">{config_json(cfg)}<div class="ws-keybar" id="ws-keybar">{keybar}</div><ol class="ws-steps">'
            '<li class="ws-step"><h2><span>1</span>Brief</h2><p>Specific answers make better results — with or without AI.</p><form id="ws-brief" class="ws-form">' + ''.join(field_html(f) for f in t['fields']) + '<button class="primary">Next: make it ↓</button></form></li>'
            '<li class="ws-step" id="ws-make"><h2><span>2</span>Make</h2><p>' + ('The template gives you a structure with <code>[[blanks]]</code>. Replace each one with your own ideas.' if noai else 'Pick a route. The template gives you a structure with <code>[[blanks]]</code> to fill in yourself. Your own key drafts it for you — then you still check it.') + '</p>'
            + routes +
            '<p id="ws-status" class="ws-status" role="status" aria-live="polite"></p><label for="ws-draft" class="ws-draft-label">Your draft — edit freely</label><textarea id="ws-draft" rows="16" spellcheck="true"></textarea></li>'
            '<li class="ws-step" id="ws-check"><h2><span>3</span>Check</h2><p>The same rules run on every draft, human or AI. Most first drafts fail something — that is the point.</p><button type="button" id="ws-run-check" class="primary">Check my draft</button><p id="ws-score" class="ws-score"></p><ul id="ws-results" class="ws-results"></ul>'
            + (f'<fieldset class="ws-self"><legend>Self-check — judgement no checker can make</legend>{selfs}</fieldset>' if selfs else '') + '</li>'
            '<li class="ws-step" id="ws-improve"><h2><span>4</span>Improve</h2><p>Fix one item at a time, then check again. Notice which fixes made it better — that is the skill.</p><ol id="ws-fixes" class="ws-fixes"><li>Run the check first.</li></ol>' + revise + '</li>'
            f'<li class="ws-step" id="ws-ship"><h2><span>5</span>Ship</h2><p>Use it for real: send it, post it or save it. Record what happened — that is your evidence of learning.</p><div class="ws-routes"><button type="button" id="ws-copy" class="primary">Copy final text</button><button type="button" id="ws-save" class="secondary">Download .{t.get("ext", "txt")}</button></div><p id="ws-shipped" class="ws-shipped" hidden>✓ Added to your tool record on this device. <a href="/free-tools/">See all 39 tools →</a></p></li>'
            '</ol></section>')

def workshop_build(t):
    cfg = dict(slug=t['slug'], name=t['name'], kind='build', builder=t['builder'], fields=t['fields'], aiFill=t.get('aiFill', []))
    ai_btn = '<button type="button" id="ws-run-ai" class="secondary" disabled>Draft the text fields with my AI key</button>' if t.get('aiFill') else ''
    return (f'<section class="ws" id="workshop" aria-label="{e(t["name"])} workshop">{config_json(cfg)}<div class="ws-keybar" id="ws-keybar"><p><b>No AI key needed.</b> The code comes from a reviewed template.</p></div><ol class="ws-steps">'
            '<li class="ws-step"><h2><span>1</span>Brief</h2><p>Answer a few questions. The generator writes the code; you will read and change it.</p><form id="ws-brief" class="ws-form">' + ''.join(field_html(f) for f in t['fields']) + '<button class="primary">Next: make it ↓</button></form></li>'
            f'<li class="ws-step" id="ws-make"><h2><span>2</span>Make</h2><p>Generate the project, then open every file. Comments explain each part. You can edit files right here.</p><div class="ws-routes"><button type="button" id="ws-run-template" class="primary">Generate my project</button>{ai_btn}</div><p id="ws-status" class="ws-status" role="status" aria-live="polite"></p>'
            '<div class="ws-files" id="ws-files" role="tablist" aria-label="Project files"></div><label for="ws-file-view" class="ws-draft-label">File contents (editable)</label><textarea id="ws-file-view" rows="18" spellcheck="false" class="code" disabled></textarea></li>'
            '<li class="ws-step" id="ws-check"><h2><span>3</span>Check</h2><p>Automatic checks for the mistakes that break real projects: invalid config, leaked keys, missing security steps.</p><button type="button" id="ws-run-check" class="primary">Check my project</button><p id="ws-score" class="ws-score"></p><ul id="ws-results" class="ws-results"></ul></li>'
            f'<li class="ws-step" id="ws-improve"><h2><span>4</span>Improve</h2><ol id="ws-fixes" class="ws-fixes"><li>Run the check first.</li></ol><div class="ws-challenge"><b>Your change:</b> {e(t["challenge"])}</div></li>'
            f'<li class="ws-step" id="ws-ship"><h2><span>5</span>Ship</h2><p>{e(t["deploy"])} Step-by-step instructions are inside <code>README.md</code>.</p><div class="ws-routes"><button type="button" id="ws-download" class="primary" disabled>Download project (.zip)</button></div><p id="ws-shipped" class="ws-shipped" hidden>✓ Added to your tool record on this device. <a href="/free-tools/">See all 39 tools →</a></p></li>'
            '</ol></section>')

UTIL_UI = {
 'json': '<label for="u-in">Paste JSON</label><textarea id="u-in" rows="10" class="code" spellcheck="false">{"tool":"Open Practice","free":true,"steps":["brief","make","check","improve","ship"]}</textarea><div class="ws-routes"><button type="button" id="u-format" class="primary">Format & validate</button><button type="button" id="u-minify" class="secondary">Minify</button></div><p id="u-status" class="ws-status" role="status"></p><label for="u-out">Result</label><textarea id="u-out" rows="10" class="code" readonly></textarea>',
 'base64': '<label for="u-in">Text or Base64</label><textarea id="u-in" rows="6" class="code">Mhoro! Sawubona! Hello! 👋</textarea><label class="inline"><input type="checkbox" id="u-url"> URL-safe</label><div class="ws-routes"><button type="button" id="u-encode" class="primary">Encode →</button><button type="button" id="u-decode" class="secondary">← Decode</button></div><p id="u-status" class="ws-status" role="status"></p><label for="u-out">Result</label><textarea id="u-out" rows="6" class="code" readonly></textarea>',
 'markdown': '<label for="u-in">Markdown</label><textarea id="u-in" rows="10" class="code"># My first page\n\nI am learning **Markdown** on [Open Practice](https://open-practice.open-practice.workers.dev).\n\n- Write\n- Check\n- Ship</textarea><p id="u-status" class="ws-status" role="status"></p><div class="u-split"><div><label for="u-out">HTML</label><textarea id="u-out" rows="10" class="code" readonly></textarea></div><div><span class="ws-draft-label">Preview</span><div id="u-preview" class="u-preview"></div></div></div>',
 'tokens': '<label for="u-in">Prompt or text</label><textarea id="u-in" rows="10">Paste a prompt here to estimate its size.</textarea><label for="u-context">Context window</label><select id="u-context"><option value="8192">8,192 tokens (small models)</option><option value="32768">32,768</option><option value="131072" selected>131,072 (128K)</option><option value="1000000">1,000,000 (1M)</option></select><p id="u-stats" class="ws-score" role="status"></p><textarea id="u-out" hidden></textarea><p id="u-status" hidden></p>',
 'cost': '<div class="u-grid"><label>Requests per day<input id="u-requests" type="number" min="0" value="500"></label><label>Input tokens per request<input id="u-inTok" type="number" min="0" value="600"></label><label>Output tokens per request<input id="u-outTok" type="number" min="0" value="250"></label><label>Days per month<input id="u-days" type="number" min="0" value="30"></label><label>Price per 1M input tokens ($)<input id="u-inPrice" type="number" min="0" step="0.01" value="0.10"></label><label>Price per 1M output tokens ($)<input id="u-outPrice" type="number" min="0" step="0.01" value="0.40"></label></div><label for="u-preset">Example price sets (verify on the provider’s pricing page)</label><select id="u-preset"><option value="">Choose an example…</option><option value="0,0">Free tier (within limits): $0 / $0</option><option value="0.05,0.08">Small open model (example): $0.05 / $0.08</option><option value="0.10,0.40">Fast mid-size model (example): $0.10 / $0.40</option><option value="0.50,1.50">Larger model (example): $0.50 / $1.50</option><option value="3,15">Frontier model (example): $3 / $15</option></select><p id="u-stats" class="ws-score" role="status"></p><textarea id="u-out" hidden></textarea><p id="u-status" hidden></p>',
}

def workshop_util(t):
    cfg = dict(slug=t['slug'], util=t['util'])
    chal = (f'<div class="ws-step"><h2><span>✓</span>Practice challenge</h2><p>{e(t["challenge_text"])}</p>' + (f'<pre class="code">{e(t["challenge_input"])}</pre>' if t['challenge_input'] else '') +
            f'<label for="c-in">Your answer</label><textarea id="c-in" rows="6" class="code">{e(t["challenge_input"]) if t["util"] == "json" else ""}</textarea><button type="button" id="c-check" class="primary">Check my answer</button><p id="c-status" class="ws-status" role="status"></p><p id="ws-shipped" class="ws-shipped" hidden>✓ Challenge recorded on this device.</p></div>')
    return f'<section class="ws" id="workshop">{config_json(cfg)}<div class="ws-step"><h2><span>⚙</span>Use the tool</h2><p class="ws-private">🔒 Runs entirely in your browser. Nothing is uploaded.</p>{UTIL_UI[t["util"]]}</div>{chal}</section>'

def tool_page(t, base='/free-tools/', section='Free tools', all_by_slug=None, courses=None, audience=None):
    url = f'{base}{t["slug"]}/'
    kind = 'build' if t.get('builder') else 'util' if t.get('util') else 'write'
    body_ws = workshop_build(t) if kind == 'build' else workshop_util(t) if kind == 'util' else workshop_write(t)
    chips = ''.join(f'<li>{e(s)}</li>' for s in t.get('skills', []))
    meta = '⏱ 10–20 min · Template only, no AI' if t.get('noAI') else {'build': '⏱ 20–40 min · Download a ZIP · Deploy free', 'util': '⏱ 5–10 min · Runs in your browser', 'write': '⏱ 10–20 min · Works with or without AI'}[kind]
    eyebrow = (audience or 'FREE TOOL') + ' · ' + CAT_NAME.get(t['cat'], t['cat']).upper()
    extra = f'<p class="hub-meta">{meta} · No signup</p><div class="hub-skills"><h2>You will practise</h2><ul>{chips}</ul></div>'
    cov = tool_cover(t['slug'])
    if cov:
        extra += f'<img class="tool-cover" src="{cov}" width="600" height="720" alt="" loading="eager" decoding="async">'
    body = hero(eyebrow, t['h1'], t['intro'], extra).replace('class="hub-hero"', 'class="hub-hero has-cover"' if cov else 'class="hub-hero"', 1) + body_ws
    if t.get('tips'):
        body += '<section class="hub-section"><h2>Pro moves</h2><ul class="hub-list">' + ''.join(f'<li>{e(x)}</li>' for x in t['tips']) + '</ul></section>'
    faq = list(t.get('faq', [])) + ([] if kind == 'util' or t.get('noAI') else SHARED_FAQ)
    body += faq_html(faq)
    rel = []
    for s in t.get('related', []):
        r = (all_by_slug or {}).get(s)
        if r:
            rel.append(card(r.get('href') or f'{base}{r["slug"]}/', r['name'], r['desc'][:110] if r.get('href') else r['h1'], CAT_NAME.get(r['cat'], ''), r.get('emoji', '')))
    if courses and t.get('course') in courses:
        c = courses[t['course']]
        rel.append(card(f'/builds/{c["id"]}.html', c['title'], 'Go deeper: a full project course with fixtures, a capstone and a handbook.', 'ACADEMY COURSE', '🎓'))
    if rel:
        body += '<section class="hub-section"><h2>Keep building</h2>' + grid(rel) + '</section>'
    steps = [('Brief', 'Describe what you need in the form.'), ('Make', 'Generate a guided template or an AI draft with your own key.'), ('Check', 'Run the automatic rubric checks.'), ('Improve', 'Fix failing items one at a time.'), ('Ship', 'Copy, download or deploy the result.')]
    ld = [{'@context': 'https://schema.org', '@type': 'SoftwareApplication', 'name': t['name'], 'url': BASE + url, 'applicationCategory': 'DeveloperApplication' if kind != 'write' else 'BusinessApplication', 'operatingSystem': 'Web browser', 'description': t['desc'], 'isAccessibleForFree': True, 'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'}, 'publisher': {'@type': 'Organization', 'name': 'Open Practice', 'url': BASE + '/'}},
          {'@context': 'https://schema.org', '@type': 'HowTo', 'name': t['h1'], 'totalTime': 'PT20M', 'estimatedCost': {'@type': 'MonetaryAmount', 'currency': 'USD', 'value': '0'}, 'step': [{'@type': 'HowToStep', 'position': i + 1, 'name': n, 'text': x, 'url': BASE + url + '#workshop'} for i, (n, x) in enumerate(steps)]},
          faq_ld(faq)]
    scripts = ('/devtools.js',) if kind == 'util' else ('/workshop.js',)
    title = t['name'] + (' — free, learn by doing' if len(t['name']) < 34 else '')
    if audience == 'SENIORS':
        body = f'<div class="big-print">{body}</div>'
    elif audience == 'KIDS':
        body = f'<div class="kid-friendly">{body}</div>'
    return page(url, title, t['desc'], body, crumbs=[(section, base), (t['name'], None)], ld=ld, scripts=scripts, active='Tools' if base == '/free-tools/' else 'Learn', priority=0.8, og=tool_og(t['slug']))

def _cover_card(t):
    """Index card: the tool's own cover when its art exists, otherwise the emoji card (never a borrowed image)."""
    c = card(t.get('href') or f'/free-tools/{t["slug"]}/', t['name'], t['desc'] if t.get('href') else t['h1'], '', '' if tool_cover(t['slug']) else t.get('emoji', ''))
    cov = tool_cover(t['slug'])
    if cov:
        c = c.replace('">', f'"><img class="hub-card-cover" src="{cov}" width="600" height="720" alt="" loading="lazy" decoding="async">', 1)
    return c.replace('class="hub-card"', f'class="hub-card{" has-cover" if cov else ""}" data-tool="{t["slug"]}"', 1)

def index_page(tools, special):
    total = len(tools) + len(special)
    body = hero('FREE TOOLS · NO SIGNUP', f'{total} free AI tools you learn by using', 'Every tool is a short workshop: brief it, make something, check it against real rules, improve it and ship it. Bring your own free AI key for drafts, or use the guided templates — no AI needed.',
                f'<p class="hub-meta"><span id="built-count">0</span> of {total} built on this device · <a href="/api-keys/">Get a free AI key</a> · <a href="/settings/">Key settings</a></p>')
    body += '<section class="hub-how"><ol><li><b>Brief</b>Say what you need</li><li><b>Make</b>Template or your own AI</li><li><b>Check</b>Automatic rubric</li><li><b>Improve</b>One fix at a time</li><li><b>Ship</b>Copy, download, deploy</li></ol></section>'
    for cat, name, blurb in CATS:
        items = [t for t in tools if t['cat'] == cat] + [s for s in special if s['cat'] == cat]
        cards = [_cover_card(t) for t in items]
        body += f'<section class="hub-section" id="{cat}"><h2>{e(name)} <small>{len(items)}</small></h2><p>{e(blurb)}</p>' + grid(cards) + '</section>'
    faq = [('Are these tools really free?', 'Yes. There is no signup and no paywall. AI drafting uses your own free key from a provider such as Groq or Google, so you are never billed by us.'), ('Why “learn by doing” instead of one-click generation?', 'One-click output teaches nothing and is often wrong. Each tool makes you brief, check and improve — the skills that transfer to any AI tool.'), *SHARED_FAQ]
    body += faq_html(faq)
    ld = [{'@context': 'https://schema.org', '@type': 'ItemList', 'name': 'Free AI tools', 'numberOfItems': total, 'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'url': BASE + (t.get('href') or f'/free-tools/{t["slug"]}/'), 'name': t['name']} for i, t in enumerate(tools + special)]}, faq_ld(faq)]
    page('/free-tools/', f'{total} Free AI Tools — learn by doing, no signup', f'{total} free AI tools that teach as you use them: writing, social, business, developer and app builders. Bring your own free key or use guided templates.', body, crumbs=[('Free tools', None)], ld=ld, scripts=('/tools-index.js',), active='Tools', priority=0.95)
