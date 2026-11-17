from django.contrib import admin

from apps.pricing.models import (CostEstimate, CreditPackage, ExchangeRate, ModelPricing, OperationPricing,
                                 ProductionOverheadPricing, ProductionTool, ProductionToolPricing, SubscriptionPlan)


@admin.register(ModelPricing)
class ModelPricingAdmin(admin.ModelAdmin):
    list_display = ('video_model', 'workflow', 'access_route', 'method', 'configuration', 'rate', 'currency', 'effective_from', 'effective_until', 'is_active', 'verification_status')
    list_filter = ('method', 'currency', 'is_active', 'verification_status', 'workflow', 'access_route__route_type', 'video_model__provider')
    search_fields = ('video_model__name', 'video_model__version', 'video_model__provider__name', 'workflow__name', 'source_url')
    date_hierarchy = 'effective_from'
    readonly_fields = ('id',)
    fieldsets = (
        ('Scope and rate', {'fields': ('video_model', 'workflow', 'access_route', 'configuration', 'method', 'rate', 'unit', 'currency', 'minimum_billable_seconds', 'billing_increment_seconds', 'failed_attempt_billing')}),
        ('Effective period', {'fields': ('effective_from', 'effective_until', 'is_active')}),
        ('Evidence', {'fields': ('source_url', 'evidence_description', 'checked_at', 'verification_status', 'administrative_notes')}),
        ('Audit', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_readonly_fields(self, request, obj=None):
        immutable = ('video_model', 'workflow', 'access_route', 'configuration', 'method', 'rate', 'unit', 'currency', 'effective_from', 'minimum_billable_seconds', 'billing_increment_seconds')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())


@admin.register(ProductionTool)
class ProductionToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'offering', 'kind', 'is_active')
    list_filter = ('provider', 'offering', 'kind', 'is_active')
    search_fields = ('name', 'slug', 'provider__name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(ProductionToolPricing)
class ProductionToolPricingAdmin(admin.ModelAdmin):
    list_display = ('tool', 'name', 'subscription_plan', 'cost_type', 'method', 'rate', 'currency', 'effective_from', 'is_active', 'verification_status')
    list_filter = ('tool__provider', 'cost_type', 'method', 'currency', 'is_active', 'verification_status')
    search_fields = ('tool__name', 'name', 'subscription_plan__name', 'source_url')
    date_hierarchy = 'effective_from'
    readonly_fields = ('id',)

    def get_readonly_fields(self, request, obj=None):
        immutable = ('tool', 'name', 'cost_type', 'method', 'rate', 'currency', 'unit', 'included_quantity', 'effective_from')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())


@admin.register(ProductionOverheadPricing)
class ProductionOverheadPricingAdmin(admin.ModelAdmin):
    list_display = ('category', 'name', 'method', 'rate', 'currency', 'unit', 'effective_from', 'is_active', 'verification_status')
    list_filter = ('category', 'method', 'currency', 'is_active', 'verification_status')
    search_fields = ('name', 'source_url')
    date_hierarchy = 'effective_from'
    readonly_fields = ('id',)

    def get_readonly_fields(self, request, obj=None):
        immutable = ('category', 'name', 'method', 'rate', 'currency', 'unit', 'effective_from')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())


@admin.register(CreditPackage)
class CreditPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'credit_quantity', 'price', 'currency', 'effective_from', 'is_active', 'verification_status')
    list_filter = ('provider', 'currency', 'is_active', 'verification_status')
    search_fields = ('name', 'provider__name', 'source_url')
    date_hierarchy = 'effective_from'
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_readonly_fields(self, request, obj=None):
        immutable = ('provider', 'name', 'credit_quantity', 'price', 'currency', 'effective_from')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'provider_offering', 'period', 'subscription_price', 'currency', 'included_credits', 'effective_from', 'is_active', 'verification_status')
    list_filter = ('provider', 'provider_offering', 'period', 'currency', 'is_active', 'verification_status', 'specialties')
    search_fields = ('name', 'slug', 'provider__name', 'provider_offering__name', 'source_url')
    date_hierarchy = 'effective_from'
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_readonly_fields(self, request, obj=None):
        immutable = ('provider', 'name', 'period', 'period_days', 'subscription_price', 'included_credits', 'additional_credit_quantity', 'additional_credit_price', 'currency', 'effective_from')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.full_clean()


@admin.register(OperationPricing)
class OperationPricingAdmin(admin.ModelAdmin):
    list_display = ('operation_key', 'label', 'provider', 'method', 'rate', 'currency', 'effective_from', 'is_active', 'verification_status')
    list_filter = ('operation_key', 'provider', 'method', 'currency', 'is_active', 'verification_status')
    search_fields = ('operation_key', 'label', 'provider__name', 'source_url')
    date_hierarchy = 'effective_from'
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_readonly_fields(self, request, obj=None):
        immutable = ('operation_key', 'provider', 'label', 'method', 'rate', 'unit', 'currency', 'effective_from')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('base_currency', 'quote_currency', 'rate', 'effective_at', 'verification_status', 'source')
    list_filter = ('base_currency', 'quote_currency', 'verification_status')
    search_fields = ('base_currency', 'quote_currency', 'source')
    date_hierarchy = 'effective_at'
    readonly_fields = ('id', 'created_at')
    fields = ('base_currency', 'quote_currency', 'rate', 'effective_at', 'source', 'verification_status', 'administrative_notes', 'id', 'created_at')

    def get_readonly_fields(self, request, obj=None):
        immutable = ('base_currency', 'quote_currency', 'rate', 'effective_at')
        return super().get_readonly_fields(request, obj) + (immutable if obj else ())


@admin.register(CostEstimate)
class CostEstimateAdmin(admin.ModelAdmin):
    list_display = ('id', 'calculator_type', 'owner', 'project', 'created_at')
    date_hierarchy = 'created_at'
    readonly_fields = ('id', 'owner', 'project', 'inputs', 'result', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
