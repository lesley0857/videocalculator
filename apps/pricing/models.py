import re
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.video_registry.models import AccessRoute, Provider, ProviderOffering, Specialty, VideoModel, Workflow


class PricingEvidenceFields(models.Model):
    class Verification(models.TextChoices):
        OFFICIAL = 'officially_documented', 'Officially documented'
        TESTED = 'independently_tested', 'Independently tested'
        DERIVED = 'calculated_or_derived', 'Calculated or derived'
        UNVERIFIED = 'unverified', 'Unverified'
        UNAVAILABLE = 'not_available', 'Not available'

    source_url = models.URLField(blank=True)
    evidence_description = models.CharField(max_length=500, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(max_length=30, choices=Verification.choices, default=Verification.UNVERIFIED)
    administrative_notes = models.TextField(blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.verification_status == self.Verification.OFFICIAL and not self.source_url:
            raise ValidationError({'source_url': 'Officially documented pricing requires a source URL.'})
        if self.verification_status in (self.Verification.OFFICIAL, self.Verification.TESTED) and not self.checked_at:
            raise ValidationError({'checked_at': 'Verified pricing evidence requires a checked date.'})


def validate_currency(value: str) -> None:
    if not re.fullmatch(r'[A-Z]{3}', value or ''):
        raise ValidationError('Currency must be a three-letter uppercase ISO code.')


class EffectivePricingRecord(PricingEvidenceFields):
    class FailedAttemptBilling(models.TextChoices):
        BILLABLE = 'billable', 'Failed attempts billed'
        FREE = 'free', 'Failed attempts free'
        UNKNOWN = 'unknown', 'Unknown'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    failed_attempt_billing = models.CharField(max_length=10, choices=FailedAttemptBilling.choices, default=FailedAttemptBilling.UNKNOWN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ('-effective_from',)
        constraints = [models.CheckConstraint(
            condition=Q(effective_until__isnull=True) | Q(effective_until__gt=F('effective_from')),
            name='%(app_label)s_%(class)s_valid_period',
        )]

    def clean(self):
        super().clean()
        validate_currency(self.currency)
        if self.effective_until and self.effective_until <= self.effective_from:
            raise ValidationError({'effective_until': 'Effective end must be later than effective start.'})

    def validate_immutable(self, fields):
        if not self.pk:
            return
        previous = type(self).objects.filter(pk=self.pk).values(*fields).first()
        if previous and any(previous[field] != getattr(self, field) for field in fields):
            raise ValidationError('Price and scope fields are immutable. Create a new effective-dated record instead.')

    def is_effective(self, at=None) -> bool:
        at = at or timezone.now()
        return self.is_active and self.effective_from <= at and (self.effective_until is None or at < self.effective_until)


class ModelPricing(EffectivePricingRecord):
    class Method(models.TextChoices):
        FIXED_GENERATION = 'fixed_generation', 'Fixed per generation'
        PER_SECOND = 'per_second', 'Per generated second'
        CREDITS_GENERATION = 'credits_per_generation', 'Credits per generation'
        CREDITS_SECOND = 'credits_per_second', 'Credits per second'

    class Unit(models.TextChoices):
        GENERATION = 'generation', 'Generation'
        SECOND = 'second', 'Second'

    video_model = models.ForeignKey(VideoModel, on_delete=models.PROTECT, related_name='pricing_records')
    workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, null=True, blank=True, related_name='model_pricing_records')
    access_route = models.ForeignKey(AccessRoute, on_delete=models.PROTECT, null=True, blank=True, related_name='model_pricing_records')
    method = models.CharField(max_length=30, choices=Method.choices)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    unit = models.CharField(max_length=20, choices=Unit.choices)
    minimum_billable_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    billing_increment_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    configuration = models.JSONField(default=dict, blank=True, help_text='Exact configuration scope, e.g. resolution/audio mode. Empty means configuration-independent.')

    class Meta(EffectivePricingRecord.Meta):
        constraints = EffectivePricingRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(rate__gte=0), name='pricing_rate_nonnegative'),
            models.UniqueConstraint(fields=('video_model', 'workflow', 'method', 'configuration', 'effective_from'), condition=Q(access_route__isnull=True), name='unique_model_price_config_start'),
            models.UniqueConstraint(fields=('video_model', 'workflow', 'access_route', 'method', 'configuration', 'effective_from'), condition=Q(access_route__isnull=False), name='unique_model_price_route_start'),
        ]
        indexes = [models.Index(fields=('video_model', 'workflow', 'method', 'is_active'))]

    def clean(self):
        super().clean()
        if not isinstance(self.configuration, dict):
            raise ValidationError({'configuration': 'Configuration scope must be a JSON object.'})
        if any(not isinstance(key, str) or not isinstance(value, (str, int, bool, Decimal)) for key, value in self.configuration.items()):
            raise ValidationError({'configuration': 'Configuration keys must be strings and values must be scalar.'})
        credits = self.method in (self.Method.CREDITS_GENERATION, self.Method.CREDITS_SECOND)
        expected_unit = self.Unit.SECOND if self.method in (self.Method.PER_SECOND, self.Method.CREDITS_SECOND) else self.Unit.GENERATION
        if self.method and self.unit != expected_unit:
            raise ValidationError({'unit': f'{self.get_method_display()} pricing requires unit {expected_unit}.'})
        if self.rate is not None and self.rate <= 0:
            raise ValidationError({'rate': 'Pricing rates must be greater than zero.'})
        if credits and self.currency != 'CRD':
            raise ValidationError({'currency': 'Credit rates use the CRD denomination, not a fiat currency.'})
        if not credits and self.currency == 'CRD':
            raise ValidationError({'currency': 'Monetary rates require a fiat currency.'})
        for field in ('minimum_billable_seconds', 'billing_increment_seconds'):
            value = getattr(self, field)
            if value is not None and value <= 0:
                raise ValidationError({field: 'Billing durations must be greater than zero.'})
        if self.method in (self.Method.PER_SECOND, self.Method.CREDITS_SECOND) and self.billing_increment_seconds is None:
            # A missing increment means exact per-second billing.
            pass
        if self.access_route_id and self.video_model_id:
            if self.access_route.offering.provider_id != self.video_model.provider_id:
                raise ValidationError({'access_route': 'Access route must belong to the model provider.'})
            if not self.video_model.offerings.filter(pk=self.access_route.offering_id).exists() or not self.access_route.video_models.filter(pk=self.video_model_id).exists():
                raise ValidationError({'access_route': 'Access route must be explicitly associated with this model version.'})
        self._validate_no_overlap(('video_model', 'workflow', 'access_route', 'method', 'configuration'))
        self.validate_immutable(('video_model_id', 'workflow_id', 'access_route_id', 'method', 'configuration', 'rate', 'unit', 'currency', 'effective_from', 'minimum_billable_seconds', 'billing_increment_seconds'))

    def _validate_no_overlap(self, scope_fields):
        if not self.is_active:
            return
        qs = type(self).objects.filter(is_active=True)
        for field in scope_fields:
            if field in ('video_model', 'workflow', 'provider'):
                qs = qs.filter(**{f'{field}_id': getattr(self, f'{field}_id')})
            else:
                qs = qs.filter(**{field: getattr(self, field)})
        qs = qs.exclude(pk=self.pk)
        if self.effective_until is not None:
            qs = qs.filter(effective_from__lt=self.effective_until)
        qs = qs.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=self.effective_from))
        if qs.exists():
            raise ValidationError('Active pricing periods for the same model, workflow, and method cannot overlap.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        scope = f' / {self.configuration}' if self.configuration else ''
        return f'{self.video_model} / {self.get_method_display()}{scope} / {self.rate} {self.currency}'


class ProductionTool(models.Model):
    """A reusable non-model production tool, such as ChatGPT or CapCut."""

    class Kind(models.TextChoices):
        SUBSCRIPTION = 'subscription', 'Subscription tool'
        METERED_SERVICE = 'metered_service', 'Metered production service'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='production_tools')
    offering = models.ForeignKey(ProviderOffering, on_delete=models.PROTECT, null=True, blank=True, related_name='production_tools')
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    activities = models.JSONField(default=list, help_text='Activities covered by this tool, e.g. concept, script, prompts, visual_assets.')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('provider__name', 'name')

    def clean(self):
        super().clean()
        allowed = {'concept', 'script', 'prompts', 'visual_assets', 'voice_narration', 'voice_replacement', 'editing', 'finishing'}
        if not isinstance(self.activities, list) or any(item not in allowed for item in self.activities):
            raise ValidationError({'activities': 'Choose one or more supported production activities.'})
        if self.offering_id and self.provider_id and self.offering.provider_id != self.provider_id:
            raise ValidationError({'offering': 'Production tool offering must belong to its provider.'})

    def __str__(self):
        return f'{self.provider.name}: {self.name}'


