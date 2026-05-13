class DistliftError(Exception):
    """Base class for all distlift errors."""


class ConfigurationError(DistliftError):
    """Invalid or missing configuration."""


class GitStateError(DistliftError):
    """Git repository is in an unexpected or unsafe state."""


class VersionError(DistliftError):
    """Version string is malformed or an invalid bump was requested."""


class ManifestUpdateError(DistliftError):
    """Failed to read or write a manifest file."""


class ReleasePlanError(DistliftError):
    """Could not build a valid release plan."""


class UnsupportedLanguageError(DistliftError):
    """The requested language is not supported by any loaded plugin."""


class PublishError(DistliftError):
    """Build or publish of package artifacts failed."""


class PluginError(DistliftError):
    """Plugin discovery, loading, or registration failed."""
