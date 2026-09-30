"""A shared page handle preserves document recycling across evidence refresh."""
class PageOwner:
    def __init__(self, page):
        self.page = page

    def __getattr__(self, name):
        return getattr(self.page, name)

    def recycle(self):
        old = self.page
        new = old.context.new_page()  # failure leaves original untouched
        self.page = new
        try:
            old.close()
        except Exception:
            # New page remains usable; caller records cleanup failure.
            raise
