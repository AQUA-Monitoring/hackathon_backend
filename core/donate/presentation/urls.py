from django.urls import path

from core.donate.presentation.payment import CardAPIView, PixAPIView, SavedCardAPIView, PaymentWebhookAPIView

urlpatterns = [
    path('card/', CardAPIView.as_view(), name='card_api_view'),
    path('pix/', PixAPIView.as_view(), name='pix_api_view'),
    path('saved/', SavedCardAPIView.as_view(), name='saved_card_api_view'),
    path('webhook/', PaymentWebhookAPIView.as_view(), name='webhook_api_view')
]