import ast
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

tree=ast.parse(Path('server/server.py').read_text(encoding='utf-8-sig'))
html=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DASHBOARD_HTML' for t in n.targets))
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
        if r.request.url=='http://theme.test/': r.fulfill(content_type='text/html',body=html)
        elif '/api/' in r.request.url: r.fulfill(content_type='application/json',body='{"ok":true,"items":[],"settings":{"theme":"Default"}}')
        else: r.abort()
    page.route('**/*',route)
    page.goto('http://theme.test/')
    page.wait_for_timeout(600)
    page.evaluate('''()=>render({sessions:[{machine_code:'M00001',machine_name:'IMM 301',job_code:'TEST',job_name:'Theme preview',operator_id:'Preview',good_total:25,pack_total:1,butal_total:2,last_seen_utc:new Date().toISOString()}],finished_jobs:[],finish_shifts:[]})''')
    backgrounds = set()
    for theme in ('Default','Soft Gray','Blue Accent','Dark','Red'):
        page.evaluate('(t)=>applyDashboardTheme(t)',theme)
        page.wait_for_timeout(400)
        colors=page.evaluate('''()=>Object.fromEntries(['body','.diag-item','.main-tab-button.active','.settings-card','.settings-row input'].map(s=>{let e=document.querySelector(s),c=getComputedStyle(e);return [s,{background:c.backgroundColor,color:c.color,border:c.borderColor}]}))''')
        print(theme,json.dumps(colors))
        backgrounds.add(colors['body']['background'])
        assert colors['body']['background'] != colors['body']['color']
        assert colors['.settings-row input']['background'] != colors['.settings-row input']['color']
        assert colors['.main-tab-button.active']['color'] == 'rgb(255, 255, 255)'
        page.screenshot(path=f'.diagnostics/theme-{theme.replace(" ","-")}.png')
        page.evaluate("()=>{document.getElementById('serverSettingsOverlay').classList.add('active');showServerSettingsPage('theme')}")
        page.screenshot(path=f'.diagnostics/theme-settings-{theme.replace(" ","-")}.png')
        page.evaluate("()=>document.getElementById('serverSettingsOverlay').classList.remove('active')")
    print('PAGE_ERRORS',errors)
    assert len(backgrounds) == 5, 'Each theme must have a distinct palette'
    assert not errors, errors
    browser.close()
