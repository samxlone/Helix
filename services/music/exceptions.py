class MusicError(Exception):
    pass


class ProviderError(MusicError):
    pass


class PlaybackError(MusicError):
    pass
