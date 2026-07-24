"""Audio filter pipeline stubs.
Real DSP/FFmpeg filter implementations will be added in later phases.
"""


class FilterChain:
    def __init__(self):
        self.active = {}

    def enable(self, name: str, **kwargs):
        self.active[name] = kwargs

    def disable(self, name: str):
        if name in self.active:
            del self.active[name]

    def list_active(self):
        return dict(self.active)
