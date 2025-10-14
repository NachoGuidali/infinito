from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.db import transaction
from ..models import (
    Purchase, PurchaseItem, Bundle, Stage, Entitlement, Enrollment
)

def create_checkout(user, items):
    """
    Crea una Purchase 'pending' con sus PurchaseItems.
    items = [
      {"type": "stage", "id": <stage_id>, "price_ars": Decimal|None},
      {"type": "bundle", "id": <bundle_id>, "price_ars": Decimal|None},
    ]
    """
    with transaction.atomic():
        p = Purchase.objects.create(user=user, status='pending', total_ars=Decimal('0'))
        total = Decimal('0')

        for it in items:
            if it['type'] == 'stage':
                stage = get_object_or_404(Stage, id=it['id'])
                price = Decimal(str(it.get('price_ars') or stage.price_ars))
                PurchaseItem.objects.create(
                    purchase=p,
                    type='stage',
                    stage=stage,
                    price_ars=price
                )
                total += price

            elif it['type'] == 'bundle':
                bundle = get_object_or_404(Bundle, id=it['id'])
                price = Decimal(str(it.get('price_ars') or bundle.price_ars))
                PurchaseItem.objects.create(
                    purchase=p,
                    type='bundle',
                    bundle=bundle,
                    price_ars=price
                )
                total += price

            else:
                raise ValueError("Tipo de ítem inválido (usa 'stage' o 'bundle').")

        p.total_ars = total
        p.save()

    return p


def mark_paid_and_grant(purchase: Purchase, external_ref: str | None = None):
    """
    Marca la compra como pagada y otorga:
      - Enrollment por cada curso involucrado
      - Entitlements por cada etapa comprada (directa) o incluida en el bundle
    No saltea el prerrequisito: eso lo valida services.access.can_view_stage
    """
    if purchase.status == 'paid':
        return  # idempotente

    purchase.status = 'paid'
    if external_ref:
        purchase.external_ref = external_ref
    purchase.save()

    # 1) Enrollment por curso
    course_ids = set()
    for item in purchase.items.all():
        if item.type == 'stage' and item.stage:
            course_ids.add(item.stage.course_id)
        elif item.type == 'bundle' and item.bundle:
            course_ids.add(item.bundle.course_id)

    for cid in course_ids:
        Enrollment.objects.get_or_create(user=purchase.user, course_id=cid)

    # 2) Entitlements por etapa
    for item in purchase.items.all():
        if item.type == 'stage' and item.stage:
            Entitlement.objects.get_or_create(
                user=purchase.user,
                stage=item.stage,
                defaults={'source': 'stage'}
            )

        elif item.type == 'bundle' and item.bundle:
            for st in item.bundle.stages.all():
                Entitlement.objects.get_or_create(
                    user=purchase.user,
                    stage=st,
                    defaults={'source': 'bundle'}
                )
