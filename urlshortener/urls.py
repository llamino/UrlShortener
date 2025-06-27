# urlshortener/urls.py
from django.urls import path
from urlshortener.views import ShortenURLAPI, RedirectView, ClickReportAPI, AddLinkApi

# from urlshortener.add import extract_links_data_to_models
app_name = 'shortener'

urlpatterns = [
    path('shorten/', ShortenURLAPI.as_view(), name='shorten-url'),
    path('report/<str:short_code>/', ClickReportAPI.as_view(), name='click-report'),
    path('<str:short_code>/', RedirectView.as_view(), name='redirect'),
    path('add_links/', AddLinkApi.as_view())
]
