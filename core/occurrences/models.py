from django.db import models
import os, geopandas as gpd
from core.addressing.infra.models import Neighborhood

class Occurrence(models.Model):
    date = models.DateTimeField()

    class Situation(models.IntegerChoices):
        ALERTA = 1, "Alerta"
        ATENCAO = 2, "Atenção"
        EMERGENCIA = 3, "Emergência"
        NORMALIDADE = 4, "Normalidade"
    situation = models.IntegerField(choices=Situation.choices, default=Situation.NORMALIDADE)

    class Type(models.IntegerChoices):
        ALAGAMENTO = 1, "Alagamento"
        CHUVAS_INTENSAS = 2, "Chuvas Intensas"
        ENXURRADA = 3, "Enxurrada"
        INUNDACAO = 4, "Inundação"
    type = models.IntegerField(choices=Type.choices, default=Type.ALAGAMENTO)

    neighborhood = models.ManyToManyField(Neighborhood, related_name="occorrences")

    def __str__(self):
        return f'{self.situation} - {self.date} - {self.neighborhood}'