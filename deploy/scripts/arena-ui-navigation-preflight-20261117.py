#!/usr/bin/env python3
"""No-network release-navigation audit for AI Arena read-only preview.

Static-only inspection of the React files; this does NOT replace a React
compile or a browser test. No process, environment, files, frontend bundle,
service, broker account or portfolio is changed.
"""
from __future__ import annotations
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "frontend/src"


def check():
    overview = (FRONT / "pages/Overview.js").read_text(encoding="utf-8")
    arena = (FRONT / "pages/BrainArena.js").read_text(encoding="utf-8")
    app = (FRONT / "App.js").read_text(encoding="utf-8")
    nav = (FRONT / "components/NavBar.js").read_text(encoding="utf-8")
    model = (FRONT / "brainArenaModel.js").read_text(encoding="utf-8")

    requirements = {
        "overview_has_discoverable_arena_link": (
            'to="/arena"' in overview and
            'Apri AI Arena' in overview and
            "import { Link } from 'react-router-dom';" in overview
        ),
        "authenticated_arena_route_exists": (
            '<Route path="/arena" element={<BrainArena />}' in app
        ),
        "existing_classic_overview_remains": (
            '<Route path="/overview" element={<Overview />}' in app
            and '<Route path="/classic" element={<Dashboard />}' in app
            and 'Falco' in overview and 'Toro' in overview
        ),
        "original_paper_navigation_preserved": (
            "{ path: '/overview'" in nav and
            "{ path: '/classic'" in nav and
            "{ path: '/trades'" in nav and
            "{ path: '/performance'" in nav
        ),
        "three_wallet_cards_without_invented_trades": (
            "ARENA_PROFILES.map(" in arena and
            "sanitizedTrial('qwen'" in arena and
            "sanitizedTrial('minimax'" in arena and
            "Non avviato" in arena and
            'trialTotalPnl(rows)' in arena
        ),
        "existing_brain_history_not_trial": (
            "Storico precedente" in arena and
            "v3_existing_brain_paper" in arena and
            "trial_comparable: false" in model
        ),
        "shadow_api_explicit_opt_in": (
            "REACT_APP_BRAIN_ARENA_SHADOW_API === '1'" in arena
            and "API.get('/api/v3/arena'" in arena
        ),
        "user_interface_never_sends_orders": (
            not re.search(r"\bAPI\.(?:post|put|patch|delete)\s*\(", arena)
            and not re.search(r"\b(?:fetch|axios)\s*\(", arena)
            and "Questa pagina non può aprire o chiudere posizioni" in arena
        ),
        "not_pretending_running_14_day_trial": (
            "in attesa di attivazione comune" in arena and
            "Capitale previsto per il test" in arena
        ),
    }
    for name, ok in requirements.items():
        print("ARENA_UI " + name + "=" + ("PASS" if ok else "FAIL"))
    print("ARENA_UI checks=" + str(sum(requirements.values())) + "/" +
          str(len(requirements)))
    print("ARENA_UI backend_changes=0 paid_AI_calls=0 orders=0")
    print("ARENA_UI RESULT=" + (
        "PREVIEW_NAVIGATION_STATIC_READY_NOT_BUILT_OR_DEPLOYED"
        if all(requirements.values())
        else "STATIC_AUDIT_FAILED"
    ))
    return 0 if all(requirements.values()) else 2


if __name__ == "__main__":
    raise SystemExit(check())
