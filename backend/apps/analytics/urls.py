from django.urls import path

from .views import PageViewHitView

urlpatterns = [
    path("hit/", PageViewHitView.as_view(), name="analytics-hit"),
]
