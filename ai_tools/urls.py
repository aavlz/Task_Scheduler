from django.urls import path

from .views import TaskSummaryView, MorningNotificationView, EveningNotificationView

urlpatterns = [
    path('summary/', TaskSummaryView.as_view(), name='ai-summary'),
    path('morning/', MorningNotificationView.as_view(), name='ai-morning-notification'),
    path('evening/', EveningNotificationView.as_view(), name='ai-evening-notification'),
]
