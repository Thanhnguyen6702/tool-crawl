"""
Base Processor — Abstract interface for all processing steps.
"""

import abc
import logging
from typing import Any

log = logging.getLogger(__name__)


class Processor(abc.ABC):
    """
    Abstract processor. Operates on a list of item dicts (from DB).

    Subclass and implement:
      - process(items) -> list[dict]
      - name property
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @abc.abstractmethod
    async def process(self, items: list[dict]) -> list[dict]:
        """Process items and return (possibly filtered/modified) list."""
        ...
