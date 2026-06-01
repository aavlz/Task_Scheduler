from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskCategoryViewSet, TaskViewSet

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'categories', TaskCategoryViewSet, basename='category')

urlpatterns = [
    path('', include(router.urls)),
]
