#!/usr/bin/env python3
"""
paa.py: People Also Ask / question-expansion collector (PLACEHOLDER).

PAA carries the highest source weight in the plan because it is literal,
measurable search demand (PROJECT_PLAN.md 5, 6). It needs a paid API
(DataForSEO or AlsoAsked), so this is a scaffold that stays a clean no-op until
the credentials are added. Wire the secret in and implement fetch(); nothing
else downstream changes, since it emits the standard question-lane item shape.

Required secret (set as a repo Actions secret, then in listen-monthly.yml env):
  DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD   (or ALSOASKED_API_KEY)

Seed keywords live in sources.yaml config.queries (see PROJECT_PLAN.md 6.1).
Cadence: monthly.
"""
import os

import common  # noqa: F401  (used once fetch() is implemented)


def collect(source):
    login = os.environ.get("DATAFORSEO_LOGIN")
    alsoasked = os.environ.get("ALSOASKED_API_KEY")
    if not (login or alsoasked):
        print(f"  - {source['id']}: PAA placeholder (awaiting DATAFORSEO_/ALSOASKED_ secret)")
        return []
    # TODO(premium): POST seed queries to the provider, map each returned
    # "people also ask" question to a question-lane item:
    #   {source_id, lane: "question", native_id: <question hash>, url: <serp url>,
    #    title: <question>, text: <question>, published_at: <run date>,
    #    engagement: {volume: <monthly searches>}}
    print(f"  - {source['id']}: PAA credentials present but fetch() not implemented yet")
    return []
