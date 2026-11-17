import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Specialty(models.Model):
    name = models.CharField(max_length=140, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('display_order', 'name')

    def __str__(self):
        return self.name


class Provider(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        DISCONTINUED = 'discontinued', 'Discontinued'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True)
    website_url = models.URLField(blank=True)
    documentation_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    specialties = models.ManyToManyField(Specialty, related_name='providers', blank=True)
    support_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class ProviderOffering(models.Model):
    class OfferingType(models.TextChoices):
        PRODUCT = 'product', 'Product'
        API = 'api', 'API service'
        SOFTWARE = 'software', 'Software/service'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='offerings')
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    offering_type = models.CharField(max_length=20, choices=OfferingType.choices, default=OfferingType.PRODUCT)
    specialties = models.ManyToManyField(Specialty, related_name='offerings', blank=True)
    website_url = models.URLField(blank=True)
    reference_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('provider__name', 'name')
        constraints = [models.UniqueConstraint(fields=('provider', 'slug'), name='uniq_provider_offering_slug')]

    def clean(self):
        super().clean()
        if self.pk and self.provider_id:
            if self.specialties.exclude(pk__in=self.provider.specialties.values('pk')).exists():
                raise ValidationError({'specialties': 'An offering specialty must also be associated with its provider.'})

    def __str__(self):
        return f'{self.provider.name}: {self.name}'


