from abc import ABC, abstractmethod

class AlertStrategy(ABC):
    @abstractmethod
    def get_priority(self) -> str:
        pass

    @abstractmethod
    def get_description(self) -> str:
        pass

class APIStrategy(AlertStrategy):
    def get_priority(self) -> str:
        return "P0"          # you said API is most dangerous
    
    def get_description(self) -> str:
        return "API failure - service unreachable"

class RDBMSStrategy(AlertStrategy):
    def get_priority(self) -> str:
        return "P0"
    def get_description(self) -> str:
        return "RDBMS Failure"

class QueueStrategy(AlertStrategy):
    def get_priority(self) -> str:
        return "P1"
    def get_description(self) -> str:
        return "Queue Failure"

class CacheStrategy(AlertStrategy):
    def get_priority(self) -> str:
        return "P2"
    def get_description(self) -> str:
        return "Cache Failure"
    
STRATEGY_MAP = {
    "API":   APIStrategy(),
    "RDBMS": RDBMSStrategy(),
    "QUEUE": QueueStrategy(),
    "CACHE": CacheStrategy(),
}

def get_alert(component_type: str):
    if component_type not in STRATEGY_MAP:
        raise ValueError(f"unknown component type:{component_type}")
    
    strategy = STRATEGY_MAP[component_type]
    return strategy.get_priority(),strategy.get_description()
            