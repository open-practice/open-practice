"""Shared layout for every generated page: header with dropdown navigation, footer, SEO head, breadcrumbs, JSON-LD."""
import html, json, re
from pathlib import Path

R = Path(__file__).resolve().parents[2]
P = R / 'apps/web/public'
BASE = 'https://open-practice.open-practice.workers.dev'
SITE = 'Open Practice'
UPDATED = '2026-10-29'
OG_DEFAULT = '/brand/og-card.png'
e = lambda s: html.escape(str(s), quote=True)
URLS = []  # (url, priority) collected for the sitemap

NAV = [
    ('Academy', '/academy/', [('All courses', '/academy/', 'Project-based AI courses'), ('Curriculum map', '/curriculum.html', 'How the paths connect'), ('50 activities', '/activities.html', 'Short guided experiments'), ('Free library', '/library.html', 'Handbooks and practice packs'), ('My learning', '/dashboard.html', 'Your saved work')]),
    ('Tools', '/free-tools/', [('39 free tools', '/free-tools/', 'Learn-by-doing workshops, no signup'), ('Tool field desk', '/tools.html', 'Pick a task, get a practice prompt'), ('AI tools directory', '/ai-tools/', 'What each tool is good for'), ('LLM guide', '/llms/', 'Language models explained'), ('Comparisons', '/compare/', 'Side-by-side, honest'), ('Tool finder quiz', '/tool-finder/', 'Find a tool in 5 questions'), ('Prompt library', '/prompts/', '60 prompts to practise')]),
    ('Learn', '/learn/', [('Start here', '/learn/beginners/', 'AI from zero'), ('AI for seniors', '/learn/seniors/', 'Large print, safe steps'), ('AI for kids', '/learn/kids/', 'Make things with a grown-up'), ('Glossary', '/glossary/', 'AI words in plain language'), ('Tutorials', '/tutorials/', 'Step-by-step builds'), ('Use cases', '/use-cases/', 'AI for your kind of work')]),
    ('Earn', '/earn/', None),
    ('API Keys ✦', '/api-keys/', None),
    ('News', '/news.html', None),
    ('Community', '/community/', None),
]

def header(active=''):
    out = ['<header class="hub-header"><a class="brand" href="/" aria-label="Open Practice home"><img src="/brand/open-practice-mark.svg" width="42" height="42" alt=""><span class="brand-type">Open <em>Practice</em><small>PRACTICAL AI ENGINEERING</small></span></a>',
           '<button class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="main-nav">Menu</button><nav id="main-nav" aria-label="Main navigation">']
    for label, href, menu in NAV:
        cur = ' aria-current="page"' if active == label else ''
        if not menu:
            out.append(f'<a class="nav-top" href="{href}"{cur}>{e(label)}</a>')
            continue
        items = ''.join(f'<a href="{h}"><b>{e(t)}</b><small>{e(d)}</small></a>' for t, h, d in menu)
        out.append(f'<div class="nav-group"><a class="nav-top" href="{href}"{cur}>{e(label)}</a><button class="nav-caret" aria-expanded="false" aria-label="{e(label)} menu">▾</button><div class="nav-menu">{items}</div></div>')
    out.append('<a class="nav-top nav-keys" href="/settings/" title="Your AI key settings" aria-label="Key settings">🔑<span class="nav-keys-label"> Key settings</span></a><button id="account-open">Sign in / Join ↗</button></nav></header>')
    return ''.join(out)

FOOTER = ('<footer><div class="hub-footer"><div><a class="brand" href="/"><img src="/brand/open-practice-mark.svg" width="44" height="44" alt="">OPEN PRACTICE</a><p>Free, practical AI learning. Built to be used — not just watched.</p><p class="footer-small">Independent · non-degree · non-accredited<br>A <a href="https://jacarandalabs.pages.dev/">Jacaranda Labs</a> venture<br>Code: MIT · Original lessons: CC BY 4.0</p></div>'
          '<div><h2>Learn</h2><a href="/academy/">Academy courses</a><a href="/learn/beginners/">Start here</a><a href="/learn/seniors/">AI for seniors</a><a href="/learn/kids/">AI for kids</a><a href="/glossary/">Glossary</a><a href="/tutorials/">Tutorials</a></div>'
          '<div><h2>Build</h2><a href="/free-tools/">39 free tools</a><a href="/earn/">Earn by Doing</a><a href="/prompts/">Prompt library</a><a href="/api-keys/">Free API keys</a><a href="/settings/">Key settings</a><a href="/tool-finder/">Tool finder</a><a href="/library.html">Free library</a></div>'
          '<div><h2>Explore</h2><a href="/ai-tools/">AI tools directory</a><a href="/llms/">LLM guide</a><a href="/compare/">Comparisons</a><a href="/use-cases/">Use cases</a><a href="/news.html">News</a><a href="/community/">Community</a></div>'
          '<div class="policy-links" role="navigation" aria-label="Policies and help"><a href="/about.html">About</a><a href="/help.html">Help & FAQ</a><a href="/privacy.html">Privacy policy</a><a href="/cookies.html">Cookies & storage</a><a href="/terms.html">Terms of use</a><a href="/licensing.html">Licensing</a><a href="/accessibility.html">Accessibility</a><a href="/contact.html">Contact</a></div></div></footer>')

