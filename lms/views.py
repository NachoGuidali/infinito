from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import logout, get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib import messages

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.urls import reverse
from django.db.models import Q, Count, Max
import hashlib

from .models import (
    Course, Stage, Lesson, Quiz, QuizAttempt, StageProgress,
    Bundle, Entitlement, Purchase, PurchaseItem
)
from .forms import QuizForm
from .services.access import can_view_stage
from .services.payments import create_checkout, mark_paid_and_grant

from django.contrib.auth.models import User


# =======================
# LOGOUT robusto
# =======================
def logout_view(request):
    """Cierra sesión y envía al home público."""
    logout(request)
    return redirect("lms:home")


# =======================
# HOME
# =======================
def home(request):
    """
    - Si NO está logueado: lms/home_public.html
    - Si está logueado: lms/home_logged.html (carouseles)
    """
    if not request.user.is_authenticated:
        return render(request, "lms/home_public.html")

    courses = Course.objects.prefetch_related("stages").all()
    trainings = courses  # TODO: separar cuando haya "capacitaciones" reales
    return render(request, "lms/home_logged.html", {
        "courses": courses,
        "trainings": trainings,
    })


# =======================
# CATÁLOGO Y CURSO
# =======================
def catalog(request):
    courses = Course.objects.prefetch_related('stages').all()
    return render(request, 'lms/catalog.html', {'courses': courses})


def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)

    stages_qs = course.stages.all().prefetch_related("lessons").order_by("order")

    # Etapas que el usuario ya tiene (por compra)
    stage_entitled_ids = set()
    course_owned = False
    if request.user.is_authenticated:
        stage_ids = set(stages_qs.values_list("id", flat=True))
        got = Entitlement.objects.filter(
            user=request.user, stage_id__in=stage_ids
        ).values_list("stage_id", flat=True)
        stage_entitled_ids = set(got)
        if stage_ids and stage_ids.issubset(stage_entitled_ids):
            course_owned = True  # tiene TODAS las etapas

    bundles = list(course.bundles.all()[:1])

    return render(request, 'lms/course_detail.html', {
        'course': course,
        'bundles': bundles,
        'stage_entitled_ids': stage_entitled_ids,
        'course_owned': course_owned,
    })


# =======================
# ETAPA Y QUIZ
# =======================
@login_required
def stage_detail(request, course_slug, stage_slug):
    stage = get_object_or_404(Stage, course__slug=course_slug, slug=stage_slug)
    ok, reason = can_view_stage(request.user, stage)
    if not ok:
        return render(request, 'lms/stage_detail.html', {'stage': stage, 'blocked_reason': reason})
    lessons = stage.lessons.all()
    return render(request, 'lms/stage_detail.html', {'stage': stage, 'lessons': lessons})


@login_required
def quiz_take(request, course_slug, stage_slug):
    stage = get_object_or_404(Stage, course__slug=course_slug, slug=stage_slug)
    quiz = get_object_or_404(Quiz, stage=stage)

    ok, reason = can_view_stage(request.user, stage)
    if not ok:
        return HttpResponseForbidden(reason)

    if request.method == 'POST':
        form = QuizForm(request.POST, quiz=quiz)
        if form.is_valid():
            total = quiz.questions.count()
            correct = 0
            for q in quiz.questions.all():
                choice_id = int(form.cleaned_data[f"q_{q.id}"])
                if q.choices.filter(id=choice_id, is_correct=True).exists():
                    correct += 1
            score = round((correct / max(total, 1)) * 100)
            passed = score >= quiz.passing_score

            QuizAttempt.objects.create(user=request.user, quiz=quiz, score=score, passed=passed)

            sp, _ = StageProgress.objects.get_or_create(user=request.user, stage=stage)
            sp.score = max(sp.score, score)
            if passed and not sp.passed:
                sp.passed = True
                sp.passed_at = timezone.now()
            sp.save()

            return redirect('lms:stage_detail', course_slug=course_slug, stage_slug=stage_slug)
    else:
        form = QuizForm(quiz=quiz)

    return render(request, 'lms/quiz_take.html', {'stage': stage, 'quiz': quiz, 'form': form})


