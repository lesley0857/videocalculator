from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.video_registry.models import Capability, CapabilityRevision


@receiver(pre_save, sender=Capability)
def preserve_capability_revision(sender, instance, **kwargs):
    if not instance.pk:
        return
    fields = ('status', 'value', 'unit', 'input_type', 'allowed_values', 'minimum_value',
              'maximum_value', 'constraints', 'is_active')
    previous = sender.objects.filter(pk=instance.pk).values(*fields).first()
    if previous and any(previous[field] != getattr(instance, field) for field in fields):
        CapabilityRevision.objects.create(
            capability_id=instance.pk,
            prior_status=previous['status'],
            prior_value=previous['value'],
            prior_unit=previous['unit'],
            prior_input_type=previous['input_type'],
            prior_allowed_values=previous['allowed_values'],
            prior_minimum_value=previous['minimum_value'],
            prior_maximum_value=previous['maximum_value'],
            prior_constraints=previous['constraints'],
            prior_is_active=previous['is_active'],
        )