class AccessRoute(models.Model):
    class RouteType(models.TextChoices):
        SUBSCRIPTION = 'subscription', 'Consumer subscription'
        API = 'api', 'Direct API usage'
        CREDITS = 'credits', 'Credit-based platform usage'
        OTHER = 'other', 'Other access route'

    class PricingMethod(models.TextChoices):
        SUBSCRIPTION = 'subscription', 'Subscription'
        PER_USE = 'per_use', 'Per use'
        PER_SECOND = 'per_second', 'Per second'
        CREDITS = 'credits', 'Credits'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offering = models.ForeignKey(ProviderOffering, on_delete=models.PROTECT, related_name='access_routes')
    name = models.CharField(max_length=160)
    route_type = models.CharField(max_length=20, choices=RouteType.choices)
    pricing_method = models.CharField(max_length=20, choices=PricingMethod.choices)
    subscription_plan = models.ForeignKey('pricing.SubscriptionPlan', on_delete=models.PROTECT, null=True, blank=True, related_name='access_routes')
    video_models = models.ManyToManyField('VideoModel', related_name='access_routes', blank=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('offering__provider__name', 'offering__name', 'name')
        constraints = [models.UniqueConstraint(fields=('offering', 'name'), name='uniq_offering_access_route')]

    def clean(self):
        super().clean()
        if self.subscription_plan_id and self.offering_id and self.subscription_plan.provider_offering_id != self.offering_id:
            raise ValidationError({'subscription_plan': 'Access-route plan must belong to its provider offering.'})
        if self.pk and self.offering_id:
            if self.video_models.exclude(provider_id=self.offering.provider_id).exists():
                raise ValidationError({'video_models': 'Access-route models must belong to the offering provider.'})
            if self.video_models.exclude(offerings=self.offering).exists():
                raise ValidationError({'video_models': 'Access-route models must be associated with the route offering.'})

    def __str__(self):
        return f'{self.offering}: {self.name}'


class VideoModel(models.Model):
    """One immutable-in-identity product version from a provider."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        RETIRED = 'retired', 'Retired'

    class Verification(models.TextChoices):
        VERIFIED = 'verified', 'Verified'
        PARTIAL = 'partially_verified', 'Partially verified'
        UNVERIFIED = 'unverified', 'Unverified'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='models')
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200)
    family = models.CharField(max_length=120, blank=True)
    version = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    documentation_url = models.URLField(blank=True)
    api_documentation_url = models.URLField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    retirement_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    verification_status = models.CharField(max_length=24, choices=Verification.choices, default=Verification.UNVERIFIED)
    workflows = models.ManyToManyField('Workflow', related_name='models', blank=True)
    offerings = models.ManyToManyField(ProviderOffering, related_name='models', blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('provider__name', 'name', 'version')
        constraints = [models.UniqueConstraint(fields=('provider', 'slug', 'version'), name='uniq_provider_model_version')]
        indexes = [models.Index(fields=('status', 'verification_status'))]

    def __str__(self):
        return f'{self.provider.name}: {self.name} ({self.version})'

    def clean(self):
        super().clean()
        if self.release_date and self.retirement_date and self.retirement_date < self.release_date:
            raise ValidationError({'retirement_date': 'Retirement date cannot precede release date.'})
        if self.pk and self.offerings.exclude(provider_id=self.provider_id).exists():
            raise ValidationError({'offerings': 'Model offerings must belong to the model provider.'})


class Workflow(models.Model):
    """Extensible controlled vocabulary for generation and production workflows."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Capability(models.Model):
    class Status(models.TextChoices):
        SUPPORTED = 'supported', 'Supported'
        NOT_SUPPORTED = 'not_supported', 'Not supported'
        UNKNOWN = 'unknown', 'Unknown'
        NOT_VERIFIED = 'not_verified', 'Not verified'

    class InputType(models.TextChoices):
        SELECT = 'select', 'Select'
        NUMBER = 'number', 'Number'
        BOOLEAN = 'boolean', 'Yes/no'
        TEXT = 'text', 'Text'
        FLAG = 'flag', 'Capability flag'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model = models.ForeignKey(VideoModel, on_delete=models.PROTECT, related_name='capabilities')
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name='model_capabilities', null=True, blank=True)
    key = models.SlugField(max_length=100, help_text='Stable key, e.g. native_audio or max_duration_seconds.')
    label = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNKNOWN)
    value = models.CharField(max_length=255, blank=True, help_text='Optional scalar/list-as-text specification; leave blank when unknown.')
    input_type = models.CharField(max_length=16, choices=InputType.choices, default=InputType.FLAG)
    allowed_values = models.JSONField(default=list, blank=True)
    minimum_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    maximum_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    constraints = models.JSONField(default=dict, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('key',)
        constraints = [models.UniqueConstraint(fields=('model', 'workflow', 'key'), name='uniq_model_workflow_capability')]
        indexes = [models.Index(fields=('key', 'status'))]

    def __str__(self):
        return f'{self.model}: {self.label} ({self.get_status_display()})'

    def clean(self):
        super().clean()
        if not isinstance(self.allowed_values, list):
            raise ValidationError({'allowed_values': 'Allowed configuration values must be a JSON list.'})
        if not isinstance(self.constraints, dict):
            raise ValidationError({'constraints': 'Configuration constraints must be a JSON object.'})
        if self.minimum_value is not None and self.maximum_value is not None and self.minimum_value > self.maximum_value:
            raise ValidationError({'maximum_value': 'Maximum value must not be less than minimum value.'})
        if self.status != self.Status.SUPPORTED and self.allowed_values:
            raise ValidationError({'allowed_values': 'Only supported capabilities may expose selectable values.'})


class Evidence(models.Model):
    class Classification(models.TextChoices):
        OFFICIAL = 'officially_documented', 'Officially documented'
        TESTED = 'independently_tested', 'Independently tested'
        DERIVED = 'calculated_or_derived', 'Calculated or derived'
        UNVERIFIED = 'unverified', 'Unverified'

    class Status(models.TextChoices):
        CURRENT = 'current', 'Current'
        SUPERSEDED = 'superseded', 'Superseded'
        UNVERIFIED = 'unverified', 'Unverified'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model = models.ForeignKey(VideoModel, on_delete=models.PROTECT, related_name='evidence')
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, related_name='evidence', null=True, blank=True)
    classification = models.CharField(max_length=30, choices=Classification.choices, default=Classification.UNVERIFIED)
    source_url = models.URLField(blank=True)
    source_title = models.CharField(max_length=240, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNVERIFIED)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-verified_at', '-created_at')

    def clean(self):
        super().clean()
        if self.capability_id and self.model_id and self.capability.model_id != self.model_id:
            raise ValidationError({'capability': 'Evidence capability must belong to the selected model.'})
        if self.classification == self.Classification.OFFICIAL and not self.source_url:
            raise ValidationError({'source_url': 'Officially documented evidence requires a source URL.'})
        if self.status == self.Status.CURRENT and self.classification != self.Classification.UNVERIFIED and not self.verified_at:
            raise ValidationError({'verified_at': 'Current verified evidence requires a verification date.'})

    def __str__(self):
        return self.source_title or f'{self.get_classification_display()} evidence for {self.model}'


class CapabilityRevision(models.Model):
    """Append-only record of the previous capability state before a change."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    capability = models.ForeignKey(Capability, on_delete=models.PROTECT, related_name='revisions')
    prior_status = models.CharField(max_length=20, choices=Capability.Status.choices)
    prior_value = models.CharField(max_length=255, blank=True)
    prior_unit = models.CharField(max_length=40, blank=True)
    prior_input_type = models.CharField(max_length=16, choices=Capability.InputType.choices, default=Capability.InputType.FLAG)
    prior_allowed_values = models.JSONField(default=list, blank=True)
    prior_minimum_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    prior_maximum_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    prior_constraints = models.JSONField(default=dict, blank=True)
    prior_is_active = models.BooleanField(default=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-recorded_at',)

    def __str__(self):
        return f'{self.capability}: prior state {self.prior_status} at {self.recorded_at}'
