from __future__ import annotations
from typing import Callable, Optional


class SyncEntity:
    def __init__(
        self,
        key: str,
        endpoint: str,
        model: type,
        sync_func: Callable[[list[dict], str], tuple[int, int]],
        dependencies: Optional[list[str]] = None,
        description: str = "",
    ):
        self.key = key
        self.endpoint = endpoint
        self.model = model
        self.sync_func = sync_func
        self.dependencies = dependencies or []
        self.description = description


class SyncRegistry:
    def __init__(self):
        self._entities: dict[str, SyncEntity] = {}

    def register(
        self,
        key: str,
        endpoint: str,
        model: type,
        sync_func: Callable[[list[dict], str], tuple[int, int]],
        dependencies: Optional[list[str]] = None,
        description: str = "",
    ) -> SyncEntity:
        entity = SyncEntity(key, endpoint, model, sync_func, dependencies, description)
        self._entities[key] = entity
        return entity

    def get(self, key: str) -> SyncEntity:
        if key not in self._entities:
            raise KeyError(f"Entidade '{key}' não registrada")
        return self._entities[key]

    def list(self) -> list[SyncEntity]:
        return list(self._entities.values())

    def resolve_order(self, keys: Optional[list[str]] = None) -> list[SyncEntity]:
        if keys is None:
            entities = list(self._entities.values())
        else:
            entities = [self.get(k) for k in keys]

        visited: set[str] = set()
        result: list[SyncEntity] = []

        def dfs(entity: SyncEntity):
            if entity.key in visited:
                return
            for dep_key in entity.dependencies:
                if dep_key in self._entities:
                    dfs(self._entities[dep_key])
                else:
                    raise ValueError(
                        f"Dependência '{dep_key}' não encontrada para '{entity.key}'"
                    )
            visited.add(entity.key)
            result.append(entity)

        for entity in entities:
            dfs(entity)

        return result


registry = SyncRegistry()
