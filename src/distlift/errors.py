"""Typed exception hierarchy for distlift."""


class DistliftError(Exception):
    """Base class for all distlift errors.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class ConfigurationError(DistliftError):
    """Invalid or missing configuration.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class GitStateError(DistliftError):
    """Git repository is in an unexpected or unsafe state.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class VersionError(DistliftError):
    """Version string is malformed or an invalid bump was requested.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class ManifestUpdateError(DistliftError):
    """Failed to read or write a manifest file.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class ReleasePlanError(DistliftError):
    """Could not build a valid release plan.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class UnsupportedLanguageError(DistliftError):
    """The requested language is not supported by any loaded plugin.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class PublishError(DistliftError):
    """Build or publish of package artifacts failed.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class PluginError(DistliftError):
    """Plugin discovery, loading, or registration failed.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class ChangelogError(DistliftError):
    """Failed to parse, format, or write a changelog document.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """
