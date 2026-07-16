from django.contrib import admin
from core.occurrences.models import Occurrence

@admin.register(Occurrence)
class Occurrence(admin.ModelAdmin):
    list_display = ('date',)
    #search_fields = ("neighborhood",)