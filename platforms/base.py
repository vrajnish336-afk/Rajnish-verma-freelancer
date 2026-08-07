from abc import ABC, abstractmethod
from typing import List
from models.opportunity import Opportunity

class BasePlatform(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def scan_opportunities(self) -> List[Opportunity]:
        """
        Scan platform for real, verified opportunities.
        Must NEVER invent a reward.
        """
        pass
