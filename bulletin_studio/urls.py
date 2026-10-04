from django.urls import path

from . import views

urlpatterns = [
    path("api/product-pages/", views.product_pages, name="product_pages"),
    path("api/images/", views.images, name="images"),
    path("api/map-config/", views.map_config, name="map_config"),
    path("api/forecast/", views.forecast, name="forecast"),
    path("api/bulletins/", views.bulletins, name="bulletins"),
    path("api/bulletins/<int:pk>/", views.bulletin, name="bulletin"),
    path("api/bulletins/<int:pk>/publish/", views.publish, name="publish"),
    path("api/bulletins/<int:pk>/issues/", views.new_issue, name="new_issue"),
    path("", views.app, name="app"),
]
