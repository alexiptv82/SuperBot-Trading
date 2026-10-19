from .policy import Policy


def research_policy():
    """Independent illustrative policy. Partial proposals disabled."""
    return Policy("bull", "research-1", 2.0, 3, 2.5, 1.25, 1.5, .8, .6, 14400000, 1.0)