class ProductionToolPricing(PricingEvidenceFields):
    class CostType(models.TextChoices):
        SUBSCRIPTION = 'subscription', 'Monthly subscription'
        USAGE = 'usage', 'Usage charge'
        FIXED = 'fixed', 'Fixed project charge'

    class Method(models.TextChoices):
        MONTHLY_SUBSCRIPTION = 'monthly_subscription', 'Monthly subscription'
        PER_UNIT = 'per_unit', 'Per unit'
        PER_1000_UNITS = 'per_1000_units', 'Per 1,000 units'
        FIXED_PROJECT = 'fixed_project', 'Fixed per project'

    class Allocation(models.TextChoices):
        MONTHLY_PROJECTS = 'monthly_projects', 'Monthly subscription / expected projects'
        MONTHLY_HOURS = 'monthly_hours', 'Monthly subscription / expected production hours'
        MANUAL = 'manual', 'Manual project allocation'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool = models.ForeignKey(ProductionTool, on_delete=models.PROTECT, related_name='pricing_records')
    subscription_plan = models.ForeignKey('SubscriptionPlan', on_delete=models.PROTECT, null=True, blank=True, related_name='production_tool_prices')
    name = models.CharField(max_length=160, help_text='Plan or pricing option name.')
    cost_type = models.CharField(max_length=16, choices=CostType.choices)
    method = models.CharField(max_length=24, choices=Method.choices)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    unit = models.CharField(max_length=40, blank=True)
    included_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    allocation_method = models.CharField(max_length=20, choices=Allocation.choices, blank=True)
    expected_monthly_projects = models.PositiveIntegerField(null=True, blank=True)
    expected_monthly_hours = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('tool__provider__name', 'tool__name', 'name', '-effective_from')
        indexes = [models.Index(fields=('tool', 'cost_type', 'is_active', 'effective_from'))]
        constraints = [models.CheckConstraint(condition=Q(rate__gte=0), name='production_tool_rate_nonnegative'),
                       models.CheckConstraint(condition=Q(effective_until__isnull=True) | Q(effective_until__gt=F('effective_from')), name='production_tool_price_valid_period')]

    def clean(self):
        super().clean()
        validate_currency(self.currency)
        if self.subscription_plan_id:
            if self.cost_type != self.CostType.SUBSCRIPTION:
                raise ValidationError({'subscription_plan': 'Only subscription pricing can reference a canonical subscription plan.'})
            if self.subscription_plan.provider_id != self.tool.provider_id or (self.tool.offering_id and self.subscription_plan.provider_offering_id != self.tool.offering_id):
                raise ValidationError({'subscription_plan': 'Canonical plan must match the tool provider and offering.'})
        if self.cost_type == self.CostType.SUBSCRIPTION:
            if self.method != self.Method.MONTHLY_SUBSCRIPTION:
                raise ValidationError({'method': 'Subscription pricing must use monthly subscription allocation.'})
            if self.allocation_method not in self.Allocation.values:
                raise ValidationError({'allocation_method': 'Choose a subscription allocation method.'})
            if self.allocation_method == self.Allocation.MONTHLY_PROJECTS and not self.expected_monthly_projects:
                raise ValidationError({'expected_monthly_projects': 'Expected monthly projects must be greater than zero.'})
            if self.allocation_method == self.Allocation.MONTHLY_HOURS and (not self.expected_monthly_hours or self.expected_monthly_hours <= 0):
                raise ValidationError({'expected_monthly_hours': 'Expected monthly hours must be greater than zero.'})
        elif self.method == self.Method.MONTHLY_SUBSCRIPTION:
            raise ValidationError({'method': 'Only subscription pricing can use monthly allocation.'})
        if self.method in (self.Method.PER_UNIT, self.Method.PER_1000_UNITS) and not self.unit:
            raise ValidationError({'unit': 'Metered prices require a unit.'})
        if self.included_quantity is not None and self.included_quantity < 0:
            raise ValidationError({'included_quantity': 'Included quantity cannot be negative.'})
        if self.effective_until and self.effective_until <= self.effective_from:
            raise ValidationError({'effective_until': 'Effective end must be later than effective start.'})
        if self.verification_status == self.Verification.OFFICIAL and not self.source_url:
            raise ValidationError({'source_url': 'Officially documented pricing requires a source URL.'})
        if self.verification_status in (self.Verification.OFFICIAL, self.Verification.TESTED) and not self.checked_at:
            raise ValidationError({'checked_at': 'Verified pricing evidence requires a checked date.'})
        if self.is_active:
            records = type(self).objects.filter(tool=self.tool, name=self.name, cost_type=self.cost_type, method=self.method, is_active=True).exclude(pk=self.pk)
            if self.effective_until:
                records = records.filter(effective_from__lt=self.effective_until)
            if records.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=self.effective_from)).exists():
                raise ValidationError('Active pricing periods for this tool option cannot overlap.')
        immutable = ('tool_id', 'subscription_plan_id', 'name', 'cost_type', 'method', 'rate', 'currency', 'unit', 'included_quantity', 'effective_from')
        if self.pk:
            prior = type(self).objects.filter(pk=self.pk).values(*immutable).first()
            if prior and any(prior[field] != getattr(self, field) for field in immutable):
                raise ValidationError('Pricing identity and rate are immutable. Create a new effective-dated record.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.tool} / {self.name}: {self.rate} {self.currency}/{self.unit or self.get_method_display()}'


class ProductionOverheadPricing(PricingEvidenceFields):
    class Category(models.TextChoices):
        ELECTRICITY = 'electricity', 'Electricity'
        INTERNET = 'internet_data', 'Internet and data'
        LABOUR = 'labour', 'Labour and professional time'
        EQUIPMENT = 'equipment', 'Equipment and hardware usage/depreciation'
        SOFTWARE = 'software_tools', 'Software subscriptions and production tools'
        STOCK = 'stock_assets', 'Stock assets, graphics, fonts and licensed materials'
        MUSIC = 'music_licensing', 'Music and sound-effect licensing'
        STORAGE = 'storage_delivery', 'Storage, file transfer and delivery'
        PAYMENT = 'payment_fees', 'Payment processing and transaction fees'
        FX = 'fx_charges', 'Foreign exchange and conversion charges'
        TAX = 'taxes_duties', 'Taxes and applicable duties'
        OTHER = 'other', 'Other production expenses'

    class Method(models.TextChoices):
        FIXED_PROJECT = 'fixed_project', 'Fixed amount per project'
        PER_HOUR = 'per_hour', 'Cost per production/labour hour'
        PER_CLIP = 'per_clip', 'Cost per generated clip'
        PER_VIDEO_MINUTE = 'per_video_minute', 'Cost per final video minute'
        PER_UNIT = 'per_unit', 'Cost per unit'
        MONTHLY_PROJECTS = 'monthly_projects', 'Monthly cost / expected projects'
        MONTHLY_HOURS = 'monthly_hours', 'Monthly cost / expected production hours'
        PERCENTAGE = 'percentage', 'Percentage of direct production cost'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=24, choices=Category.choices)
    name = models.CharField(max_length=160)
    method = models.CharField(max_length=24, choices=Method.choices)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    unit = models.CharField(max_length=40, blank=True)
    expected_monthly_projects = models.PositiveIntegerField(null=True, blank=True)
    expected_monthly_hours = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('category', 'name', '-effective_from')
        indexes = [models.Index(fields=('category', 'is_active', 'effective_from'))]
        constraints = [models.CheckConstraint(condition=Q(rate__gte=0), name='production_overhead_rate_nonnegative'),
                       models.CheckConstraint(condition=Q(effective_until__isnull=True) | Q(effective_until__gt=F('effective_from')), name='production_overhead_valid_period')]

    def clean(self):
        super().clean()
        validate_currency(self.currency)
        if self.method == self.Method.PER_UNIT and not self.unit:
            raise ValidationError({'unit': 'Per-unit overhead rates require a unit.'})
        if self.method == self.Method.MONTHLY_PROJECTS and not self.expected_monthly_projects:
            raise ValidationError({'expected_monthly_projects': 'Expected monthly projects must be greater than zero.'})
        if self.method == self.Method.MONTHLY_HOURS and (not self.expected_monthly_hours or self.expected_monthly_hours <= 0):
            raise ValidationError({'expected_monthly_hours': 'Expected monthly hours must be greater than zero.'})
        if self.method == self.Method.PERCENTAGE and self.rate > 100:
            raise ValidationError({'rate': 'Percentage overhead cannot exceed 100.'})
        if self.effective_until and self.effective_until <= self.effective_from:
            raise ValidationError({'effective_until': 'Effective end must be later than effective start.'})
        if self.verification_status == self.Verification.OFFICIAL and not self.source_url:
            raise ValidationError({'source_url': 'Officially documented pricing requires a source URL.'})
        if self.verification_status in (self.Verification.OFFICIAL, self.Verification.TESTED) and not self.checked_at:
            raise ValidationError({'checked_at': 'Verified pricing evidence requires a checked date.'})
        if self.is_active:
            records = type(self).objects.filter(category=self.category, name=self.name, method=self.method, is_active=True).exclude(pk=self.pk)
            if self.effective_until:
                records = records.filter(effective_from__lt=self.effective_until)
            if records.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=self.effective_from)).exists():
                raise ValidationError('Active pricing periods for this overhead option cannot overlap.')
        immutable = ('category', 'name', 'method', 'rate', 'currency', 'unit', 'effective_from')
        if self.pk:
            prior = type(self).objects.filter(pk=self.pk).values(*immutable).first()
            if prior and any(prior[field] != getattr(self, field) for field in immutable):
                raise ValidationError('Overhead pricing is immutable. Create a new effective-dated record.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_category_display()} / {self.name}: {self.rate} {self.currency}/{self.unit or self.get_method_display()}'


class CreditPackage(EffectivePricingRecord):
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='credit_packages')
    name = models.CharField(max_length=120)
    credit_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    price = models.DecimalField(max_digits=18, decimal_places=8)

    class Meta(EffectivePricingRecord.Meta):
        constraints = EffectivePricingRecord.Meta.constraints + [models.CheckConstraint(condition=Q(credit_quantity__gt=0) & Q(price__gt=0), name='credit_package_positive_values')]
        indexes = [models.Index(fields=('provider', 'is_active', 'effective_from'))]

    def clean(self):
        super().clean()
        if self.currency == 'CRD':
            raise ValidationError({'currency': 'Credit package purchase price must use a fiat currency.'})
        if self.credit_quantity is not None and self.credit_quantity <= 0:
            raise ValidationError({'credit_quantity': 'Credit quantity must be positive.'})
        if self.price is not None and self.price <= 0:
            raise ValidationError({'price': 'Package price must be positive.'})
        self._validate_no_overlap(('provider', 'name'))
        self.validate_immutable(('provider_id', 'name', 'credit_quantity', 'price', 'currency', 'effective_from'))

    def _validate_no_overlap(self, scope_fields):
        if not self.is_active:
            return
        qs = type(self).objects.filter(is_active=True).exclude(pk=self.pk)
        for field in scope_fields:
            qs = qs.filter(**{f'{field}_id': getattr(self, f'{field}_id')}) if field in ('provider',) else qs.filter(**{field: getattr(self, field)})
        if self.effective_until is not None:
            qs = qs.filter(effective_from__lt=self.effective_until)
        qs = qs.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=self.effective_from))
        if qs.exists():
            raise ValidationError('Active credit package periods with the same provider and name cannot overlap.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.provider}: {self.name} ({self.credit_quantity} credits)'


class SubscriptionPlan(EffectivePricingRecord):
    class Period(models.TextChoices):
        MONTHLY = 'monthly', 'Monthly'
        ANNUAL = 'annual', 'Annual'
        CUSTOM = 'custom', 'Custom'

    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, related_name='subscription_plans')
    provider_offering = models.ForeignKey(ProviderOffering, on_delete=models.PROTECT, null=True, blank=True, related_name='subscription_plans')
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)
    period = models.CharField(max_length=12, choices=Period.choices)
    period_days = models.PositiveSmallIntegerField(null=True, blank=True)
    subscription_price = models.DecimalField(max_digits=18, decimal_places=8)
    included_credits = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    additional_credit_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    additional_credit_price = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    included_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    included_unit = models.CharField(max_length=40, blank=True)
    specialties = models.ManyToManyField(Specialty, related_name='subscription_plans', blank=True)
    allocation_method = models.CharField(max_length=20, choices=ProductionToolPricing.Allocation.choices, blank=True)
    expected_monthly_projects = models.PositiveIntegerField(null=True, blank=True)
    expected_monthly_hours = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta(EffectivePricingRecord.Meta):
        constraints = EffectivePricingRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(subscription_price__gte=0) & (Q(included_credits__isnull=True) | Q(included_credits__gt=0)), name='subscription_plan_valid_amounts'),
            models.CheckConstraint(condition=(Q(additional_credit_quantity__isnull=True) & Q(additional_credit_price__isnull=True)) | (Q(additional_credit_quantity__isnull=False) & Q(additional_credit_price__isnull=False)), name='subscription_addons_both_or_neither'),
        ]
        indexes = [models.Index(fields=('provider', 'is_active', 'effective_from')),
                   models.UniqueConstraint(fields=('provider_offering', 'slug'), condition=~Q(slug=''), name='uniq_offering_plan_slug')]

    def clean(self):
        super().clean()
        if self.provider_offering_id and self.provider_offering.provider_id != self.provider_id:
            raise ValidationError({'provider_offering': 'Subscription plan offering must belong to the selected provider.'})
        if self.pk and self.provider_offering_id and self.specialties.exclude(pk__in=self.provider_offering.specialties.values('pk')).exists():
            raise ValidationError({'specialties': 'Plan specialties must be supported by its provider offering.'})
        if self.included_quantity is not None and not self.included_unit:
            raise ValidationError({'included_unit': 'An included usage allowance requires a unit.'})
        if self.allocation_method == ProductionToolPricing.Allocation.MONTHLY_PROJECTS and not self.expected_monthly_projects:
            raise ValidationError({'expected_monthly_projects': 'Expected monthly projects must be greater than zero.'})
        if self.allocation_method == ProductionToolPricing.Allocation.MONTHLY_HOURS and (not self.expected_monthly_hours or self.expected_monthly_hours <= 0):
            raise ValidationError({'expected_monthly_hours': 'Expected monthly hours must be greater than zero.'})
        if self.currency == 'CRD':
            raise ValidationError({'currency': 'Subscription price must use a fiat currency.'})
        if self.period == self.Period.CUSTOM and not self.period_days:
            raise ValidationError({'period_days': 'Custom periods require a positive duration in days.'})
        if bool(self.additional_credit_quantity) != bool(self.additional_credit_price):
            raise ValidationError('Additional credit quantity and price must be supplied together.')
        if self.subscription_price is not None and self.subscription_price < 0:
            raise ValidationError({'subscription_price': 'Subscription price cannot be negative.'})
        self._validate_plan_overlap()
        self.validate_immutable(('provider_id', 'name', 'period', 'period_days', 'subscription_price', 'included_credits', 'additional_credit_quantity', 'additional_credit_price', 'currency', 'effective_from'))
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values('provider_offering_id', 'slug').first()
            if previous and previous['provider_offering_id'] and previous['provider_offering_id'] != self.provider_offering_id:
                raise ValidationError({'provider_offering': 'A linked subscription plan cannot be reassigned to another offering.'})
            if previous and previous['slug'] and previous['slug'] != self.slug:
                raise ValidationError({'slug': 'A plan identifier is immutable once assigned.'})

    def _validate_plan_overlap(self):
        if not self.is_active:
            return
        qs = type(self).objects.filter(provider=self.provider, name=self.name, is_active=True).exclude(pk=self.pk)
        if self.effective_until is not None:
            qs = qs.filter(effective_from__lt=self.effective_until)
        if qs.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=self.effective_from)).exists():
            raise ValidationError('Active subscription plan periods with the same provider and name cannot overlap.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.provider}: {self.name}'


class OperationPricing(EffectivePricingRecord):
    class Method(models.TextChoices):
        FIXED = 'fixed', 'Fixed per operation'
        PER_UNIT = 'per_unit', 'Per unit'
        PER_SECOND = 'per_second', 'Per second'

    operation_key = models.SlugField(max_length=80)
    label = models.CharField(max_length=120)
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, null=True, blank=True, related_name='operation_pricing')
    method = models.CharField(max_length=20, choices=Method.choices)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    unit = models.CharField(max_length=30, default='operation')

    class Meta(EffectivePricingRecord.Meta):
        constraints = EffectivePricingRecord.Meta.constraints + [models.CheckConstraint(condition=Q(rate__gt=0), name='operation_rate_positive'), models.UniqueConstraint(fields=('operation_key', 'provider', 'effective_from'), name='unique_operation_pricing_start')]
        indexes = [models.Index(fields=('operation_key', 'provider', 'is_active'))]

    def clean(self):
        super().clean()
        if self.rate is not None and self.rate <= 0:
            raise ValidationError({'rate': 'Operation rates must be positive.'})
        if self.currency == 'CRD':
            raise ValidationError({'currency': 'Operation prices must be monetary. Use model credit pricing for credit-denominated generation.'})
        if self.is_active:
            qs = type(self).objects.filter(operation_key=self.operation_key, provider=self.provider, is_active=True).exclude(pk=self.pk)
            if self.effective_until is not None:
                qs = qs.filter(effective_from__lt=self.effective_until)
            if qs.filter(Q(effective_until__isnull=True) | Q(effective_until__gt=self.effective_from)).exists():
                raise ValidationError('Active operation pricing periods for this operation/provider cannot overlap.')
        self.validate_immutable(('operation_key', 'provider_id', 'label', 'method', 'rate', 'unit', 'currency', 'effective_from'))

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.label}: {self.rate} {self.currency}/{self.unit}'


