from django.db import models
from core.addressing.infra.models import Neighborhood

class Occurrence(models.Model):
    date = models.DateField()
    class Situation(models.IntegerChoices):
        ALERTA = 1, "alerta"
        ATENCAO = 2, "atencao"
        MOBILIZACAO = 3, "mobilizacao"
        NORMALIDADE = 4, "normalidade"
    situation = models.IntegerField(choices=Situation.choices, default=Situation.NORMALIDADE)

    class Type (models.IntegerChoices): 
        ALAGAMENTO = 1, "alagamento"
        CHUVAS_INTENSAS = 2, "Chuvas Intensas"
        ENXURRADA = 3, "Enxurrada"
        INUNDACAO = 4, "Inundação"
    type = models.IntegerField(choices=Type.choices, default=Type.ALAGAMENTO)
    
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.PROTECT, related_name="ocorrencias", null=True, blank=True)

    def __str__(self):
        return f'{self.situation} - {self.date} - {self.neighborhood}'