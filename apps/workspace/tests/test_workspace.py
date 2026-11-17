import json
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.pricing.models import CostEstimate, ExchangeRate, ModelPricing
from apps.video_registry.models import Provider, VideoModel, Workflow
from apps.workspace.models import Project


class WorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='owner@example.test', password='A-Strong-User-Password-48!')
        self.other_user = User.objects.create_user(email='other@example.test', password='A-Strong-Other-Password-48!')
        self.project = Project.objects.create(owner=self.user, name='Launch video')
        self.other_project = Project.objects.create(owner=self.other_user, name='Private project')
        self.workflow = Workflow.objects.get(slug='text-to-video')
        self.provider = Provider.objects.create(name='Workspace Synthetic Lab', slug='workspace-synthetic-lab')
        self.model = VideoModel.objects.create(provider=self.provider, name='Workspace Model', slug='workspace-model', version='1')
        self.model.workflows.add(self.workflow)
        self.price = ModelPricing.objects.create(
            video_model=self.model, workflow=self.workflow, method=ModelPricing.Method.FIXED_GENERATION,
            rate=Decimal('0.50'), unit='generation', currency='USD', effective_from=timezone.now()-timedelta(hours=1),
            failed_attempt_billing=ModelPricing.FailedAttemptBilling.BILLABLE,
            verification_status='unverified', evidence_description='Synthetic workspace fixture.',
        )
        self.client.force_login(self.user)

    def estimate_payload(self, **overrides):
        data = {
            'components': [{
                'video_model_id': str(self.model.pk), 'workflow_slug': self.workflow.slug,
                'duration_seconds': '5', 'generation_requests': 2, 'clip_count': 2,
                'pricing_record_id': str(self.price.pk), 'retry_allowance': 0,
            }],
            'output_currency': 'USD', 'project_id': str(self.project.pk),
        }
        data.update(overrides)
        return data

    def save_estimate(self, data=None):
        return self.client.post(reverse('pricing:estimate'), data=json.dumps(data or self.estimate_payload()), content_type='application/json')

    def test_registration_login_and_logout(self):
        self.client.logout()
        response = self.client.post(reverse('accounts:register'), {
            'email': 'new-user@example.test', 'first_name': 'New', 'last_name': 'User',
            'password1': 'Silver-Paper-74!Ocean', 'password2': 'Silver-Paper-74!Ocean',
        })
        self.assertRedirects(response, reverse('workspace:dashboard'))
        self.assertTrue(self.client.session.get('_auth_user_id'))
        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('home'))
        response = self.client.post(reverse('accounts:login'), {'username': 'new-user@example.test', 'password': 'Silver-Paper-74!Ocean'})
        self.assertRedirects(response, reverse('workspace:dashboard'))

    def test_registration_preserves_local_calculator_return_and_rejects_external_return(self):
        self.client.logout()
        response = self.client.post(reverse('accounts:register'), {
            'email': 'resume-user@example.test', 'password1': 'Silver-Paper-74!Ocean',
            'password2': 'Silver-Paper-74!Ocean', 'next': '/pricing/test/?resume=1',
        })
        self.assertRedirects(response, '/pricing/test/?resume=1')
        self.client.logout()
        response = self.client.post(reverse('accounts:register'), {
            'email': 'external-return-user@example.test', 'password1': 'Silver-Paper-74!Ocean',
            'password2': 'Silver-Paper-74!Ocean', 'next': 'https://example.invalid/steal',
        })
        self.assertRedirects(response, reverse('workspace:dashboard'))

    def test_project_management_and_owner_scoped_browser_pages(self):
        own_projects = self.client.get(reverse('workspace:api-project-list')).json()['results']
        self.assertEqual([item['id'] for item in own_projects], [str(self.project.pk)])
        self.assertEqual(self.client.get(reverse('workspace:estimate-create', args=[self.project.pk])).status_code, 200)
        response = self.client.post(reverse('workspace:project-create'), {'name': '  New short film  ', 'description': 'Planning notes'})
        created = Project.objects.get(owner=self.user, name='New short film')
        self.assertRedirects(response, reverse('workspace:project-detail', args=[created.pk]))
        self.assertEqual(self.client.get(reverse('workspace:project-list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('workspace:project-detail', args=[self.other_project.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('workspace:project-edit', args=[self.other_project.pk]), {'name': 'Stolen', 'description': ''}).status_code, 404)
        response = self.client.post(reverse('workspace:project-edit', args=[created.pk]), {'name': 'Revised name', 'description': 'Updated'})
        self.assertRedirects(response, reverse('workspace:project-detail', args=[created.pk]))
        response = self.client.post(reverse('workspace:project-archive', args=[created.pk]))
        created.refresh_from_db()
        self.assertEqual(created.status, Project.Status.ARCHIVED)
        self.assertIsNotNone(created.archived_at)
        response = self.client.post(reverse('workspace:project-restore', args=[created.pk]))
        created.refresh_from_db()
        self.assertEqual(created.status, Project.Status.ACTIVE)
        self.assertIsNone(created.archived_at)

    def test_unauthenticated_workspace_and_estimate_access_is_denied(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('workspace:dashboard')).status_code, 302)
        self.assertEqual(self.client.get(reverse('workspace:project-list')).status_code, 302)
        self.assertEqual(self.client.get(reverse('workspace:api-project-list')).status_code, 401)
        self.assertEqual(self.save_estimate().status_code, 401)
        self.assertEqual(self.client.get(reverse('pricing:estimate-detail', args=['00000000-0000-0000-0000-000000000001'])).status_code, 401)

    def test_owner_scoped_api_rejects_uuid_substitution_and_foreign_project_saves(self):
        self.assertEqual(self.client.get(reverse('workspace:api-project-detail', args=[self.other_project.pk])).status_code, 404)
        foreign_payload = self.estimate_payload(project_id=str(self.other_project.pk))
        self.assertEqual(self.save_estimate(foreign_payload).status_code, 404)
        forged_owner = self.estimate_payload(owner_id=str(self.other_user.pk))
        self.assertEqual(self.save_estimate(forged_owner).status_code, 400)

    def test_estimate_is_saved_under_user_project_and_history_reopens_snapshot(self):
        response = self.save_estimate()
        self.assertEqual(response.status_code, 200)
        estimate = CostEstimate.objects.get(pk=response.json()['estimate_id'])
        self.assertEqual((estimate.owner, estimate.project), (self.user, self.project))
        self.assertEqual(estimate.result['commercial']['total_estimated_production_cost'], '1.00')
        history = self.client.get(reverse('workspace:api-project-estimates', args=[self.project.pk]))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()['results'][0]['production_cost'], '1.00')
        detail = self.client.get(reverse('workspace:api-estimate-detail', args=[estimate.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['result_snapshot']['commercial']['total_estimated_production_cost'], '1.00')
        self.assertEqual(self.client.get(reverse('workspace:estimate-detail', args=[estimate.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('workspace:api-estimate-detail', args=[estimate.pk]), HTTP_HOST='localhost').status_code, 200)

    def test_another_user_cannot_read_estimate_or_compare_it(self):
        response = self.save_estimate()
        estimate_id = response.json()['estimate_id']
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(reverse('workspace:api-estimate-detail', args=[estimate_id])).status_code, 404)
        own_other_estimate = self.client.post(reverse('pricing:estimate'),
            data=json.dumps(self.estimate_payload(project_id=str(self.other_project.pk))), content_type='application/json')
        self.assertEqual(own_other_estimate.status_code, 200)
        self.client.force_login(self.user)
        compare = self.client.post(reverse('workspace:api-estimate-compare'),
            data=json.dumps({'estimate_ids': [estimate_id, own_other_estimate.json()['estimate_id']]}), content_type='application/json')
        self.assertEqual(compare.status_code, 404)

    def test_pricing_change_does_not_recalculate_historical_estimate_and_revised_estimate_is_new(self):
        first_response = self.save_estimate()
        first = CostEstimate.objects.get(pk=first_response.json()['estimate_id'])
        first_result = first.result.copy()
        now = timezone.now()
        self.price.effective_until = now
        self.price.save()
        revised_price = ModelPricing.objects.create(
            video_model=self.model, workflow=self.workflow, method=ModelPricing.Method.FIXED_GENERATION,
            rate=Decimal('0.80'), unit='generation', currency='USD', effective_from=now+timedelta(seconds=1),
            failed_attempt_billing=ModelPricing.FailedAttemptBilling.BILLABLE,
            verification_status='unverified', evidence_description='Second synthetic price period.',
        )
        self.assertEqual(self.client.get(reverse('workspace:api-estimate-detail', args=[first.pk])).json()['result_snapshot'], first_result)
        second_data = self.estimate_payload(as_of=(now+timedelta(seconds=2)).isoformat().replace('+00:00', 'Z'))
        second_data['components'][0]['pricing_record_id'] = str(revised_price.pk)
        second_response = self.save_estimate(second_data)
        second = CostEstimate.objects.get(pk=second_response.json()['estimate_id'])
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.result['commercial']['total_estimated_production_cost'], '1.00')
        self.assertEqual(second.result['commercial']['total_estimated_production_cost'], '1.60')
        first.result = {'tampered': True}
        with self.assertRaises(ValidationError):
            first.save()

    def test_comparison_keeps_different_currencies_separate_and_preserves_fx_snapshot(self):
        first = self.save_estimate().json()['estimate_id']
        ExchangeRate.objects.create(base_currency='USD', quote_currency='NGN', rate=1500,
            effective_at=timezone.now()-timedelta(minutes=1), source='Synthetic test rate')
        second_data = self.estimate_payload(output_currency='NGN')
        second = self.save_estimate(second_data).json()['estimate_id']
        response = self.client.post(reverse('workspace:api-estimate-compare'),
            data=json.dumps({'estimate_ids': [first, second]}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['currency'] for item in response.json()['estimates']], ['USD', 'NGN'])
        self.assertEqual([item['production_cost'] for item in response.json()['estimates']], ['1.00', '1500.00'])
        snapshot = self.client.get(reverse('workspace:api-estimate-detail', args=[second])).json()['result_snapshot']
        self.assertEqual(snapshot['model_costs'][0]['exchange_rate']['rate'], '1500.0000000000')

    def test_legacy_unassigned_estimates_are_preserved_but_never_user_visible(self):
        legacy = CostEstimate.objects.bulk_create([CostEstimate(inputs={'legacy': True}, result={'status': 'complete'})])[0]
        self.assertIsNone(legacy.owner_id)
        self.assertIsNone(legacy.project_id)
        self.assertEqual(self.client.get(reverse('workspace:api-estimate-detail', args=[legacy.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('pricing:estimate-detail', args=[legacy.pk])).status_code, 404)
        with self.assertRaises(ValidationError):
            CostEstimate.objects.create(inputs={}, result={})

    def test_incomplete_estimates_are_saved_and_remain_incomplete_in_history(self):
        unpriced = VideoModel.objects.create(provider=self.provider, name='Unpriced Model', slug='unpriced-model', version='1')
        unpriced.workflows.add(self.workflow)
        payload = self.estimate_payload()
        payload['components'][0]['video_model_id'] = str(unpriced.pk)
        payload['components'][0].pop('pricing_record_id')
        response = self.save_estimate(payload)
        self.assertEqual(response.status_code, 422)
        saved = CostEstimate.objects.get(pk=response.json()['estimate_id'])
        self.assertEqual(saved.result['status'], 'incomplete')
        detail = self.client.get(reverse('workspace:api-estimate-detail', args=[saved.pk]))
        self.assertEqual(detail.json()['result_snapshot']['commercial']['status'], 'incomplete')

    def test_estimate_cannot_bind_another_users_project_even_through_model_validation(self):
        with self.assertRaises(ValidationError):
            CostEstimate.objects.create(owner=self.user, project=self.other_project, inputs={}, result={})

    def test_archive_blocks_new_estimates_and_csrf_is_required(self):
        self.project.archive()
        self.assertEqual(self.save_estimate().status_code, 400)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(reverse('workspace:project-archive', args=[self.project.pk]))
        self.assertEqual(response.status_code, 403)
