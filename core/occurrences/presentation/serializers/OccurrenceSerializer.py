from rest_framework import serializers
from core.occurrences.models import Occurrence

class OccurrenceSerializer(serializers.Serializer):
    date = serializers.DateField()
    situation = serializers.CharField(source='get_situation_display')
    type = serializers.CharField()
    neighborhood = serializers.CharField()

class OccurrenceSerializer(serializers.Serializer):
    class Meta: 
        model = Occurrence
        fields = '__all__'