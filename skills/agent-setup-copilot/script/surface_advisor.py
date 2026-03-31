#!/usr/bin/env python3
"""
Surface advisor for provider / CLI / IDE / API integration fit.
Reads provider_surface_compatibility from the ontology snapshot and returns
ranked candidates for OpenClaw / headless / auth preferences.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def load_relation_instances() -> dict:
    for base in [
        Path.home() / '.cache' / 'agent-setup-copilot',
        Path(__file__).parent / 'bundle',
    ]:
        path = base / 'instances' / 'relation.yaml'
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            return (data or {}).get('instances', {}) or {}
    raise FileNotFoundError('relation.yaml not found in cache or bundle')


SUPPORT_SCORE = {
    'native': 5,
    'supported': 4,
    'possible': 3,
    'experimental': 2,
    'unknown': 1,
    'unsupported': 0,
}
FIT_SCORE = {'high': 3, 'medium': 2, 'low': 1, 'unknown': 0}


def score_item(item: dict, prefer_openclaw: bool, require_headless: bool, auth_mode: str | None):
    score = SUPPORT_SCORE.get(item.get('openclaw_support_level', 'unknown'), 0)
    score += FIT_SCORE.get(item.get('headless_automation_fit', 'unknown'), 0)

    if prefer_openclaw and item.get('openclaw_support_level') in ('supported', 'native'):
        score += 2
    if require_headless and item.get('headless_automation_fit') == 'high':
        score += 2
    if require_headless and item.get('headless_automation_fit') in ('low', 'unknown'):
        score -= 2
    if auth_mode:
        modes = item.get('auth_modes', []) or []
        if auth_mode in modes:
            score += 2
        else:
            score -= 1
    return score


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Recommend provider/product surfaces from ontology compatibility metadata')
    ap.add_argument('--prefer-openclaw', action='store_true')
    ap.add_argument('--require-headless', action='store_true')
    ap.add_argument('--auth-mode', choices=['api_key', 'oauth', 'local_login', 'browser_session'])
    ap.add_argument('--top-k', type=int, default=5)
    args = ap.parse_args()

    instances = load_relation_instances()
    compat = instances.get('provider_surface_compatibility', {}) or {}

    ranked = []
    for key, item in compat.items():
        ranked.append({
            'id': key,
            'score': score_item(item, args.prefer_openclaw, args.require_headless, args.auth_mode),
            **item,
        })

    ranked.sort(key=lambda x: (-x['score'], x['id']))
    out = {
        'filters': {
            'prefer_openclaw': args.prefer_openclaw,
            'require_headless': args.require_headless,
            'auth_mode': args.auth_mode,
        },
        'results': ranked[: args.top_k],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
