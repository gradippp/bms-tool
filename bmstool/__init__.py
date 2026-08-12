"""BookMyShow showtimes CLI."""

__version__ = "0.1.0"


class BmsError(Exception):
    """Base error for all bmstool failures."""


class BmsUrlError(BmsError):
    """The supplied URL is not a BookMyShow buytickets URL."""


class BmsFetchError(BmsError):
    """The page could not be fetched."""


class BmsParseError(BmsError):
    """The page was fetched but its structure was not understood."""