SITEBAR = '<div class="site-bar"><span>FREE PRACTICAL AI LEARNING · LEARN BY DOING</span><span>NO SIGNUP NEEDED · YOUR WORK STAYS YOURS</span></div>'

def crumbs_html(crumbs):
    if not crumbs:
        return ''
    parts = ['<a href="/">Home</a>'] + [f'<a href="{u}">{e(n)}</a>' if u else f'<span aria-current="page">{e(n)}</span>' for n, u in crumbs]
    return '<nav class="crumbs" aria-label="Breadcrumb">' + ' › '.join(parts) + '</nav>'

def crumbs_ld(crumbs, url):
    items = [{'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'}]
    for i, (n, u) in enumerate(crumbs, 2):
        items.append({'@type': 'ListItem', 'position': i, 'name': n, 'item': BASE + (u or url)})
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': items}

def faq_ld(faq):
    return {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faq]}

def faq_html(faq, title='Questions people ask'):
    if not faq:
        return ''
    return f'<section class="hub-faq"><h2>{e(title)}</h2>' + ''.join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q, a in faq) + '</section>'

def page(url, title, desc, body, crumbs=None, ld=None, scripts=(), styles=(), active='', priority=0.6, og=None, noindex=False, wide=False, og_type='website'):
    """Write url ('/x/y/') to apps/web/public/x/y/index.html (or the .html path given)."""
    assert url.startswith('/'), url
    desc = re.sub(r'\s+', ' ', desc).strip()
    assert 50 <= len(desc) <= 175, f'description length {len(desc)} for {url}: {desc}'
    full_title = title if title.endswith(SITE) else f'{title} · {SITE}'
    assert len(full_title) <= 90, full_title
    lds = [crumbs_ld(crumbs, url)] if crumbs else []
    lds += ld or []
    img = BASE + (og or OG_DEFAULT)
    head = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(full_title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{BASE}{url}">'
            + ('<meta name="robots" content="noindex">' if noindex else '') +
            f'<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="{SITE}"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{BASE}{url}"><meta property="og:image" content="{img}"><meta name="twitter:card" content="summary_large_image">'
            '<link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/hub.css">' + ''.join(f'<link rel="stylesheet" href="{s}">' for s in styles) + '<link rel="icon" type="image/svg+xml" href="/brand/open-practice-mark.svg"><meta name="color-scheme" content="light"><meta name="theme-color" content="#7c1f16">'
            + ''.join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace('</', '<\\/') + '</script>' for x in lds) + '</head><body>')
    js = ''.join(f'<script type="module" src="{s}"></script>' for s in ('/nav.js', '/learner.js', '/growth.js', *scripts))
    doc = head + SITEBAR + header(active) + f'<main class="hub-main{" wide" if wide else ""}">' + crumbs_html(crumbs) + body + '</main>' + FOOTER + js + '</body></html>'
    path = P / (url.lstrip('/') + 'index.html' if url.endswith('/') else url.lstrip('/'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc)
    if not noindex:
        URLS.append((url, priority))
    return path

def hero(eyebrow, h1, intro, extra=''):
    return f'<section class="hub-hero"><div class="eyebrow">{e(eyebrow)}</div><h1>{e(h1)}</h1><p class="lede">{e(intro)}</p>{extra}</section>'

def card(href, title, text, kicker='', emoji=''):
    return f'<a class="hub-card" href="{href}">' + (f'<span class="hub-emoji" aria-hidden="true">{e(emoji)}</span>' if emoji else '') + (f'<small>{e(kicker)}</small>' if kicker else '') + f'<b>{e(title)}</b><span>{e(text)}</span></a>'

def grid(cards, cls=''):
    return f'<div class="hub-grid {cls}">' + ''.join(cards) + '</div>'

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
