import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ARCHIVED = 'archived', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='video_projects')
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at', '-created_at')
        constraints = [
            models.UniqueConstraint(fields=('owner', 'name'), name='unique_workspace_project_name_per_owner'),
            models.CheckConstraint(
                condition=(models.Q(status='active', archived_at__isnull=True) |
                           models.Q(status='archived', archived_at__isnull=False)),
                name='workspace_project_archive_timestamp_matches_status',
            ),
        ]
        indexes = [models.Index(fields=('owner', 'status', '-updated_at'))]

    def clean(self):
        super().clean()
        self.name = (self.name or '').strip()
        if self.status == self.Status.ACTIVE and self.archived_at is not None:
            raise ValidationError({'archived_at': 'Active projects cannot have an archive timestamp.'})
        if self.status == self.Status.ARCHIVED and self.archived_at is None:
            raise ValidationError({'archived_at': 'Archived projects must record when they were archived.'})
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values('owner_id').first()
            if old and old['owner_id'] != self.owner_id:
                raise ValidationError({'owner': 'Project ownership cannot be changed.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def archive(self):
        self.status = self.Status.ARCHIVED
        self.archived_at = timezone.now()
        self.save(update_fields=('status', 'archived_at', 'updated_at'))

    def restore(self):
        self.status = self.Status.ACTIVE
        self.archived_at = None
        self.save(update_fields=('status', 'archived_at', 'updated_at'))

    def __str__(self):
        return f'{self.name} ({self.owner})'
