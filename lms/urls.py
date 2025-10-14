from django.urls import path
from . import views

app_name = "lms"

urlpatterns = [
    # HOME
    path("", views.home, name="home"),

    # Catálogo
    path("catalogo/", views.catalog, name="catalog"),

    # Curso / Etapa / Quiz
    path("curso/<slug:slug>/", views.course_detail, name="course_detail"),
    path("curso/<slug:course_slug>/etapa/<slug:stage_slug>/", views.stage_detail, name="stage_detail"),
    path("curso/<slug:course_slug>/etapa/<slug:stage_slug>/quiz/", views.quiz_take, name="quiz_take"),

    # Checkout + Webhook
    path("checkout/", views.checkout_view, name="checkout"),
    path("webhooks/pago/", views.webhook_paid, name="webhook_paid"),

    # Perfil
    path("perfil/", views.profile, name="profile"),

    # Panel admin “ligero”
    path("panel-admin/", views.admin_panel, name="admin_panel"),
    path("panel-admin/pedido/<int:pk>/estado/", views.admin_order_status, name="admin_order_status"),
    path("panel-admin/pedido/<int:pk>/eliminar/", views.admin_order_delete, name="admin_order_delete"),
    path("panel-admin/usuario/<int:user_id>/", views.admin_user_detail, name="admin_user_detail"),

    # Logout robusto (ya lo tenés)
    path("salir/", views.logout_view, name="logout"),
]
# ...rutas existentes...


