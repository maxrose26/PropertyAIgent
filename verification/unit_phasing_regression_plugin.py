"""Offline historical regression authority for fake vision clients only.

Run with the syscall-denial runner and stage1_preservation_plugin. This adds the
existing visual permission to synthetic test policy, never application policy.
Visual tests already inject _FakeVisionClient; network remains kernel-denied.
"""
def pytest_configure(config):
    from verification.stage1_test_context import PAID_ACTIONS
    if "visual.classify" not in PAID_ACTIONS:
        PAID_ACTIONS.append("visual.classify")


def pytest_unconfigure(config):
    from verification.stage1_test_context import PAID_ACTIONS
    if "visual.classify" in PAID_ACTIONS:
        PAID_ACTIONS.remove("visual.classify")
