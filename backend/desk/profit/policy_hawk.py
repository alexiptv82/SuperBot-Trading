from .policy import Policy


def research_policy():
    """Illustrative, uncalibrated; not approved for activation."""
    return Policy("hawk", "research-1", 1.5, 2, 2.0, 1.0, 1.5, .8, .6, 3600000, 1.0)
