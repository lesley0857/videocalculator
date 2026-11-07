"""
Product catalog models.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class Product(models.Model):
    """
    Product model representing platform offerings (e.g., Talking Flyer Calculator, AI Video Calculator).
    """
    name = models.CharField(_('name'), max_length=255)
    slug = models.SlugField(_('slug'), unique=True)
    description = models.TextField(_('description'), blank=True)
    is_active = models.BooleanField(_('is active'), default=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('product')
        verbose_name_plural = _('products')
        ordering = ['name']

    def __str__(self):
        return self.name

