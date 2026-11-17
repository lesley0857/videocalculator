from django.core.exceptions import ValidationError
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.video_registry.models import (AccessRoute, Capability, CapabilityRevision, Evidence,
    Provider, ProviderOffering, Specialty, VideoModel, Workflow)
from apps.video_registry.services import (filter_models, get_active_providers, get_model,
    validate_model_configuration)


class RegistryDataTests(TestCase):
    def setUp(self):
        self.provider = Provider.objects.create(name='Example Studio', slug='example-studio')
        self.workflow, _ = Workflow.objects.get_or_create(name='Text to video', slug='text-to-video')
        self.model = VideoModel.objects.create(provider=self.provider, name='Studio Video', slug='studio-video', version='1')
        self.model.workflows.add(self.workflow)

    def test_provider_is_unique_and_status_controls_active_listing(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Provider.objects.create(name='Example Studio', slug='another-slug')
        self.assertEqual(get_active_providers(), [self.provider])
        self.provider.status = Provider.Status.INACTIVE
        self.provider.save(update_fields=['status', 'updated_at'])
        self.assertEqual(get_active_providers(), [])

    def test_model_versions_are_distinct_and_unique_per_provider(self):
        later = VideoModel.objects.create(provider=self.provider, name='Studio Video', slug='studio-video', version='2')
        self.assertNotEqual(self.model.pk, later.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VideoModel.objects.create(provider=self.provider, name='Studio Video', slug='studio-video', version='1')
        self.assertEqual(get_model(self.provider.slug, self.model.slug, '1').pk, self.model.pk)

    def test_workflow_and_capability_filters_only_return_supported_models(self):
        Capability.objects.create(model=self.model, key='native_audio', label='Native audio', status=Capability.Status.UNKNOWN)
        self.assertEqual(filter_models(workflow='text-to-video'), [self.model])
        self.assertEqual(filter_models(capability='native_audio'), [])
        Capability.objects.filter(model=self.model, key='native_audio').update(status=Capability.Status.SUPPORTED)
        self.assertEqual(filter_models(capability='native_audio'), [self.model])

    def test_capabilities_can_explicitly_be_unknown_or_not_supported(self):
        unknown = Capability.objects.create(model=self.model, key='lip_sync', label='Lip sync')
        unsupported = Capability.objects.create(model=self.model, key='video_input', label='Video input', status=Capability.Status.NOT_SUPPORTED)
        self.assertEqual(unknown.status, Capability.Status.UNKNOWN)
        self.assertEqual(unsupported.status, Capability.Status.NOT_SUPPORTED)

    def test_capability_changes_keep_prior_state(self):
        item = Capability.objects.create(model=self.model, key='max_duration_seconds', label='Maximum duration', value='5', unit='seconds')
        item.value = '10'
        item.save()
        self.assertEqual(CapabilityRevision.objects.get(capability=item).prior_value, '5')

    def test_structured_capability_revision_and_verified_configuration(self):
        cap = Capability.objects.create(model=self.model, key='resolution', label='Resolution',
            status=Capability.Status.SUPPORTED, input_type=Capability.InputType.SELECT,
            allowed_values=['720p', '1080p'])
        with self.assertRaisesRegex(ValueError, 'verified capability'):
            validate_model_configuration(self.model, self.workflow, {'resolution': '720p'})
        Evidence.objects.create(model=self.model, capability=cap,
            classification=Evidence.Classification.TESTED, status=Evidence.Status.CURRENT,
            verified_at='2026-11-15T09:00:00Z')
        self.assertEqual(validate_model_configuration(self.model, self.workflow, {'resolution': '1080p'}), {'resolution': '1080p'})
        with self.assertRaisesRegex(ValueError, 'allowed values'):
            validate_model_configuration(self.model, self.workflow, {'resolution': '4k'})
        cap.allowed_values = ['720p']
        cap.save()
        revision = CapabilityRevision.objects.get(capability=cap)
        self.assertEqual(revision.prior_allowed_values, ['720p', '1080p'])

    def test_specialty_offering_and_route_relationships_filter_models(self):
        specialty = Specialty.objects.get(slug='video-generation-animation')
        self.provider.specialties.add(specialty)
        offering = ProviderOffering.objects.create(provider=self.provider, name='Studio API', slug='studio-api', offering_type='api')
        offering.specialties.add(specialty)
        self.model.offerings.add(offering)
        route = AccessRoute.objects.create(offering=offering, name='Direct API', route_type='api', pricing_method='per_second')
        route.video_models.add(self.model)
        self.assertEqual(filter_models(specialty_slug=specialty.slug, offering_id=offering.pk, route_id=route.pk), [self.model])
        response = self.client.get(reverse('video_registry:specialty-providers', args=[specialty.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['slug'], self.provider.slug)
        offering.is_active = False
        offering.save()
        self.assertEqual(self.client.get(reverse('video_registry:specialty-providers', args=[specialty.slug])).json()['results'], [])

    def test_evidence_requires_same_model_and_official_source(self):
        capability = Capability.objects.create(model=self.model, key='speech', label='Speech')
        other = VideoModel.objects.create(provider=self.provider, name='Other', slug='other', version='1')
        evidence = Evidence(model=other, capability=capability, classification=Evidence.Classification.OFFICIAL)
        with self.assertRaises(ValidationError):
            evidence.full_clean()
        evidence.capability = None
        with self.assertRaises(ValidationError):
            evidence.full_clean()
        evidence.source_url = 'https://docs.example.test/video'
        evidence.full_clean()


class RegistryApiTests(TestCase):
    def setUp(self):
        self.provider = Provider.objects.create(name='Example Studio', slug='example-studio', description='Public description')
        self.workflow, _ = Workflow.objects.get_or_create(name='Text to video', slug='text-to-video')
        self.model = VideoModel.objects.create(provider=self.provider, name='Studio Video', slug='studio-video', version='v1', admin_notes='secret')
        self.model.workflows.add(self.workflow)
        self.capability = Capability.objects.create(model=self.model, key='native_audio', label='Native audio', status=Capability.Status.SUPPORTED)
        Evidence.objects.create(model=self.model, capability=self.capability,
            classification=Evidence.Classification.OFFICIAL, source_url='https://docs.example.test/model',
            source_title='Model docs', status=Evidence.Status.CURRENT,
            verified_at='2026-11-15T09:00:00Z')

    def test_provider_list_and_detail(self):
        response = self.client.get(reverse('video_registry:provider-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'][0]['slug'], 'example-studio')
        self.assertEqual(self.client.get(reverse('video_registry:provider-detail', args=['example-studio'])).status_code, 200)
        self.assertEqual(self.client.get(reverse('video_registry:provider-detail', args=['missing'])).status_code, 404)

    def test_model_list_and_detail_expose_versions_evidence_but_not_private_notes(self):
        response = self.client.get(reverse('video_registry:model-list'))
        self.assertEqual(response.status_code, 200)
        detail = self.client.get(reverse('video_registry:model-detail', args=['example-studio', 'studio-video']))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['version'], 'v1')
        self.assertEqual(detail.json()['capabilities'][0]['status'], 'supported')
        self.assertEqual(detail.json()['capabilities'][0]['evidence'][0]['source_url'], 'https://docs.example.test/model')
        self.assertNotIn('secret', detail.content.decode())

    def test_filter_by_capability_and_workflow_and_reject_invalid_filter(self):
        self.assertEqual(len(self.client.get(reverse('video_registry:model-list'), {'capability': 'native_audio'}).json()['results']), 1)
        self.assertEqual(len(self.client.get(reverse('video_registry:model-list'), {'workflow': 'text-to-video'}).json()['results']), 1)
        self.assertEqual(self.client.get(reverse('video_registry:model-list'), {'workflow': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(reverse('video_registry:model-list'), {'capability': 'bad'}).status_code, 400)

    def test_model_capability_endpoint_is_read_only_and_missing_model_is_404(self):
        url = reverse('video_registry:model-capabilities', args=['example-studio', 'studio-video'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['verification_status'], 'unverified')
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.get(reverse('video_registry:model-detail', args=['example-studio', 'missing'])).status_code, 404)

    def test_registry_models_are_registered_in_admin(self):
        for model in (Provider, VideoModel, Capability, Evidence, Workflow):
            self.assertTrue(admin.site.is_registered(model))
        self.assertEqual(reverse('admin:video_registry_provider_changelist'), '/admin/video_registry/provider/')

    def test_admin_lists_and_create_forms_load_for_staff(self):
        user = get_user_model().objects.create_superuser(email='registry-admin@example.test', password='test-password')
        self.client.force_login(user)
        routes = (
            'admin:video_registry_provider_changelist',
            'admin:video_registry_provider_add',
            'admin:video_registry_videomodel_changelist',
            'admin:video_registry_videomodel_add',
            'admin:video_registry_workflow_changelist',
            'admin:video_registry_capability_changelist',
            'admin:video_registry_capability_add',
            'admin:video_registry_evidence_changelist',
            'admin:video_registry_evidence_add',
            'admin:video_registry_capabilityrevision_changelist',
        )
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

