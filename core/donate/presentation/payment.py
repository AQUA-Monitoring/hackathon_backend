from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.views import View, APIView

import mercadopago, os, uuid, json

from core.donate.services.payment import PaymentService

class CardAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        payment = PaymentService.payment_card(request)
        if request.method == 'POST':
            print(payment.get("status"))
            if payment.get("status") >= 400:
                return JsonResponse(payment, safe=False)    
        return JsonResponse({'error': 'método não permitido'}, status=405)
    
class PixAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        payment = PaymentService.payment_pix(request)
        if request.method == 'POST':
            return JsonResponse(payment, safe=False)    
        return JsonResponse({'error': 'método não permitido'}, status=405)
    
class SavedCardAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        card = PaymentService.saved_card(request)
        if request.method == 'POST':
            return JsonResponse(card, safe=False)
        return JsonResponse({'error': 'método não permitido'}, status=405)
    
class PaymentWebhookAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        result = PaymentService.create_webhook(request)
        return JsonResponse(result, safe=False)