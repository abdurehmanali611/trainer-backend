from django.urls import path

from . import (
    views_billing,
    views_chat,
    views_clients,
    views_common,
    views_dashboard,
    views_plans,
    views_schedule,
)

urlpatterns = [
    # Dashboard
    path("dashboard/", views_dashboard.DashboardView.as_view()),
    path("dashboard/workload/", views_dashboard.WorkloadView.as_view()),

    # Clients
    path("clients/", views_clients.ClientListView.as_view()),
    path("clients/<int:pk>/", views_clients.ClientDetailView.as_view()),
    path("clients/<int:pk>/otp/", views_clients.ClientOtpView.as_view()),
    path("clients/<int:pk>/mode/", views_clients.ClientModeView.as_view()),
    path("clients/<int:pk>/measurements/", views_clients.MeasurementListView.as_view()),
    path("clients/<int:pk>/photos/", views_clients.ProgressPhotoListCreateView.as_view()),
    path("photos/<int:pk>/", views_clients.ProgressPhotoDeleteView.as_view()),
    path("clients/<int:pk>/records/", views_clients.PersonalRecordListCreateView.as_view()),
    path("clients/<int:pk>/food-diary/", views_clients.FoodDiaryReviewView.as_view()),
    path(
        "clients/<int:pk>/food-diary/<int:entry_id>/feedback/",
        views_clients.FoodDiaryFeedbackView.as_view(),
    ),
    path("clients/<int:pk>/water/", views_clients.WaterLogReviewView.as_view()),
    path(
        "clients/<int:pk>/water/<int:log_id>/feedback/",
        views_clients.WaterLogReviewView.as_view(),
    ),
    path("clients/<int:pk>/attendance/", views_clients.ClientAttendanceView.as_view()),
    path(
        "clients/<int:pk>/workout-progress/",
        views_clients.ClientWorkoutProgressView.as_view(),
    ),

    # Plans
    path("exercises/", views_plans.ExerciseListView.as_view()),
    path("exercises/<int:pk>/", views_plans.ExerciseDetailView.as_view()),
    path("workout-plans/", views_plans.WorkoutPlanListCreateView.as_view()),
    path("workout-plans/<int:pk>/", views_plans.WorkoutPlanDetailView.as_view()),
    path("workout-plans/<int:pk>/assign/", views_plans.WorkoutPlanAssignView.as_view()),
    path("diet-plans/", views_plans.DietPlanListCreateView.as_view()),
    path("diet-plans/<int:pk>/", views_plans.DietPlanDetailView.as_view()),
    path("diet-plans/<int:pk>/assign/", views_plans.DietPlanAssignView.as_view()),
    path("ai/suggest-plan/", views_plans.AISuggestPlanView.as_view()),

    # Scheduling
    path("sessions/", views_schedule.SessionListCreateView.as_view()),
    path("sessions/<int:pk>/", views_schedule.SessionDetailView.as_view()),
    path("requests/", views_schedule.RequestQueueView.as_view()),
    path(
        "requests/reschedule/<int:pk>/decide/",
        views_schedule.RescheduleDecideView.as_view(),
    ),
    path(
        "requests/permission/<int:pk>/decide/",
        views_schedule.PermissionDecideView.as_view(),
    ),
    path("attendance/", views_schedule.AttendanceListView.as_view()),

    # Billing
    path("packages/", views_billing.PackageListCreateView.as_view()),
    path("packages/<int:pk>/", views_billing.PackageDetailView.as_view()),
    path("periods/", views_billing.PeriodListCreateView.as_view()),
    path("invoices/", views_billing.InvoiceListView.as_view()),
    path("invoices/<int:pk>/", views_billing.InvoiceDetailView.as_view()),
    path("invoices/<int:pk>/forgive/", views_billing.InvoiceForgiveView.as_view()),
    path("invoices/<int:pk>/transfer/", views_billing.InvoiceTransferView.as_view()),
    path("payments/", views_billing.PaymentListCreateView.as_view()),
    path("payments/<int:pk>/decide/", views_billing.PaymentDecideView.as_view()),
    path("billing/summary/", views_billing.BillingSummaryView.as_view()),
    path(
        "payment-instructions/", views_billing.PaymentInstructionListCreateView.as_view()
    ),
    path(
        "payment-instructions/<int:pk>/", views_billing.PaymentInstructionDetailView.as_view()
    ),

    # Chat
    path("chat/threads/", views_chat.ThreadListView.as_view()),
    path("chat/threads/<int:client_id>/", views_chat.ThreadMessagesView.as_view()),
    path("chat/threads/<int:client_id>/read/", views_chat.ThreadReadView.as_view()),
    path("chat/broadcast/", views_chat.BroadcastView.as_view()),

    # Notifications & devices
    path("notifications/", views_common.NotificationListView.as_view()),
    path("notifications/<int:pk>/read/", views_common.NotificationReadView.as_view()),
    path("devices/", views_common.DeviceRegisterView.as_view()),
]
