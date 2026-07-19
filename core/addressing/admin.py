from django.contrib import admin
from core.addressing.models import Address, AddressReference, GeodataDataset, Neighborhood, Region, City, Street


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "street",
        "number",
        "city",
        "city_ref",
        "state",
        "country",
        "zipcode",
        "updated_at",
    )
    search_fields = ("street", "city", "zipcode")
    list_filter = ("city", "state", "country")
    list_per_page = 25
    autocomplete_fields = ("city_ref", "neighborhood", "street_ref", "address_reference")


@admin.register(Neighborhood)
class NeighborhoodAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "official_code", "city", "region", "is_active", "updated_at")
    search_fields = ("name", "normalized_name", "official_code", "city")
    list_filter = ("city", "region", "is_active")
    autocomplete_fields = ("region",)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "official_code", "city", "is_active", "updated_at")
    search_fields = ("name", "normalized_name", "official_code", "city")
    list_filter = ("city", "is_active")


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "official_code", "is_active", "created_at", "updated_at")
    search_fields = ("name", "normalized_name", "official_code")
    list_filter = ("is_active",)


@admin.register(GeodataDataset)
class GeodataDatasetAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "kind", "authority", "source_version", "status", "retrieved_at")
    list_filter = ("city", "kind", "status", "authority")
    search_fields = ("title", "authority", "sha256")


@admin.register(Street)
class StreetAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "source_record_id", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name", "source_record_id")


@admin.register(AddressReference)
class AddressReferenceAdmin(admin.ModelAdmin):
    list_display = ("street_name", "number", "modifier", "address_type", "species", "city", "zipcode", "is_active")
    list_filter = ("city", "address_type", "species", "is_active")
    search_fields = ("street_name", "number", "modifier", "zipcode", "source_record_id")
