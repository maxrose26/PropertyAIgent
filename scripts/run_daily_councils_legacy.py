"""Preserved manual legacy workflow. Not the daily intake or activation authority.

Uses the original explicit launch:run_daily_councils machine permission. This
module grants no permission and must not be installed as a scheduled fallback.
"""
from scripts.run_daily_councils import legacy_main

if __name__ == '__main__':
    raise SystemExit(legacy_main())
