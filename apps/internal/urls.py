from django.urls import path

from . import views_auth, views_client

urlpatterns = [
    # Auth (no client JWT — service token only)
    path("auth/client-login/", views_auth.ClientLoginView.as_view()),
    path("auth/access-status/", views_auth.ClientAccessStatusView.as_view()),
    path("auth/lock-payment-submit/", views_auth.ClientLockPaymentSubmitView.as_view()),
    path("auth/change-credential/", views_auth.ClientChangeCredentialView.as_view()),
    path("auth/reset-request/", views_auth.ClientResetRequestView.as_view()),
    path("auth/reset-confirm/", views_auth.ClientResetConfirmView.as_view()),

    # Client-scoped (client JWT + service token)
    path("client/me/", views_client.MeView.as_view()),
    path("client/today/", views_client.TodayView.as_view()),
    path("client/plans/", views_client.PlanListView.as_view()),
    path("client/plans/<int:pk>/", views_client.PlanDetailView.as_view()),
    path("client/diet/", views_client.DietView.as_view()),
    path("client/exercises/", views_client.ExerciseLibraryView.as_view()),
    path("client/schedule/", views_client.ScheduleView.as_view()),
    path("client/requests/reschedule/", views_client.RescheduleRequestCreateView.as_view()),
    path("client/requests/permission/", views_client.PermissionRequestCreateView.as_view()),
    path("client/requests/", views_client.MyRequestsView.as_view()),
    path("client/attendance/", views_client.MyAttendanceView.as_view()),
    path("client/billing/", views_client.MyBillingView.as_view()),
    path("client/invoices/", views_client.InvoiceListView.as_view()),
    path("client/chat/", views_client.ChatMessagesView.as_view()),
    path("client/chat/read/", views_client.ChatReadView.as_view()),
    path("client/diary/", views_client.FoodDiaryView.as_view()),
    path("client/water/", views_client.WaterView.as_view()),
    path("client/measurements/", views_client.MeasurementsView.as_view()),
    path("client/photos/", views_client.PhotosView.as_view()),
    path("client/records/", views_client.RecordsView.as_view()),
    path("client/workout/log/", views_client.WorkoutLogView.as_view()),
    path("client/workout/complete/", views_client.WorkoutCompleteView.as_view()),
    path("client/achievements/", views_client.AchievementsView.as_view()),
    path("client/notifications/", views_client.NotificationListView.as_view()),
    path("client/devices/", views_client.DeviceRegisterView.as_view()),
]
