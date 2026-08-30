from django.urls import path

from . import views

urlpatterns = [
    path("api/product-pages/", views.product_pages, name="product_pages"),
    path("api/bulletins/", views.bulletins, name="bulletins"),
    path("api/bulletins/<int:pk>/", views.bulletin, name="bulletin"),
    path("api/bulletins/<int:pk>/publish/", views.publish, name="publish"),
    path("", views.app, name="app"),
]
