import config

class ShariaFilter:
    def __init__(self):
        self.whitelist = config.WHITELIST_PAIRS

    def is_compliant(self, symbol):
        """Checks if a symbol is in the pre-approved Sharia whitelist."""
        return symbol in self.whitelist
