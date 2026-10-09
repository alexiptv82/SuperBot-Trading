"""Test end-to-end del login in un browser vero, in HTTPS (come in produzione)."""
import sys
from playwright.sync_api import sync_playwright, expect

URL = 'https://localhost:8443/'
BOOT = 'Iniziale-12!'
NEW = 'NuovaPwd-2026x'
problems = []


def step(msg):
    print('OK  ', msg, flush=True)


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

    try:
        page.goto(URL)
        expect(login_box()).to_be_visible()
        step('pagina di login in HTTPS caricata')

        # occhio mostra/nascondi
        assert login_box().get_attribute('type') == 'password'
        page.get_by_role('button', name='Mostra password').click()
        assert login_box().get_attribute('type') == 'text'
        page.get_by_role('button', name='Nascondi password').click()
        assert login_box().get_attribute('type') == 'password'
        step('occhio: mostra e nasconde')

        # password sbagliata -> deve dire "errata" (vero 401 dal server)
        try_login('sbagliata-xyz-123')
        expect(page.get_by_text('Password errata')).to_be_visible()
        step('password sbagliata: "Password errata" (401 dal server)')

        # password iniziale -> schermata di cambio
        try_login(BOOT)
        expect(page.get_by_text('Primo accesso')).to_be_visible()
        step('password iniziale accettata: schermata di cambio password')

        page.get_by_placeholder('Nuova password (min. 10 caratteri)').fill(NEW)
        page.get_by_placeholder('Ripeti la nuova password').fill(NEW)
        page.get_by_role('button', name='Salva nuova password').click()

        # headless: nessun lettore di impronte -> si entra direttamente (se
        # l'offerta compare, la si rifiuta)
        page.wait_for_timeout(1500)
        if page.get_by_text('Attiva impronta').count():
            page.get_by_role('button', name='Più tardi').click()
        expect(page.get_by_text('Impostazioni')).to_be_visible()
        assert page.evaluate("localStorage.getItem('sb_token')")
        step('nuova password salvata: dentro l\'app')

        # sessione persistente al ricaricamento
        page.reload()
        expect(page.get_by_text('Impostazioni')).to_be_visible()
        step('ricarica pagina: ancora dentro')

        # esco; la password iniziale non deve piu' valere, la nuova si'
        page.evaluate("localStorage.removeItem('sb_token')")
        page.reload()
        expect(login_box()).to_be_visible()
        try_login(BOOT)
        expect(page.get_by_text('Password errata')).to_be_visible()
        step('dopo il cambio la password iniziale non vale piu\'')
        try_login(NEW)
        expect(page.get_by_text('Impostazioni')).to_be_visible()
        step('login con la nuova password riuscito')
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
