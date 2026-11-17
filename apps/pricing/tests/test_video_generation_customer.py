import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.pricing.contracts import validate_video_generation_contract
from apps.pricing.models import CostEstimate, ModelPricing, ProductionTool, ProductionToolPricing
from apps.video_registry.models import AccessRoute, Capability, Evidence, Provider, ProviderOffering, Specialty, VideoModel, Workflow
from apps.workspace.models import Project


class VideoGenerationCustomerTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.specialty = Specialty.objects.get(slug='video-generation-animation')
        self.provider = Provider.objects.create(name='Customer Video Studio', slug='customer-video-studio', website_url='https://video.example.test')
        self.provider.specialties.add(self.specialty)
        self.offering = ProviderOffering.objects.create(provider=self.provider, name='Direct API', slug='direct-api', offering_type='api')
        self.offering.specialties.add(self.specialty)
        self.workflow = Workflow.objects.get(slug='text-to-video')
        self.model = VideoModel.objects.create(provider=self.provider, name='Customer Video Model', slug='customer-video-model', version='v1')
        self.model.workflows.add(self.workflow)
        self.model.offerings.add(self.offering)
        self.route = AccessRoute.objects.create(offering=self.offering, name='API usage', route_type='api', pricing_method='per_use')
        self.route.video_models.add(self.model)
        self.price = ModelPricing.objects.create(video_model=self.model, workflow=self.workflow, access_route=self.route,
            method=ModelPricing.Method.FIXED_GENERATION, rate=Decimal('0.50'), unit=ModelPricing.Unit.GENERATION,
            currency='USD', effective_from=now - timedelta(days=1), verification_status=ModelPricing.Verification.TESTED,
            evidence_description='Synthetic test fixture', checked_at=now)
        self.user = get_user_model().objects.create_user(email='video-generation-customer@example.test', password='safe-password')
        self.project = Project.objects.create(owner=self.user, name='Video project')

    def payload(self):
        return {'calculator_type': 'video_generation', 'output_currency': 'USD', 'project_id': str(self.project.pk),
            'markup_percentage': '25', 'components': [{'video_model_id': str(self.model.pk), 'workflow_slug': self.workflow.slug,
                'specialty_slug': self.specialty.slug, 'provider_id': str(self.provider.pk), 'offering_id': str(self.offering.pk),
                'access_route_id': str(self.route.pk), 'pricing_record_id': str(self.price.pk), 'configuration': {},
                'generation_requests': 2, 'clip_count': 2, 'duration_seconds': '5'}],
            'operations': [], 'tools': [], 'overheads': [],
            'production': {'desired_final_duration_seconds': '30', 'expected_usable_duration_seconds': '8'},
            'video_generation': {'schema_version': 1, 'title': 'Launch story', 'video_brief': 'Introduce a new product to small businesses.',
                'purpose': 'Product awareness', 'target_audience': 'Small business owners', 'destination_platform': 'Website',
                'aspect_ratio': '16:9', 'output_resolution': '1080p', 'target_finished_duration_seconds': '30',
                'visual_style': 'Warm documentary', 'production_instructions': 'Keep claims factual.',
                'script_preparation_method': 'self_written', 'tone': '', 'narrative_direction': '',
                'script_directions': 'Friendly delivery.', 'script': 'A better way to work.', 'scriptwriting_tool_id': None,
                'scenes': [{'sequence': 1, 'title': 'Opening', 'description': 'Show a busy shop.', 'visual_direction': 'Morning light',
                    'camera_direction': 'Slow push in', 'generation_prompt': 'Small shop opening at sunrise', 'planned_duration_seconds': '6',
                    'required_visual_assets': 'Shop sign', 'required_voice_audio': 'Voiceover', 'production_notes': 'No brand marks'},
                    {'sequence': 2, 'title': 'Product', 'description': 'Reveal the product.', 'planned_duration_seconds': '4'}]}}

    def test_customer_entry_points_and_external_script_scene_workflow_render(self):
        for url in (reverse('calculators:video-generation'), reverse('home'), reverse('products:list'), reverse('calculators:index')):
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code, 200)
        page = self.client.get(reverse('calculators:video-generation'))
        for text in ('Video Generation Calculator', 'external AI assistant', 'Prepare external prompt', 'Copy prompt',
                     'Plan scenes', 'Add scene'):
            self.assertContains(page, text)
        self.assertContains(page, 'vg-primary-specialty')
        self.assertContains(page, 'video-generation-animation')
        self.assertContains(page, 'scriptwriting-creative-development')

    def test_catalogue_cascade_and_server_estimate_persistence_and_reuse(self):
        providers = self.client.get(reverse('video_registry:specialty-providers', args=[self.specialty.slug]))
        self.assertEqual(providers.status_code, 200)
        self.assertEqual(providers.json()['results'][0]['slug'], self.provider.slug)
        qs = {'specialty': self.specialty.slug, 'provider': self.provider.slug}
        offering = self.client.get(reverse('video_registry:offering-list'), qs)
        self.assertEqual(offering.json()['results'][0]['id'], str(self.offering.pk))
        qs = {'specialty': self.specialty.slug, 'provider': self.provider.slug,
              'offering': str(self.offering.pk), 'access_route': str(self.route.pk)}
        models = self.client.get(reverse('video_registry:model-list'), qs)
        self.assertEqual(models.json()['results'][0]['version'], 'v1')

        self.client.force_login(self.user)
        response = self.client.post(reverse('pricing:estimate'), data=json.dumps(self.payload()), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content.decode())
        saved = CostEstimate.objects.get(pk=response.json()['estimate_id'])
        self.assertEqual(saved.calculator_type, CostEstimate.CalculatorType.VIDEO_GENERATION)
        self.assertEqual(saved.result['summary']['billable_generated_seconds'], '10')
        self.assertEqual(saved.inputs['video_generation']['total_planned_scene_duration_seconds'], '10')
        self.assertEqual(saved.inputs['video_generation']['scenes'][0]['camera_direction'], 'Slow push in')
        reuse = self.client.get(reverse('calculators:video-generation') + f'?from={saved.pk}')
        self.assertEqual(reuse.status_code, 200)
        self.assertContains(reuse, 'Reusing saved estimate')
        self.assertContains(reuse, 'A better way to work.')
        self.assertEqual(self.client.get(reverse('workspace:estimate-detail', args=[saved.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse('workspace:estimate-detail', args=[saved.pk])), 'Reuse this brief and scene plan')

    def test_video_contract_preserves_scene_fields_and_rejects_invalid_or_inapplicable_script_tool(self):
        payload = self.payload()['video_generation']
        result = validate_video_generation_contract(payload, [])
        self.assertEqual(result['total_planned_scene_duration_seconds'], '10')
        self.assertEqual(result['scenes'][0]['visual_direction'], 'Morning light')
        self.assertEqual(result['target_finished_duration_seconds'], '30')
        payload['script_preparation_method'] = 'ai_assisted'
        payload['scriptwriting_tool_id'] = 'tool-1'
        with self.assertRaisesRegex(ValueError, 'priced scriptwriting tool'):
            validate_video_generation_contract(payload, [])
        payload['script_preparation_method'] = 'self_written'
        with self.assertRaisesRegex(ValueError, 'cannot select'):
            validate_video_generation_contract(payload, [{'tool_id': 'tool-1'}])
        invalid = self.payload()['video_generation']
        invalid['scenes'][1]['sequence'] = 3
        with self.assertRaisesRegex(ValueError, 'consecutive'):
            validate_video_generation_contract(invalid, [])

    def test_anonymous_estimate_never_persists_or_accepts_project_identity(self):
        self.client.logout()
        payload = self.payload(); payload.pop('project_id')
        response = self.client.post(reverse('pricing:estimate'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertNotIn('estimate_id', response.json())
        self.assertEqual(CostEstimate.objects.count(), 0)
        payload['project_id'] = str(self.project.pk)
        self.assertEqual(self.client.post(reverse('pricing:estimate'), data=json.dumps(payload), content_type='application/json').status_code, 401)

    def test_only_verified_model_configuration_is_selectable_and_server_enforced(self):
        capability = Capability.objects.create(model=self.model, workflow=self.workflow, key='resolution', label='Resolution',
            status=Capability.Status.SUPPORTED, input_type=Capability.InputType.SELECT, allowed_values=['720p', '1080p'])
        Evidence.objects.create(model=self.model, capability=capability, classification=Evidence.Classification.OFFICIAL,
            source_url='https://video.example.test/docs', source_title='Model options', verified_at=timezone.now(), status=Evidence.Status.CURRENT)
        detail = self.client.get(reverse('video_registry:model-capabilities', args=[self.provider.slug, self.model.slug]), {'version': self.model.version})
        self.assertEqual(detail.status_code, 200)
        option = next(item for item in detail.json()['capabilities'] if item['key'] == 'resolution')
        self.assertTrue(option['configuration']['selectable'])
        self.assertEqual(option['configuration']['allowed_values'], ['720p', '1080p'])
        self.client.force_login(self.user)
        payload = self.payload(); payload['components'][0]['configuration'] = {'resolution': '16k'}
        response = self.client.post(reverse('pricing:estimate'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('verified allowed values', response.json()['error'])

    def test_target_finished_duration_cannot_disagree_with_shared_cost_assumptions(self):
        payload = self.payload(); payload['video_generation']['target_finished_duration_seconds'] = '45'
        self.client.force_login(self.user)
        response = self.client.post(reverse('pricing:estimate'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('must match', response.json()['error'])

    def test_external_ai_scriptwriting_tool_is_optional_priced_and_not_called_by_platform(self):
        specialty = Specialty.objects.get(slug='scriptwriting-creative-development')
        provider = Provider.objects.create(name='Configured Writing Service', slug='configured-writing-service', website_url='https://writer.example.test')
        provider.specialties.add(specialty)
        offering = ProviderOffering.objects.create(provider=provider, name='Writing subscription', slug='writing-subscription')
        offering.specialties.add(specialty)
        tool = ProductionTool.objects.create(provider=provider, offering=offering, name='Configured writing tool',
            slug='configured-writing-tool', kind=ProductionTool.Kind.METERED_SERVICE, activities=['script'])
        price = ProductionToolPricing.objects.create(tool=tool, name='Per project', cost_type=ProductionToolPricing.CostType.USAGE,
            method=ProductionToolPricing.Method.FIXED_PROJECT, rate=Decimal('0.25'), currency='USD',
            effective_from=timezone.now() - timedelta(days=1))
        payload = self.payload(); payload['video_generation']['script_preparation_method'] = 'ai_assisted'
        payload['video_generation']['scriptwriting_tool_id'] = str(tool.pk)
        payload['tools'] = [{'tool_id': str(tool.pk), 'provider_id': str(provider.pk), 'offering_id': str(offering.pk),
            'specialty_slug': specialty.slug, 'activities': ['script'], 'usage_pricing_id': str(price.pk),
            'usage_quantity': '1', 'included_allowance_remaining': '0'}]
        self.client.force_login(self.user)
        response = self.client.post(reverse('pricing:estimate'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()['commercial']['production_tool_cost'], '0.25')
        self.assertEqual(response.json()['calculator_type'], 'video_generation')
        self.assertContains(self.client.get(reverse('calculators:video-generation')), 'does not call an AI service')