# =======================
# CHECKOUT / WEBHOOK
# =======================
@login_required
def checkout_view(request):
    """?stage_id=<id> o ?bundle_id=<id> crea Purchase y muestra el total."""
    items = []
    stage_id = request.GET.get('stage_id')
    bundle_id = request.GET.get('bundle_id')

    if stage_id:
        items.append({"type": "stage", "id": int(stage_id), "price_ars": None})
    if bundle_id:
        items.append({"type": "bundle", "id": int(bundle_id), "price_ars": None})

    if not items:
        return HttpResponse("Seleccioná una etapa o el curso completo.")

    purchase = create_checkout(request.user, items)
    return render(request, 'lms/checkout.html', {'purchase': purchase})


@csrf_exempt
def webhook_paid(request):
    """Webhook de pago (demo). En prod: Mercado Pago POSTea acá y marcamos 'paid'."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    purchase_id = request.POST.get('purchase_id')
    external_ref = request.POST.get('external_ref', '')

    try:
        purchase = Purchase.objects.get(id=purchase_id)
    except Purchase.DoesNotExist:
        return HttpResponse(status=404)

    mark_paid_and_grant(purchase, external_ref)
    return HttpResponse('ok')


# ==============================
# PERFIL (resumen + compras)
# ==============================
def _gravatar_url(email: str, size: int = 200) -> str:
    mail = (email or "").strip().lower().encode("utf-8")
    md5 = hashlib.md5(mail).hexdigest()
    return f"https://www.gravatar.com/avatar/{md5}?s={size}&d=identicon"


@login_required
def profile(request):
    user = request.user

    # POST: actualizar datos básicos
    if request.method == "POST":
        user.first_name = request.POST.get("first_name", "").strip()
        user.last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip()
        if email:
            user.email = email
        user.save()
        return redirect("lms:profile")

    # Etapas habilitadas por compra
    entitled_stage_ids = set(
        Entitlement.objects.filter(user=user).values_list("stage_id", flat=True)
    )

    # Cursos de esas etapas
    course_ids = (
        Stage.objects.filter(id__in=entitled_stage_ids)
        .values_list("course_id", flat=True)
        .distinct()
    )

    my_courses = (
        Course.objects.filter(id__in=course_ids)
        .prefetch_related("stages", "stages__lessons")
        .order_by("title")
    )

    courses_data = []
    total_inscriptos = 0
    total_finalizados = 0

    failed_quizzes = QuizAttempt.objects.filter(user=user, passed=False).count()

    for course in my_courses:
        total_inscriptos += 1

        stages = list(course.stages.all().order_by("order"))
        stage_ids = [s.id for s in stages]

        passed_by_id = set(
            StageProgress.objects.filter(
                user=user, stage_id__in=stage_ids, passed=True
            ).values_list("stage_id", flat=True)
        )

        stages_info = []
        next_stage = None
        for s in stages:
            entitled = s.id in entitled_stage_ids
            passed = s.id in passed_by_id
            url = reverse("lms:stage_detail", args=[course.slug, s.slug]) if entitled else None
            stages_info.append({
                "obj": s,
                "title": s.title,
                "order": s.order,
                "entitled": entitled,
                "passed": passed,
                "url": url,
            })
            if (not passed) and entitled and (next_stage is None):
                next_stage = s

        total = len(stages)
        passed_count = sum(1 for s in stages if s.id in passed_by_id)
        status = "aprobado" if (total > 0 and passed_count == total) else (
            "en_progreso" if passed_count > 0 else "nuevo"
        )
        if status == "aprobado":
            total_finalizados += 1

        next_url = reverse("lms:stage_detail", args=[course.slug, next_stage.slug]) if next_stage else None

        courses_data.append({
            "course": course,
            "total": total,
            "passed": passed_count,
            "status": status,
            "next_stage_url": next_url,
            "stages_info": stages_info,
        })

    total_en_progreso = sum(1 for d in courses_data if d["status"] in ("en_progreso", "nuevo"))

    purchases = Purchase.objects.filter(user=user).order_by("-created_at").prefetch_related(
        "items", "items__stage", "items__bundle"
    )

    stats = {
        "inscriptos": total_inscriptos,
        "en_progreso": total_en_progreso,
        "finalizados": total_finalizados,
        "desaprobados": failed_quizzes,
    }

    return render(request, "lms/profile.html", {
        "avatar_url": _gravatar_url(user.email, 200),
        "courses_data": courses_data,
        "purchases": purchases,
        "stats": stats,
    })


# ==================================
# PANEL ADMIN LIGERO + ACCIONES
# ==================================
def _is_staff(u):
    return u.is_authenticated and u.is_staff


@user_passes_test(_is_staff)
def admin_panel(request):
    """
    Panel administrativo:
      - Lista y filtra pedidos (usuario, estado, curso).
      - Cambia estado de pedidos (aprobado/pendiente/cancelado).
      - Elimina pedidos.
      - Muestra alumnos que completaron un curso (todas las etapas aprobadas).
    """
    UserModel = get_user_model()

    # ----- Filtros -----
    user_id = request.GET.get("user")
    status = request.GET.get("status")            # "pending", "paid", "cancelled" o vacío
    course_id = request.GET.get("course")         # id del curso (str) o vacío
    q = request.GET.get("q", "").strip()          # búsqueda por usuario/email

    users_qs = UserModel.objects.all().order_by("username")
    courses_qs = Course.objects.all().order_by("title")

    # ----- Pedidos (Purchase) con filtros -----
    purchases_qs = (
        Purchase.objects.all()
        .select_related("user")
        .prefetch_related("items", "items__stage", "items__stage__course", "items__bundle", "items__bundle__course")
        .order_by("-created_at")
    )

    if user_id:
        purchases_qs = purchases_qs.filter(user_id=user_id)

    if status:
        purchases_qs = purchases_qs.filter(status=status)

    if course_id:
        try:
            cid = int(course_id)
            purchases_qs = purchases_qs.filter(
                Q(items__stage__course_id=cid) |
                Q(items__bundle__course_id=cid)
            )
        except ValueError:
            cid = None
        purchases_qs = purchases_qs.distinct()

    if q:
        purchases_qs = purchases_qs.filter(
            Q(user__username__icontains=q) | Q(user__email__icontains=q)
        )

    purchases = list(purchases_qs[:300])  # límite de seguridad

    # ----- Alumnos que completaron curso (todas las etapas aprobadas) -----
    completed = []  # lista de dicts: {"user": <User>, "course": <Course>, "completed_at": <datetime>}
    courses_for_completed = courses_qs
    if course_id:
        try:
            cid = int(course_id)
            courses_for_completed = courses_for_completed.filter(id=cid)
        except ValueError:
            pass

    for c in courses_for_completed:
        total_stages = c.stages.count()
        if total_stages == 0:
            continue

        # Agrupamos progreso por usuario en este curso
        rows = (
            StageProgress.objects.filter(passed=True, stage__course=c)
            .values("user_id")
            .annotate(cnt=Count("stage", distinct=True), last=Max("passed_at"))
            .filter(cnt=total_stages)
        )
        user_ids = [r["user_id"] for r in rows]
        users_map = {u.id: u for u in UserModel.objects.filter(id__in=user_ids)}
        for r in rows:
            completed.append({
                "user": users_map.get(r["user_id"]),
                "course": c,
                "completed_at": r["last"],
            })

    # Más nuevo primero
    completed.sort(key=lambda x: (x["completed_at"] or timezone.datetime.min), reverse=True)

    # ----- Resumen -----
    total_users = StageProgress.objects.values("user").distinct().count()
    total_courses = Course.objects.count()
    total_stages = Stage.objects.count()
    total_lessons = Lesson.objects.count()

    return render(request, "lms/admin_panel.html", {
        "users": users_qs,
        "courses": courses_qs,
        "selected_user_id": int(user_id) if user_id else None,
        "selected_status": status or "",
        "selected_course_id": int(course_id) if course_id else None,
        "search_q": q,
        "purchases": purchases,
        "completed": completed,  # alumnos que terminaron curso
        "stage_progress": [],    # (dejado por compatibilidad si ya lo usabas)
        "summary": {
            "users": total_users,
            "courses": total_courses,
            "stages": total_stages,
            "lessons": total_lessons,
        },
    })


@user_passes_test(_is_staff)
@require_POST
def admin_update_purchase_status(request, purchase_id: int):
    """
    Cambia el estado de un Purchase:
      - "paid": marcar pagado (equivalente a recepción manual de transferencia) -> otorga accesos
      - "pending": volver a pendiente
      - "cancelled": cancelado
    * Mercado Pago se marca vía webhook; esto es para transferencias/manual.
    """
    new_status = request.POST.get("status")
    try:
        purchase = Purchase.objects.get(id=purchase_id)
    except Purchase.DoesNotExist:
        return HttpResponse(status=404)

    if new_status not in ("pending", "paid", "cancelled"):
        return HttpResponse("Estado inválido", status=400)

    # Si lo pasamos a "paid" manualmente, otorgamos acceso (como hace el webhook)
    if new_status == "paid" and purchase.status != "paid":
        mark_paid_and_grant(purchase, external_ref="MANUAL")

    # Nota: no revocamos accesos si se pasa a pending/cancelled (defínelo si lo necesitás)
    purchase.status = new_status
    purchase.save(update_fields=["status"])
    messages.success(request, f"Pedido #{purchase.id} actualizado a '{new_status}'.")
    return redirect(request.META.get("HTTP_REFERER", "lms:admin_panel"))


@user_passes_test(_is_staff)
@require_POST
def admin_delete_purchase(request, purchase_id: int):
    """
    Elimina un Purchase y sus items.
    * No revoca Entitlements ya otorgados (podemos agregarlo si lo pedís).
    """
    try:
        purchase = Purchase.objects.get(id=purchase_id)
    except Purchase.DoesNotExist:
        return HttpResponse(status=404)

    pid = purchase.id
    purchase.delete()
    messages.success(request, f"Pedido #{pid} eliminado.")
    return redirect(request.META.get("HTTP_REFERER", "lms:admin_panel"))


# ---- ALIAS retrocompatibles con nombres que ya usabas en urls.py ----
@user_passes_test(_is_staff)
@require_POST
def admin_order_status(request, purchase_id: int):
    return admin_update_purchase_status(request, purchase_id)


@user_passes_test(_is_staff)
@require_POST
def admin_order_delete(request, purchase_id: int):
    return admin_delete_purchase(request, purchase_id)


# ==============================
# DETALLE POR USUARIO (panel)
# ==============================
@user_passes_test(_is_staff)
def admin_user_detail(request, user_id: int):
    UserModel = get_user_model()
    the_user = get_object_or_404(UserModel, pk=user_id)

    purchases = (
        Purchase.objects.filter(user=the_user)
        .prefetch_related("items", "items__stage", "items__bundle")
        .order_by("-created_at")
    )

    progresses = (
        StageProgress.objects.filter(user=the_user)
        .select_related("stage", "stage__course")
        .order_by("-updated_at", "-passed_at")
    )

    return render(request, "lms/admin_user_detail.html", {
        "the_user": the_user,
        "purchases": purchases,
        "progresses": progresses,
    })
