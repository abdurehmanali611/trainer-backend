from django.urls import path

from . import views_trainer as v

urlpatterns = [
    path("billing/", v.PlatformBillingView.as_view()),
    path("billing/locked/", v.LockedBillingView.as_view()),
    path("payments/", v.PlatformPaymentSubmitView.as_view()),
    path("payments/locked/", v.LockedPaymentSubmitView.as_view()),
    path("chat/", v.PlatformChatView.as_view()),
    path("chat/unread/", v.PlatformChatUnreadView.as_view()),
]
