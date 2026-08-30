from django.urls import path

from . import views

urlpatterns = [
    path("api/bulletins/", views.bulletins, name="bulletins"),
    path("api/bulletins/<uuid:pk>/", views.bulletin, name="bulletin"),
    path("", views.app, name="app"),
]
