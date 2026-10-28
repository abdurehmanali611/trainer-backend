from django.urls import path

from . import views_admin as v

urlpatterns = [
    path("auth/login/", v.AdminLoginView.as_view()),
    path("dashboard/summary/", v.DashboardSummaryView.as_view()),
    path("reports/analytics/", v.DashboardSummaryView.as_view()),
    path("trainers/", v.TrainersView.as_view()),
    path("trainers/<int:trainer_id>/", v.TrainerDetailView.as_view()),
    path("trainers/<int:trainer_id>/billing/", v.TrainerBillingView.as_view()),
    path("trainers/<int:trainer_id>/access/", v.TrainerAccessView.as_view()),
    path("trainers/<int:trainer_id>/payments/", v.TrainerPaymentsView.as_view()),
    path("payments/pending/", v.PendingPaymentsView.as_view()),
    path("payments/<int:payment_id>/approve/", v.PaymentApproveView.as_view()),
    path("payments/<int:payment_id>/reject/", v.PaymentRejectView.as_view()),
    path("pricing/", v.PricingView.as_view()),
    path("pricing/<int:plan_id>/", v.PricingDetailView.as_view()),
    path("sales-agents/", v.SalesAgentsView.as_view()),
    path("sales-agents/<int:agent_id>/", v.SalesAgentDetailView.as_view()),
    path("clients/", v.ClientsView.as_view()),
    path("clients/<int:client_id>/access/", v.ClientAccessView.as_view()),
    path("audit/", v.AuditView.as_view()),
    path("signups/", v.SignupsView.as_view()),
    path("chat/threads/", v.ChatThreadsView.as_view()),
    path("chat/directory/", v.ChatDirectoryView.as_view()),
    path("chat/threads/<int:trainer_id>/", v.ChatThreadView.as_view()),
    path("chat/broadcast/", v.ChatBroadcastView.as_view()),
    path("chat/start/", v.ChatStartView.as_view()),
]
