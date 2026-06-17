from rest_framework.views import APIView
from rest_framework.response import Response
from datetime import datetime
from core.weather.infra.services.queue import enqueueFillClimates
#from core.weather.presentation.tasks.tasks import fillWeather

class WeatherSearch(APIView):
    def post(self, request):
        try:
            start = "2026-04-29"
            end = datetime.now().strftime("%Y-%m-%d")
            total_tasks, _ = enqueueFillClimates(start, end)
            return Response({
                "status": f'{total_tasks} tarefas enfileiradas com sucesso.'
            })
        except Exception as e:
            print("❌ Erro ao processar ClimaSearch:", str(e))
            return Response({"erro": "Ocorreu um erro interno."}, status=500)