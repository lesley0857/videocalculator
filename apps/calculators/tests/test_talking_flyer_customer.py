import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.pricing.models import CostEstimate, ModelPricing
from apps.video_registry.models import AccessRoute, Provider, ProviderOffering, Specialty, VideoModel, Workflow
from apps.workspace.models import Project


class TalkingFlyerCustomerFlowTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.provider = Provider.objects.create(name='Customer Flow Studio', slug='customer-flow-studio')
        self.specialty = Specialty.objects.get(slug='video-generation-animation')
        self.provider.specialties.add(self.specialty)
        self.offering = ProviderOffering.objects.create(provider=self.provider, name='Studio API', slug='studio-api', offering_type='api')
        self.offering.specialties.add(self.specialty)
        self.workflow = Workflow.objects.get(slug='text-to-video')
        self.model = VideoModel.objects.create(provider=self.provider, name='Studio Video', slug='studio-video', version='v1')
        self.model.workflows.add(self.workflow)
        self.model.offerings.add(self.offering)
        self.route = AccessRoute.objects.create(offering=self.offering, name='Direct API', route_type='api', pricing_method='per_second')
        self.route.video_models.add(self.model)
        self.price = ModelPricing.objects.create(video_model=self.model, workflow=self.workflow, access_route=self.route,
            method=ModelPricing.Method.FIXED_GENERATION, rate=Decimal('0.50'), unit=ModelPricing.Unit.GENERATION,
            currency='USD', effective_from=now - timedelta(days=1),
            verification_status=ModelPricing.Verification.TESTED, evidence_description='Synthetic fixture', checked_at=now)
        self.user = get_user_model().objects.create_user(email='talking-flyer-owner@example.test', password='safe-password')

    def customer_payload(self):
        return {'calculator_type': 'talking_flyer', 'output_currency': 'USD',
            'talking_flyer': {'schema_version': 1, 'script': 'Hello there, buy now.', 'word_count': 4,
                'narration_wpm': 120, 'narration_duration_seconds': '2.00',
                'clip_plan': {'schema_version': 1, 'clip_count': 1,
                    'clips': [{'sequence': 1, 'word_count': 4, 'text': 'Hello there, buy now.',
                        'duration_seconds': '5.00', 'reserved_duration_seconds': '0.00', 'usable_duration_seconds': '5.00'}],
                    'total_planned_generated_duration_seconds': '5.00', 'total_reserved_duration_seconds': '0.00',
                    'total_usable_duration_seconds': '5.00'}},
            'components': [{'video_model_id': str(self.model.pk), 'workflow_slug': self.workflow.slug,
                'specialty_slug': self.specialty.slug, 'provider_id': str(self.provider.pk),
                'offering_id': str(self.offering.pk), 'access_route_id': str(self.route.pk),
                'pricing_record_id': str(self.price.pk), 'clip_sequences': [1],
                'duration_seconds': '5', 'generation_requests': 1, 'clip_count': 1}],
            'operations': [], 'tools': [], 'overheads': [],
            'production': {'desired_final_duration_seconds': '5.00', 'expected_usable_duration_seconds': '5.00'}}

    def test_customer_entry_points_and_specialty_flow_render(self):
        for url in (reverse('calculators:talking-flyer'), reverse('products:list'), reverse('calculators:index'), reverse('home')):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        page = self.client.get(reverse('calculators:talking-flyer'))
        self.assertContains(page, 'Calculate narration timing')
        self.assertContains(page, 'Plan clips and script segments')
        self.assertContains(page, 'tf-clip-assignments')
        self.assertContains(page, 'video-generation-animation')

    def test_existing_narration_and_clip_apis_drive_the_customer_plan(self):
        narration = self.client.post(reverse('calculators:narration-calculate-api'),
            data=json.dumps({'text': 'Hello there, buy now.', 'wpm': 120}), content_type='application/json')
        self.assertEqual(narration.status_code, 200)
        self.assertEqual(narration.json()['data']['word_count'], 4)
        self.assertEqual(narration.json()['data']['wpm'], 120)
        invalid_speed = self.client.post(reverse('calculators:narration-calculate-api'),
            data=json.dumps({'text': 'Words here', 'wpm': 59}), content_type='application/json')
        self.assertEqual(invalid_speed.status_code, 400)
        plan = self.client.post(reverse('calculators:clip-planner-calculate-api'), data=json.dumps({
            'narration': 'Hello there, buy now.', 'wpm': 120,
            'clip_options': [{'duration_seconds': 5, 'reserved_seconds': 0}],
            'segmentation': {'sentence_boundary_preference': True, 'sentence_boundary_tolerance': .2},
        }), content_type='application/json')
        self.assertEqual(plan.status_code, 200, plan.content.decode())
        self.assertTrue(plan.json()['validation']['is_valid'])
        self.assertEqual(plan.json()['clips'][0]['narration_text'], 'Hello there, buy now.')

    def test_unexpected_narration_exception_is_logged_but_response_stays_generic(self):
        with patch(
            'apps.calculators.views.calculate_narration',
            side_effect=RuntimeError('synthetic private failure'),
        ):
            with self.assertLogs('apps.calculators.views', level='ERROR') as captured:
                response = self.client.post(
                    reverse('calculators:narration-calculate-api'),
                    {'text': 'Hello', 'wpm': 120},
                )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()['error'],
            'An unexpected error occurred during calculation.',
        )
        self.assertIn('Traceback (most recent call last):', captured.output[0])
        self.assertIn('synthetic private failure', captured.output[0])

    def test_unexpected_clip_planning_exception_is_logged_but_response_stays_generic(self):
        with patch(
            'apps.calculators.views.UniversalClipPlanningEngine.calculate',
            side_effect=RuntimeError('synthetic private failure'),
        ):
            with self.assertLogs('apps.calculators.views', level='ERROR') as captured:
                response = self.client.post(
                    reverse('calculators:clip-planner-calculate-api'),
                    data=json.dumps({'narration': 'Hello', 'wpm': 120}),
                    content_type='application/json',
                )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()['error'],
            'An unexpected error occurred during clip planning.',
        )
        self.assertIn('Traceback (most recent call last):', captured.output[0])
        self.assertIn('synthetic private failure', captured.output[0])

    def test_specialty_selection_estimate_and_anonymous_save_return_flow(self):
        response = self.client.get(reverse('video_registry:specialty-providers', args=[self.specialty.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['slug'], self.provider.slug)
        model_list = self.client.get(reverse('video_registry:model-list'), {'specialty': self.specialty.slug,
            'provider': self.provider.slug, 'offering': str(self.offering.pk), 'access_route': str(self.route.pk)})
        self.assertEqual(model_list.status_code, 200)
        self.assertEqual(model_list.json()['results'][0]['version'], 'v1')

        payload = self.customer_payload()
        estimate_response = self.client.post(reverse('pricing:estimate'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(estimate_response.status_code, 200, estimate_response.content.decode())
        self.assertNotIn('estimate_id', estimate_response.json())
        self.assertEqual(CostEstimate.objects.count(), 0)

        prepare = self.client.post(reverse('calculators:talking-flyer-save-prepare'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(prepare.status_code, 200, prepare.content.decode())
        self.assertEqual(prepare.json()['next_url'], '/accounts/login/?next=/calculators/talking-flyer/save/')
        self.assertTrue(self.client.login(email=self.user.email, password='safe-password'))
        save_page = self.client.get(reverse('calculators:talking-flyer-save'))
        self.assertContains(save_page, 'Choose a project')
        saved = self.client.post(reverse('calculators:talking-flyer-save'), {'project_name':'Flyer launch project'})
        self.assertEqual(saved.status_code, 302)
        estimate = CostEstimate.objects.get()
        self.assertEqual(estimate.calculator_type, CostEstimate.CalculatorType.TALKING_FLYER)
        self.assertEqual(estimate.project.name, 'Flyer launch project')
        self.assertEqual(estimate.inputs['talking_flyer']['clip_plan']['clips'][0]['duration_seconds'], '5.00')
        self.assertEqual(estimate.result['commercial']['total_estimated_production_cost'], '0.50')
        self.assertIn('resolved_snapshot', estimate.inputs)
        self.assertEqual(self.client.get(saved.url).status_code, 200)
        self.assertContains(self.client.get(saved.url), 'Talking Flyer')

    def test_save_rejects_foreign_projects_and_missing_customer_inputs(self):
        payload = self.customer_payload()
        invalid = payload | {'calculator_type':'video_generation'}
        self.assertEqual(self.client.post(reverse('calculators:talking-flyer-save-prepare'),
            data=json.dumps(invalid), content_type='application/json').status_code, 400)
        self.client.force_login(self.user)
        prepare = self.client.post(reverse('calculators:talking-flyer-save-prepare'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(prepare.status_code, 200)
        foreign = get_user_model().objects.create_user(email='other-owner@example.test', password='safe-password')
        foreign_project = Project.objects.create(owner=foreign, name='Not yours')
        response = self.client.post(reverse('calculators:talking-flyer-save'), {'project_id':str(foreign_project.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose one of your active projects.')
        self.assertEqual(CostEstimate.objects.count(), 0)

    def test_anonymous_save_context_survives_registration_return(self):
        payload = self.customer_payload()
        prepare = self.client.post(reverse('calculators:talking-flyer-save-prepare'),
            data=json.dumps(payload), content_type='application/json')
        self.assertEqual(prepare.status_code, 200)
        register_url = '/accounts/register/?next=%2Fcalculators%2Ftalking-flyer%2Fsave%2F'
        registration = self.client.post(register_url, {'email':'new-flyer-owner@example.test',
            'first_name':'Flyer', 'last_name':'Owner', 'password1':'Strong-TalkingFlyer-2026!',
            'password2':'Strong-TalkingFlyer-2026!'})
        self.assertEqual(registration.status_code, 302)
        self.assertEqual(registration.url, '/calculators/talking-flyer/save/')
        self.assertContains(self.client.get(registration.url), 'Choose a project')
