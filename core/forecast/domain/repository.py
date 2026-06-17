from abc import ABC, abstractmethod
from typing import List, Dict

class MachineLearningRepository(ABC):
    @abstractmethod
    def getCoords(self) -> List[Dict[str, float]]:
        pass

    def getWeatherByCoord(self, lat: float, lon: float):
        pass

    @abstractmethod
    def forecast(self, lat: float, lon: float, date: str, flood: float, probability: float):
        pass