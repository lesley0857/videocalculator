from django.apps import AppConfig


class VideoRegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.video_registry'
    label = 'video_registry'
    verbose_name = 'AI Video Registry'

    def ready(self):
        from apps.video_registry import signals  # noqa: F401
