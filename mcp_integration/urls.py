from django.urls import path

from .views import ToolExecuteView, ToolListView

urlpatterns = [
    path('', ToolListView.as_view(), name='tool-list'),
    path('<slug:slug>/execute/', ToolExecuteView.as_view(), name='tool-execute'),
]
