from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.workspace.models import Project

from apps.pricing.models import CostEstimate, CreditPackage, ExchangeRate, ModelPricing, OperationPricing, SubscriptionPlan
from apps.video_registry.models import Provider, VideoModel, Workflow


class PricingModelTests(TestCase):
    def setUp(self):
        self.provider = Provider.objects.create(name='Pricing Synthetic Lab', slug='pricing-synthetic-lab')
        self.workflow, _ = Workflow.objects.get_or_create(name='Text to video', slug='text-to-video')
        self.model_v1 = VideoModel.objects.create(provider=self.provider, name='Synthetic Model', slug='synthetic-model', version='1')
        self.model_v2 = VideoModel.objects.create(provider=self.provider, name='Synthetic Model', slug='synthetic-model', version='2')
        self.model_v1.workflows.add(self.workflow)
        self.now = timezone.now()

    def price(self, **kwargs):
        values = {'video_model': self.model_v1, 'workflow': self.workflow,
                  'method': ModelPricing.Method.FIXED_GENERATION, 'rate': Decimal('0.50'),
                  'unit': ModelPricing.Unit.GENERATION, 'currency': 'USD',
                  'effective_from': self.now - timedelta(days=1), 'verification_status': 'unverified'}
        values.update(kwargs)
        return ModelPricing.objects.create(**values)

    def test_model_prices_reference_exact_version_and_workflow(self):
        rate = self.price()
        self.assertEqual(rate.video_model_id, self.model_v1.pk)
        self.assertEqual(rate.workflow_id, self.workflow.pk)
        self.assertNotEqual(rate.video_model_id, self.model_v2.pk)

    def test_duplicate_active_overlapping_period_is_rejected(self):
        self.price()
        with self.assertRaises(ValidationError):
            self.price(rate=Decimal('0.80'))

    def test_database_unique_and_date_constraints_are_enforced(self):
        first = self.price()
        duplicate = ModelPricing(video_model=self.model_v1, workflow=self.workflow, method=first.method,
            rate=Decimal('0.80'), unit=first.unit, currency='USD', effective_from=first.effective_from)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModelPricing.objects.bulk_create([duplicate])
        invalid_period = ModelPricing(video_model=self.model_v2, workflow=self.workflow, method=first.method,
            rate=Decimal('0.80'), unit=first.unit, currency='USD', effective_from=self.now,
            effective_until=self.now - timedelta(seconds=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModelPricing.objects.bulk_create([invalid_period])

    def test_new_effective_price_preserves_historical_amount(self):
        first = self.price(effective_from=self.now - timedelta(days=4), effective_until=self.now - timedelta(days=1))
        second = self.price(effective_from=self.now - timedelta(days=1), rate=Decimal('0.75'))
        first.refresh_from_db()
        self.assertEqual(first.rate, Decimal('0.50000000'))
        self.assertEqual(second.rate, Decimal('0.75000000'))
        first.rate = Decimal('0.90')
        with self.assertRaises(ValidationError):
            first.save()

    def test_price_method_currency_and_unit_are_validated(self):
        with self.assertRaises(ValidationError):
            self.price(currency='US')
        with self.assertRaises(ValidationError):
            self.price(method=ModelPricing.Method.PER_SECOND, unit=ModelPricing.Unit.GENERATION)
        with self.assertRaises(ValidationError):
            self.price(method=ModelPricing.Method.CREDITS_GENERATION, currency='USD')

    def test_credit_subscription_exchange_and_operation_records(self):
        package = CreditPackage.objects.create(provider=self.provider, name='Synthetic 100 Credits', credit_quantity=100,
            price=Decimal('2'), currency='USD', effective_from=self.now - timedelta(days=1))
        plan = SubscriptionPlan.objects.create(provider=self.provider, name='Synthetic Monthly', period='monthly',
            subscription_price=Decimal('20'), included_credits=1000, currency='USD', effective_from=self.now - timedelta(days=1))
        fx = ExchangeRate.objects.create(base_currency='USD', quote_currency='NGN', rate=1500,
            effective_at=self.now - timedelta(hours=1), verification_status=ExchangeRate.Verification.TESTED, source='Synthetic test rate')
        operation = OperationPricing.objects.create(operation_key='tts', label='Synthetic TTS', method='per_unit',
            rate=Decimal('0.01'), unit='character', currency='USD', effective_from=self.now - timedelta(days=1))
        self.assertEqual(package.provider, plan.provider)
        self.assertEqual((fx.base_currency, fx.quote_currency), ('USD', 'NGN'))
        self.assertEqual(operation.operation_key, 'tts')

    def test_exchange_rate_and_plan_validation(self):
        with self.assertRaises(ValidationError):
            ExchangeRate.objects.create(base_currency='USD', quote_currency='USD', rate=1, effective_at=self.now)
        with self.assertRaises(ValidationError):
            SubscriptionPlan.objects.create(provider=self.provider, name='Broken', period='custom', period_days=None,
                subscription_price=Decimal('5'), included_credits=10, currency='USD', effective_from=self.now)


class PricingApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='pricing-owner@example.test', password='safe-password')
        self.project = Project.objects.create(owner=self.user, name='Synthetic estimate project')
        self.client.force_login(self.user)
        self.provider = Provider.objects.create(name='API Synthetic Lab', slug='api-synthetic-lab')
        self.workflow, _ = Workflow.objects.get_or_create(name='Text to video', slug='text-to-video')
        self.model = VideoModel.objects.create(provider=self.provider, name='API Model', slug='api-model', version='1')
        self.model.workflows.add(self.workflow)
        self.rate = ModelPricing.objects.create(video_model=self.model, workflow=self.workflow,
            method=ModelPricing.Method.FIXED_GENERATION, rate=Decimal('0.50'), unit='generation', currency='USD',
            effective_from=timezone.now() - timedelta(hours=1), verification_status='independently_tested',
            evidence_description='Synthetic fixture only.', checked_at=timezone.now())
        self.fx = ExchangeRate.objects.create(base_currency='USD', quote_currency='NGN', rate=1500,
            effective_at=timezone.now() - timedelta(minutes=10), verification_status='independently_tested', source='Synthetic test rate')

    def payload(self, **kwargs):
        return {'components': [{'video_model_id': str(self.model.pk), 'workflow_slug': self.workflow.slug,
                                'duration_seconds': '5', 'generation_requests': 2, 'clip_count': 2,
                                'pricing_record_id': str(self.rate.pk)}], 'output_currency': 'USD',
                'project_id': str(self.project.pk), **kwargs}

    def test_pricing_listing_and_model_version_detail(self):
        response = self.client.get(reverse('pricing:pricing-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['version'], '1')
        detail = self.client.get(reverse('pricing:model-pricing-detail', args=[self.model.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['results'][0]['workflow'], 'text-to-video')
        self.assertEqual(self.client.get(reverse('pricing:model-pricing-detail', args=['00000000-0000-0000-0000-000000000000'])).status_code, 404)

    def test_estimate_api_uses_authoritative_prices_and_persists_snapshot(self):
        response = self.client.post(reverse('pricing:estimate'), data=self.payload(markup_percentage='30'), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['commercial']['base_production_cost'], '1.00')
        self.assertEqual(response.json()['commercial']['suggested_selling_price'], '1.30')
        snapshot = CostEstimate.objects.get(pk=response.json()['estimate_id'])
        detail = self.client.get(reverse('pricing:estimate-detail', args=[snapshot.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['result_snapshot']['commercial']['gross_profit'], '0.30')
        self.assertEqual(detail.json()['calculator_type'], 'general')

    def test_saved_estimate_keeps_resolved_price_snapshot_after_price_deactivation(self):
        response = self.client.post(reverse('pricing:estimate'), data=self.payload(markup_percentage='30'), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        snapshot = CostEstimate.objects.get(pk=response.json()['estimate_id'])
        original_inputs, original_result = snapshot.inputs.copy(), snapshot.result.copy()
        self.rate.is_active = False
        self.rate.save()
        detail = self.client.get(reverse('pricing:estimate-detail', args=[snapshot.pk])).json()
        self.assertEqual(detail['input_snapshot'], original_inputs)
        self.assertEqual(detail['result_snapshot'], original_result)
        self.assertIn('resolved_snapshot', detail['input_snapshot'])

    def test_public_estimate_is_calculated_without_persisting_or_accepting_project_ownership(self):
        self.client.logout()
        public_payload = self.payload(markup_percentage='30')
        public_payload.pop('project_id')
        before = CostEstimate.objects.count()
        response = self.client.post(reverse('pricing:estimate'), data=public_payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['commercial']['total_estimated_production_cost'], '1.00')
        self.assertEqual(response.json()['commercial']['suggested_selling_price'], '1.30')
        self.assertNotIn('estimate_id', response.json())
        self.assertEqual(CostEstimate.objects.count(), before)
        forged = self.payload()
        self.assertEqual(self.client.post(reverse('pricing:estimate'), data=forged, content_type='application/json').status_code, 401)

    def test_customer_facing_directory_and_calculator_pages_render(self):
        products = self.client.get(reverse('products:list'), HTTP_ACCEPT='text/html')
        self.assertEqual(products.status_code, 200)
        self.assertContains(products, 'Plan AI-assisted video production')
        calculators = self.client.get(reverse('calculators:index'))
        self.assertEqual(calculators.status_code, 200)
        self.assertContains(calculators, 'Narration timing')
        self.assertContains(calculators, 'Clip planner')
        cost_page = self.client.get(reverse('pricing:test-interface'))
        self.assertEqual(cost_page.status_code, 200)
        self.assertContains(cost_page, 'name="csrfmiddlewaretoken"')
        self.assertContains(cost_page, 'id="provider"')
        narration = self.client.get(reverse('calculators:talking-flyer-narration-test'))
        self.assertContains(narration, 'continueToClipPlanner')
        clip_planner = self.client.get(reverse('calculators:talking-flyer-clip-planner-test'))
        self.assertContains(clip_planner, 'costEstimateCta')

    def test_estimate_currency_conversion_and_price_tampering_rejection(self):
        converted = self.client.post(reverse('pricing:estimate'), data=self.payload(output_currency='NGN'), content_type='application/json')
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(converted.json()['commercial']['total_estimated_production_cost'], '1500.00')
        tampered = self.payload()
        tampered['components'][0]['rate'] = '0.0001'
        response = self.client.post(reverse('pricing:estimate'), data=tampered, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_missing_model_price_and_missing_operation_are_incomplete(self):
        other = VideoModel.objects.create(provider=self.provider, name='Unpriced', slug='unpriced', version='1')
        other.workflows.add(self.workflow)
        payload = {'components': [{'video_model_id': str(other.pk), 'workflow_slug': self.workflow.slug, 'duration_seconds': '5'}],
                   'operations': [{'operation_key': 'lip-sync', 'quantity': '1'}], 'output_currency': 'USD',
                   'project_id': str(self.project.pk)}
        response = self.client.post(reverse('pricing:estimate'), data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 422, response.content.decode())
        self.assertEqual(response.json()['status'], 'incomplete')
        self.assertIsNone(response.json()['commercial']['suggested_selling_price'])
        self.assertEqual(len(response.json()['missing_information']), 2)

    def test_invalid_workflow_invalid_model_and_invalid_request_are_rejected(self):
        bad_workflow = self.payload()
        bad_workflow['components'][0]['workflow_slug'] = 'not-a-workflow'
        self.assertEqual(self.client.post(reverse('pricing:estimate'), data=bad_workflow, content_type='application/json').status_code, 400)
        bad_model = self.payload()
        bad_model['components'][0]['video_model_id'] = '00000000-0000-0000-0000-000000000000'
        self.assertEqual(self.client.post(reverse('pricing:estimate'), data=bad_model, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(reverse('pricing:estimate'), data='{broken', content_type='application/json').status_code, 400)

    def test_exchange_list_read_only_and_development_interface(self):
        response = self.client.get(reverse('pricing:exchange-rates'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['rate'], '1500.0000000000')
        self.assertEqual(self.client.post(reverse('pricing:pricing-list')).status_code, 405)
        interface = self.client.get(reverse('pricing:test-interface'))
        self.assertEqual(interface.status_code, 200)
        self.assertContains(interface, 'AI video production cost calculator')
        plans = self.client.get(reverse('pricing:subscription-plans'))
        self.assertEqual(plans.status_code, 200)

    def test_estimate_post_requires_csrf_outside_test_client_shortcut(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse('pricing:estimate'), data=self.payload(), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_admin_registers_pricing_management_models(self):
        for model in (ModelPricing, CreditPackage, SubscriptionPlan, OperationPricing, ExchangeRate, CostEstimate):
            self.assertTrue(admin.site.is_registered(model))
        user = get_user_model().objects.create_superuser(email='pricing-admin@example.test', password='temporary-password')
        self.client.force_login(user)
        for route in ('admin:pricing_modelpricing_changelist', 'admin:pricing_creditpackage_changelist',
                      'admin:pricing_subscriptionplan_changelist', 'admin:pricing_operationpricing_changelist',
                      'admin:pricing_exchangerate_changelist', 'admin:pricing_costestimate_changelist'):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

