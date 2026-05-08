from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.views import APIView

import mercadopago, os, uuid, json

from core.donate.services.payment import PaymentService
from core.donate.presentation.serializers import CardSerializer, PixSerializer

class CardAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        serializer = CardSerializer(data=request.data)
        if not serializer.is_valid():
            print(serializer.errors)
            return JsonResponse(serializer.errors, status=400)
        payment = PaymentService.payment_card(serializer.validated_data)
        status = payment.get("status")
        return JsonResponse(payment, safe=False, status=status)
    
class PixAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        serializer = PixSerializer(data=request.data)
        if not serializer.is_valid():
            print(serializer.errors)
            return JsonResponse(serializer.errors, status=400)
        payment = PaymentService.payment_pix(serializer.validated_data)
        response = payment["response"]
        status = payment["status"]
        return JsonResponse(response, safe=False, status=status)
    
class SavedCardAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        card = PaymentService.saved_card(request)
        return JsonResponse(card, safe=False)
    
class PaymentWebhookAPIView(APIView):
    @csrf_exempt
    def post(self, request):
        result = PaymentService.create_webhook(request)
        return JsonResponse(result, safe=False)