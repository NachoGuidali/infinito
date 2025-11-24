from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "lms"

urlpatterns = [
    # HOME
    path("", views.home, name="home"),

    # --- Signup (registro + confirmación por email) ---
    path("crear-cuenta/", views.signup, name="signup"),
    path("crear-cuenta/hecho/", views.signup_done, name="signup_done"),
    path("crear-cuenta/confirmar/<str:token>/", views.signup_confirm, name="signup_confirm"),
    # Alias opcional corto
    path("signup/", RedirectView.as_view(pattern_name="lms:signup", permanent=False)),

    # Catálogo (general) + atajos
    path("catalogo/", views.catalog, name="catalog"),
    path("cursos/", RedirectView.as_view(url="/catalogo/?type=course"), name="catalog_courses"),
    path("capacitaciones/", RedirectView.as_view(url="/catalogo/?type=training"), name="catalog_trainings"),

    # Curso / Etapa / Quiz
    path("curso/<slug:slug>/", views.course_detail, name="course_detail"),
    path("curso/<slug:course_slug>/etapa/<slug:stage_slug>/", views.stage_detail, name="stage_detail"),
    path("curso/<slug:course_slug>/etapa/<slug:stage_slug>/quiz/", views.quiz_take, name="quiz_take"),

    # ------- Carrito -------
    path("carrito/", views.cart_view, name="cart_view"),
    path("carrito/agregar/", views.cart_add, name="cart_add"),                # POST: type=stage|bundle, id=<int>
    path("carrito/quitar/<str:key>/", views.cart_remove, name="cart_remove"), # key p.ej. "stage:12" / "bundle:3"
    path("carrito/vaciar/", views.cart_clear, name="cart_clear"),
    path("carrito/pagar/", views.cart_go_checkout, name="cart_go_checkout"),  # crea Purchase y redirige a /checkout/

    # Checkout + Webhook
    path("checkout/", views.checkout_view, name="checkout"),
    path("webhooks/pago/", views.webhook_paid, name="webhook_paid"),

    # Perfil
    path("perfil/", views.profile, name="profile"),

    # Panel admin “ligero”
    path("panel-admin/", views.admin_panel, name="admin_panel"),
    path("panel-admin/pedido/<int:purchase_id>/estado/", views.admin_order_status, name="admin_order_status"),
    path("panel-admin/pedido/<int:purchase_id>/eliminar/", views.admin_order_delete, name="admin_order_delete"),
    path("panel-admin/usuario/<int:user_id>/", views.admin_user_detail, name="admin_user_detail"),

    # Logout robusto
    path("salir/", views.logout_view, name="logout"),
]
