"""
Every connector takes a FetchSource and returns a plain list of dicts —
nothing here knows about Django models beyond that, so a connector is
testable with zero database access.

Keys per item (only `title` is required; the rest are optional):
    title, description, organization, location, opportunity_url,
    image_url, application_deadline (datetime | None),
    source_published_at (datetime | None),
    sections (list — the description split into named sections; see
    apps/ingestion/sections.py)
"""

from abc import ABC, abstractmethod


class BaseConnector(ABC):
    def __init__(self, source):
        self.source = source

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Fetch and return raw opportunity items. Raise on failure rather
        than returning an empty list, so the caller can distinguish
        'nothing new' from 'the fetch broke'."""
        raise NotImplementedError
