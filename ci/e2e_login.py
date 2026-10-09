"""Test end-to-end in un browser vero, in HTTPS (come in produzione):
aggiornamento dell'app, login, cambio password, password dimenticata."""
import json
import os
import re
import sys
from playwright.sync_api import sync_playwright, expect

URL = 'https://localhost:8443/'
BOOT = 'Iniziale-12!'
NEW = 'NuovaPwd-2026x'
RECOVERED = 'Recuperata-2026y'
MESSAGES = '/tmp/telegram_messages.jsonl'
INDEX = os.environ['BUILD_INDEX']
problems = []


def step(msg):
    print('OK  ', msg, flush=True)


def telegram_texts():
    if not os.path.exists(MESSAGES):
        return []
    return [json.loads(l)['text'] for l in open(MESSAGES) if l.strip()]


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', args=['--ignore-certificate-errors'])
    ctx = browser.new_context(ignore_https_errors=True, viewport={'width': 400, 'height': 800})
    page = ctx.new_page()
    page.set_default_timeout(15000)
    page.on('requestfailed', lambda r: problems.append('richiesta fallita %s %s %s' % (r.method, r.url, r.failure)))
    page.on('console', lambda m: problems.append('console: ' + m.text[:200]) if m.type == 'error' else None)

    def login_box():
        return page.get_by_placeholder('Password', exact=True)

    def try_login(pwd):
        login_box().fill(pwd)
        page.get_by_role('button', name='Accedi').click()

    def in_app():
        expect(page.get_by_text('Impostazioni')).to_be_visible()

    def logout():
        page.evaluate("localStorage.removeItem('sb_token')")
        page.reload()
        expect(login_box()).to_be_visible()

    try:
        # ── aggiornamento dell'app dopo un deploy ──────────────────────────
        page.goto(URL)
        expect(login_box()).to_be_visible()
        step('pagina di login in HTTPS caricata')
        page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.getRegistration().then(r => !!(r && r.active))")
        page.reload()
        page.wait_for_function("!!navigator.serviceWorker.controller")
        step('service worker attivo e in controllo della pagina')
        html = open(INDEX).read()
        assert '<head>' in html
        open(INDEX, 'w').write(html.replace('<head>', '<head><meta name="e2e-marker" content="v2">', 1))
        page.reload()
        assert page.evaluate("!!document.querySelector('meta[name=e2e-marker]')"), \
            'dopo un deploy il primo avvio mostra ancora la versione vecchia'
        step('dopo un "deploy" il primo avvio carica gia\' la versione nuova')

        # ── occhio mostra/nascondi ────────────────────────────────────────
        assert login_box().get_attribute('type') == 'password'
        page.get_by_role('button', name='Mostra password').click()
        assert login_box().get_attribute('type') == 'text'
        page.get_by_role('button', name='Nascondi password').click()
        assert login_box().get_attribute('type') == 'password'
        step('occhio: mostra e nasconde')

        # ── login e cambio password ───────────────────────────────────────
        try_login('sbagliata-xyz-123')
        expect(page.get_by_text('Password errata')).to_be_visible()
        step('password sbagliata: "Password errata" (401 dal server)')
        try_login(BOOT)
        expect(page.get_by_text('Primo accesso')).to_be_visible()
        step('password iniziale accettata: schermata di cambio password')
        page.get_by_placeholder('Nuova password (min. 10 caratteri)').fill(NEW)
        page.get_by_placeholder('Ripeti la nuova password').fill(NEW)
        page.get_by_role('button', name='Salva nuova password').click()
        page.wait_for_timeout(1500)
        if page.get_by_text('Attiva impronta').count():
            page.get_by_role('button', name='Più tardi').click()
        in_app()
        step('nuova password salvata: dentro l\'app')

        # ── password dimenticata ──────────────────────────────────────────
        logout()
        page.get_by_role('button', name='Password dimenticata?').click()
        expect(page.get_by_text('Ti mando un codice')).to_be_visible()
        before = len(telegram_texts())
        page.get_by_role('button', name='Invia codice su Telegram').click()
        expect(page.get_by_placeholder('Codice (8 cifre)')).to_be_visible()
        step('"Password dimenticata?": richiesta codice accettata')
        texts = telegram_texts()
        assert len(texts) == before + 1, 'il codice non e\' arrivato su Telegram'
        code = re.search(r'<b>(\d{8})</b>', texts[-1]).group(1)
        assert code not in page.inner_text('body'), 'il codice e\' visibile nell\'app'
        step('codice arrivato su Telegram (8 cifre) e non visibile nell\'app')

        wrong = '00000000' if code != '00000000' else '11111111'
        page.get_by_placeholder('Codice (8 cifre)').fill(wrong)
        page.get_by_placeholder('Nuova password (min. 10 caratteri)').fill(RECOVERED)
        page.get_by_placeholder('Ripeti la nuova password').fill(RECOVERED)
        page.get_by_role('button', name='Imposta nuova password').click()
        expect(page.get_by_text('Codice errato')).to_be_visible()
        step('codice sbagliato: "Codice errato"')

        page.get_by_placeholder('Codice (8 cifre)').fill(code)
        page.get_by_role('button', name='Imposta nuova password').click()
        page.wait_for_timeout(1500)
        if page.get_by_text('Attiva impronta').count():
            page.get_by_role('button', name='Più tardi').click()
        in_app()
        assert any('cambiata' in t for t in telegram_texts()), 'nessun avviso su Telegram a cambio avvenuto'
        step('codice giusto: nuova password impostata, dentro l\'app, avviso su Telegram')

        logout()
        try_login(NEW)
        expect(page.get_by_text('Password errata')).to_be_visible()
        step('la password precedente non vale piu\'')
        try_login(RECOVERED)
        in_app()
        step('login con la password recuperata riuscito')
    except Exception as e:
        print('FALLITO:', type(e).__name__, str(e)[:600], flush=True)
        try:
            print('TESTO PAGINA:', page.inner_text('body')[:500].replace('\n', ' | '), flush=True)
        except Exception:
            pass
        print('PROBLEMI RETE/CONSOLE:', problems[:8], flush=True)
        browser.close()
        sys.exit(1)
    print('PROBLEMI RETE/CONSOLE (info):', problems[:8], flush=True)
    browser.close()