class ExchangeRate(models.Model):
    class Verification(models.TextChoices):
        OFFICIAL = 'officially_documented', 'Officially documented'
        TESTED = 'independently_tested', 'Independently tested'
        DERIVED = 'calculated_or_derived', 'Calculated or derived'
        UNVERIFIED = 'unverified', 'Unverified'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_currency = models.CharField(max_length=3, validators=[validate_currency])
    quote_currency = models.CharField(max_length=3, validators=[validate_currency])
    rate = models.DecimalField(max_digits=20, decimal_places=10, help_text='Quote-currency units per one base-currency unit.')
    effective_at = models.DateTimeField()
    source = models.CharField(max_length=300, blank=True)
    verification_status = models.CharField(max_length=30, choices=Verification.choices, default=Verification.UNVERIFIED)
    administrative_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-effective_at',)
        constraints = [models.CheckConstraint(condition=Q(rate__gt=0), name='exchange_rate_positive'), models.UniqueConstraint(fields=('base_currency', 'quote_currency', 'effective_at'), name='unique_exchange_rate_timestamp')]
        indexes = [models.Index(fields=('base_currency', 'quote_currency', '-effective_at'))]

    def clean(self):
        super().clean()
        validate_currency(self.base_currency)
        validate_currency(self.quote_currency)
        if self.base_currency == self.quote_currency:
            raise ValidationError('Base and quote currencies must differ.')
        if 'CRD' in (self.base_currency, self.quote_currency):
            raise ValidationError('Exchange-rate records apply to fiat currencies, not CRD credit units.')
        if self.rate is not None and self.rate <= 0:
            raise ValidationError({'rate': 'Exchange rate must be positive.'})
        if self.verification_status in (self.Verification.OFFICIAL, self.Verification.TESTED) and not self.source:
            raise ValidationError({'source': 'Verified exchange rates require a source reference.'})
        self._validate_immutable()

    def _validate_immutable(self):
        if not self.pk:
            return
        fields = ('base_currency', 'quote_currency', 'rate', 'effective_at')
        previous = type(self).objects.filter(pk=self.pk).values(*fields).first()
        if previous and any(previous[field] != getattr(self, field) for field in fields):
            raise ValidationError('Exchange-rate identity and value are immutable; add a new effective-dated rate.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'1 {self.base_currency} = {self.rate} {self.quote_currency} ({self.effective_at:%Y-%m-%d})'


class CostEstimate(models.Model):
    """Append-only calculation snapshots; null ownership is reserved for legacy rows."""
    class CalculatorType(models.TextChoices):
        TALKING_FLYER = 'talking_flyer', 'Talking Flyer'
        VIDEO_GENERATION = 'video_generation', 'Video Generation'
        GENERAL = 'general', 'General calculator'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey('accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='cost_estimates')
    project = models.ForeignKey('workspace.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='estimates')
    calculator_type = models.CharField(max_length=24, choices=CalculatorType.choices, null=True, blank=True)
    inputs = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        constraints = [models.CheckConstraint(
            condition=(Q(owner__isnull=True, project__isnull=True) | Q(owner__isnull=False, project__isnull=False)),
            name='estimate_owner_and_project_both_null_or_present',
        )]
        indexes = [models.Index(fields=('owner', 'project', '-created_at'))]

    def clean(self):
        super().clean()
        if bool(self.owner_id) != bool(self.project_id):
            raise ValidationError('A saved estimate must have both an owner and a project.')
        if self.owner_id and self.project_id and self.project.owner_id != self.owner_id:
            raise ValidationError({'project': 'The selected project does not belong to this estimate owner.'})

    def save(self, *args, **kwargs):
        if self._state.adding and (self.owner_id is None or self.project_id is None):
            raise ValidationError('New saved estimates must belong to an owner and project.')
        if self._state.adding and self.calculator_type is None:
            self.calculator_type = self.CalculatorType.GENERAL
        if not self._state.adding:
            previous = type(self).objects.filter(pk=self.pk).values('owner_id', 'project_id', 'calculator_type', 'inputs', 'result').first()
            if previous and any(previous[field] != getattr(self, field) for field in ('owner_id', 'project_id', 'calculator_type', 'inputs', 'result')):
                raise ValidationError('Saved estimates are immutable. Create a new estimate instead.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Saved estimates cannot be deleted.')

    def __str__(self):
        return f'Cost estimate {self.id} ({self.created_at:%Y-%m-%d %H:%M})'
