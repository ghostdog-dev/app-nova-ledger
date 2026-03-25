from django.contrib import admin
from django.urls import include, path

from accounts.views import callback_page, login_page

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
    path('api/auth/', include('accounts.urls')),
    path('login/', login_page, name='login_page'),
    path('callback/', callback_page, name='callback_page'),
]
