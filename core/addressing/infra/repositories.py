from typing import Iterable, Optional

from core.addressing.domain import entities as d_entities
from core.addressing.domain import repository as d_repo
from core.addressing.infra import models as orm


def _to_domain_neighborhood(m: orm.Neighborhood) -> d_entities.Neighborhood:
    return d_entities.Neighborhood(
        id=str(m.id),
        name=m.name,
        city=m.city,
        region_id=str(m.region_id) if m.region_id else "",
        props=m.props or {},
        geometry=(__import__("json").loads(m.geometry.geojson) if m.geometry else None),
    )


def _to_domain_region(m: orm.Region) -> d_entities.Region:
    return d_entities.Region(
        id=str(m.id),
        name=m.name,
        city=m.city,
        props=m.props or {},
        geometry=(__import__("json").loads(m.geometry.geojson) if m.geometry else None),
    )


class DjangoNeighborhoodRepository(d_repo.NeighborhoodRepository):
    def get_by_id(self, id: str) -> Optional[d_entities.Neighborhood]:
        try:
            m = orm.Neighborhood.objects.get(id=id)
        except orm.Neighborhood.DoesNotExist:
            return None
        return _to_domain_neighborhood(m)

    def list_by_city(self, city: str) -> Iterable[d_entities.Neighborhood]:
        qs = orm.Neighborhood.objects.filter(city__iexact=city)
        for m in qs.iterator():
            yield _to_domain_neighborhood(m)

    # Extra helpers beyond protocol (kept internal to this module)
    def list_all(self) -> Iterable[d_entities.Neighborhood]:  # type: ignore[override]
        for m in orm.Neighborhood.objects.all().iterator():
            yield _to_domain_neighborhood(m)

    def list_by_city_and_region(self, city: str, region: str) -> Iterable[d_entities.Neighborhood]:  # type: ignore[override]
        qs = orm.Neighborhood.objects.filter(city__iexact=city, region__name__iexact=region)
        for m in qs.iterator():
            yield _to_domain_neighborhood(m)

    def create_neighborhood(self, neighborhood: d_entities.Neighborhood) -> d_entities.Neighborhood:
        m = orm.Neighborhood.objects.create(
            id=neighborhood.id,
            name=neighborhood.name,
            city=neighborhood.city,
            region_id=neighborhood.region_id or None,
            props=neighborhood.props or {},
        )
        return _to_domain_neighborhood(m)

    def update_neighborhood(self, neighborhood: d_entities.Neighborhood) -> d_entities.Neighborhood:
        orm.Neighborhood.objects.filter(id=neighborhood.id).update(
            name=neighborhood.name,
            city=neighborhood.city,
            region_id=neighborhood.region_id or None,
            props=neighborhood.props or {},
        )
        m = orm.Neighborhood.objects.get(id=neighborhood.id)
        return _to_domain_neighborhood(m)


class DjangoRegionRepository(d_repo.RegionRepository):
    def get_by_id(self, id: str) -> Optional[d_entities.Region]:
        try:
            m = orm.Region.objects.get(id=id)
        except orm.Region.DoesNotExist:
            return None
        return _to_domain_region(m)

    def list_by_city(self, city: str) -> Iterable[d_entities.Region]:
        qs = orm.Region.objects.filter(city__iexact=city)
        for m in qs.iterator():
            yield _to_domain_region(m)

    def create_region(self, region: d_entities.Region) -> d_entities.Region:
        m = orm.Region.objects.create(id=region.id, name=region.name, city=region.city, props=region.props or {})
        return _to_domain_region(m)

    def update_region(self, region: d_entities.Region) -> d_entities.Region:
        orm.Region.objects.filter(id=region.id).update(name=region.name, city=region.city, props=region.props or {})
        m = orm.Region.objects.get(id=region.id)
        return _to_domain_region(m)
