"""Seed only first-party, researched catalogue entries without overwriting rows."""
from datetime import date, datetime, timezone
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pricing.models import ModelPricing, ProductionTool, ProductionToolPricing, SubscriptionPlan
from apps.video_registry.models import (
    AccessRoute, Capability, Evidence, Provider, ProviderOffering, Specialty, VideoModel, Workflow,
)


CHECKED_AT = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
EFFECTIVE_FROM = datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)

SOURCES = {
    'openai_plus': 'https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus',
    'openai_regions': 'https://help.openai.com/en/articles/7947663-chatgpt-supported-countries',
    'anthropic_plans': 'https://support.anthropic.com/en/articles/11049762-choosing-a-claude-ai-plan',
    'anthropic_regions': 'https://www.anthropic.com/legal/supported-regions',
    'google_video': 'https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash',
    'google_pricing': 'https://ai.google.dev/gemini-api/docs/pricing',
    'google_regions': 'https://ai.google.dev/gemini-api/docs/available-regions',
    'google_veo_cloud': 'https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate.md',
    'google_cloud_prices': 'https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing',
    'elevenlabs_api': 'https://elevenlabs.io/pricing/api',
    'canva_plans': 'https://www.canva.com/pricing/?countryCode=us&currency=USD',
    'capcut_plans': 'https://www.capcut.com/pricing',
    'capcut_regional': 'https://www.capcut.com/help/how-much-does-capcut-pro-cost',
}


class Command(BaseCommand):
    help = 'Import the reviewed first-party provider catalogue; defaults to a rollback-only dry run.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Commit the import (otherwise perform a dry run).')

    def handle(self, *args, **options):
        self.created = 0
        self.unchanged = 0
        try:
            with transaction.atomic():
                self._populate()
                summary = f'Catalogue rows created: {self.created}; existing rows preserved: {self.unchanged}.'
                if not options['apply']:
                    self.stdout.write('DRY RUN — ' + summary)
                    transaction.set_rollback(True)
                    return
            self.stdout.write(self.style.SUCCESS('APPLIED — ' + summary))
        except Exception:
            raise

    def _get(self, model, key, defaults):
        row, created = model.objects.get_or_create(**key, defaults=defaults)
        self.created += int(created)
        self.unchanged += int(not created)
        return row

    def _specialty(self, slug):
        return Specialty.objects.get(slug=slug)

    def _provider(self, name, slug, category, url, specialties, description):
        row = self._get(Provider, {'slug': slug}, {
            'name': name, 'category': category, 'website_url': url,
            'description': description, 'status': Provider.Status.ACTIVE,
        })
        if not row.specialties.exists():
            row.specialties.add(*(self._specialty(x) for x in specialties))
        return row

    def _offering(self, provider, name, slug, kind, specialties, url, reference, description):
        row = self._get(ProviderOffering, {'provider': provider, 'slug': slug}, {
            'name': name, 'offering_type': kind, 'website_url': url,
            'reference_url': reference, 'description': description,
            'is_active': True,
        })
        if not row.specialties.exists():
            row.specialties.add(*(self._specialty(x) for x in specialties))
        return row

    def _plan(self, provider, offering, name, slug, price, period, source, note, *, included=None, active=False):
        return self._get(SubscriptionPlan, {'provider_offering': offering, 'slug': slug}, {
            'provider': provider, 'name': name, 'subscription_price': Decimal(price),
            'currency': 'USD', 'period': period, 'effective_from': EFFECTIVE_FROM,
            'is_active': active, 'verification_status': 'officially_documented',
            'source_url': source, 'checked_at': CHECKED_AT,
            'evidence_description': 'Official first-party plan page checked 2026-11-17.',
            'notes': note, 'included_quantity': Decimal(included) if included else None,
            'included_unit': 'characters' if included else '',
            'allocation_method': ProductionToolPricing.Allocation.MANUAL if active else '',
        })

    def _populate(self):
        script = 'scriptwriting-creative-development'
        image = 'image-visual-asset-creation'
        video = 'video-generation-animation'
        voice = 'voice-narration'
        editing = 'editing-finishing'

        openai = self._provider('OpenAI', 'openai', 'AI platform', 'https://openai.com', [script, image],
            'OpenAI provides ChatGPT subscriptions and a separately billed developer API.')
        chatgpt = self._offering(openai, 'ChatGPT', 'chatgpt', ProviderOffering.OfferingType.PRODUCT,
            [script, image], 'https://chatgpt.com', SOURCES['openai_plus'],
            'Consumer application for writing and supported image capabilities; API access is separate.')
        self._plan(openai, chatgpt, 'ChatGPT Plus (US list price)', 'chatgpt-plus-us', '20.00',
            SubscriptionPlan.Period.MONTHLY, SOURCES['openai_plus'],
            'US list price. API usage is billed separately; regional checkout price and taxes must be confirmed. Not exposed as a locally priced plan.', active=False)
        self._offering(openai, 'OpenAI API', 'openai-api', ProviderOffering.OfferingType.API,
            [script, image], 'https://platform.openai.com', 'https://platform.openai.com/pricing/',
            'Developer API. Token-based text/image pricing is researched but not expressible by the existing video-generation pricing contract.')

        anthropic = self._provider('Anthropic', 'anthropic', 'AI platform', 'https://www.anthropic.com', [script],
            'Anthropic provides Claude consumer plans and a separately billed developer platform.')
        claude = self._offering(anthropic, 'Claude', 'claude', ProviderOffering.OfferingType.PRODUCT,
            [script], 'https://claude.ai', SOURCES['anthropic_plans'],
            'Consumer assistant for writing and creative development; API access is separate.')
        self._plan(anthropic, claude, 'Claude Pro (US list price)', 'claude-pro-us', '20.00',
            SubscriptionPlan.Period.MONTHLY, SOURCES['anthropic_plans'],
            'US monthly list price. Local billing varies by region. Nigeria is listed in the current supported-regions policy. API usage is separate.', active=False)
        self._offering(anthropic, 'Claude API', 'claude-api', ProviderOffering.OfferingType.API,
            [script], 'https://platform.claude.com', 'https://platform.claude.com/docs/en/about-claude/pricing',
            'Developer API. Token-based input/output billing is not representable in the existing project calculator contract.')

        google = self._provider('Google', 'google', 'Cloud and AI platform', 'https://ai.google.dev', [video],
            'Gemini API and Gemini Enterprise Agent Platform provide distinct video model access routes.')
        gemini_api = self._offering(google, 'Gemini API', 'gemini-api', ProviderOffering.OfferingType.API,
            [video], 'https://ai.google.dev/gemini-api', SOURCES['google_video'],
            'Developer API offering. Nigeria appears in the current published Gemini API supported-region list.')
        omni = self._get(VideoModel, {'provider': google, 'slug': 'gemini-omni-flash', 'version': 'gemini-omni-1.1-flash'}, {
            'name': 'Gemini Omni Flash', 'family': 'Gemini Omni Flash',
            'description': 'Stable Gemini API model for conversational video generation and editing.',
            'documentation_url': SOURCES['google_video'], 'api_documentation_url': SOURCES['google_video'],
            'release_date': date(2026, 8, 1), 'status': VideoModel.Status.ACTIVE,
            'verification_status': VideoModel.Verification.VERIFIED,
        })
        omni.offerings.add(gemini_api)
        video_workflow = Workflow.objects.get(slug='text-to-video')
        omni.workflows.add(video_workflow)
        api_route = self._get(AccessRoute, {'offering': gemini_api, 'name': 'Gemini API pay-as-you-go'}, {
            'route_type': AccessRoute.RouteType.API, 'pricing_method': AccessRoute.PricingMethod.PER_SECOND,
            'description': 'Paid Gemini API route; use account-specific quotas and billing terms.', 'is_active': True,
        })
        api_route.video_models.add(omni)
        capabilities = [
            ('text_to_video', 'Text to video', Capability.Status.SUPPORTED, Capability.InputType.FLAG, 'supported', [], '', None, None),
            ('image_to_video', 'Image to video', Capability.Status.SUPPORTED, Capability.InputType.FLAG, 'supported', [], '', None, None),
            ('video_extension', 'Video extension and editing', Capability.Status.SUPPORTED, Capability.InputType.FLAG, 'supported', [], '', None, None),
            ('native_audio', 'Native audio', Capability.Status.SUPPORTED, Capability.InputType.FLAG, 'supported', [], '', None, None),
            ('generation_duration_seconds', 'Output video duration', Capability.Status.SUPPORTED, Capability.InputType.NUMBER, '', [], 'seconds', Decimal('3'), Decimal('10')),
            ('resolution', 'Output resolution', Capability.Status.SUPPORTED, Capability.InputType.SELECT, '', ['360p', '720p', '1080p', '4K'], '', None, None),
            ('frame_rate', 'Output frame rate', Capability.Status.SUPPORTED, Capability.InputType.SELECT, '', ['24'], 'fps', None, None),
        ]
        for key, label, status, input_type, value, allowed, unit, minv, maxv in capabilities:
            capability = self._get(Capability, {'model': omni, 'workflow': video_workflow, 'key': key}, {
                'label': label, 'status': status, 'input_type': input_type, 'value': value,
                'allowed_values': allowed, 'unit': unit, 'minimum_value': minv, 'maximum_value': maxv,
            })
            self._get(Evidence, {'model': omni, 'capability': capability, 'source_url': SOURCES['google_video']}, {
                'classification': Evidence.Classification.OFFICIAL, 'status': Evidence.Status.CURRENT,
                'source_title': 'Gemini Omni Flash model documentation', 'verified_at': CHECKED_AT,
                'verified_by': 'Task 012 research', 'notes': 'Checked against first-party model and video documentation on 2026-11-17.',
            })
        # Google's published video-output rate is derived from 17.50 USD / million
        # output tokens at 5,792 tokens/second (0.10136 USD/second). The endpoint
        # also bills input tokens, which this app cannot represent, so keep this
        # research row inactive to prevent a false complete estimate.
        self._get(ModelPricing, {'video_model': omni, 'workflow': video_workflow, 'access_route': api_route,
                                 'method': ModelPricing.Method.PER_SECOND, 'configuration': {},
                                 'effective_from': EFFECTIVE_FROM}, {
            'rate': Decimal('0.10136000'), 'unit': ModelPricing.Unit.SECOND, 'currency': 'USD',
            'is_active': False, 'verification_status': 'calculated_or_derived',
            'source_url': SOURCES['google_pricing'], 'checked_at': CHECKED_AT,
            'evidence_description': 'Derived: $17.50 / 1,000,000 video output tokens × 5,792 tokens/second = $0.10136/video second.',
            'administrative_notes': 'Inactive because input text/image/audio token charges are additional and the calculator cannot represent them. Do not enable until the cost contract supports those inputs.',
        })

        # Google Cloud Veo uses a distinct fixed-quota route and US-central1
        # endpoint; keep that route explicit instead of conflating it with the
        # Gemini Developer API. Its price is per output generation count.
        cloud = self._offering(google, 'Gemini Enterprise Agent Platform', 'gemini-enterprise-agent-platform',
            ProviderOffering.OfferingType.API, [video], 'https://cloud.google.com/vertex-ai',
            SOURCES['google_veo_cloud'], 'Google Cloud video model access; these Veo endpoints are in us-central1 and use the documented fixed-quota route.')
        workflows = [Workflow.objects.get(slug='text-to-video'), Workflow.objects.get(slug='image-to-video')]
        for name, slug, version, resolution_values, rates in (
            ('Veo 3.1', 'veo-3-1', 'veo-3.1-generate-001', ['720p', '1080p', '4k'], {
                ('native_audio', '720p'): '0.40', ('native_audio', '1080p'): '0.40', ('native_audio', '4k'): '0.60',
                ('video_only', '720p'): '0.20', ('video_only', '1080p'): '0.20', ('video_only', '4k'): '0.40',
            }),
            ('Veo 3.1 Fast', 'veo-3-1-fast', 'veo-3.1-fast-generate-001', ['720p', '1080p'], {
                ('native_audio', '720p'): '0.10', ('native_audio', '1080p'): '0.12',
                ('video_only', '720p'): '0.08', ('video_only', '1080p'): '0.10',
            }),
        ):
            model = self._get(VideoModel, {'provider': google, 'slug': slug, 'version': version}, {
                'name': name, 'family': 'Veo 3.1',
                'description': 'Google Cloud Veo video generation; exact capabilities and output configuration are evidence-backed.',
                'documentation_url': SOURCES['google_veo_cloud'], 'api_documentation_url': SOURCES['google_veo_cloud'],
                'release_date': date(2025, 11, 17), 'status': VideoModel.Status.ACTIVE,
                'verification_status': VideoModel.Verification.VERIFIED,
            })
            model.offerings.add(cloud)
            model.workflows.add(*workflows)
            route = self._get(AccessRoute, {'offering': cloud, 'name': f'{name} us-central1 fixed-quota API'}, {
                'route_type': AccessRoute.RouteType.API, 'pricing_method': AccessRoute.PricingMethod.PER_USE,
                'description': 'Use the us-central1 endpoint with the published fixed-quota access mode and an active Cloud Billing account.',
                'notes': 'Price is per generated output count. Cloud account eligibility, quota, billing currency, and Nigerian VAT are account-specific.',
                'is_active': True,
            })
            route.video_models.add(model)
            verified_values = [
                ('text_to_video', 'Text to video', Capability.InputType.FLAG, 'supported', [], '', None, None),
                ('image_to_video', 'Image to video', Capability.InputType.FLAG, 'supported', [], '', None, None),
                ('native_audio', 'Native generated audio', Capability.InputType.FLAG, 'supported', [], '', None, None),
                ('video_only', 'Video only (without generated audio)', Capability.InputType.FLAG, '', [], '', None, None),
                ('resolution', 'Output resolution', Capability.InputType.SELECT, '', resolution_values, '', None, None),
                ('aspect_ratio', 'Aspect ratio', Capability.InputType.SELECT, '', ['16:9', '9:16'], '', None, None),
                ('generation_duration_seconds', 'Generation duration', Capability.InputType.SELECT, '', ['4', '6', '8'], 'seconds', None, None),
                ('max_outputs_per_prompt', 'Maximum outputs per prompt', Capability.InputType.FLAG, 'Up to 4 outputs per prompt', [], 'outputs', None, None),
            ]
            for key, label, input_type, value, allowed, unit, minv, maxv in verified_values:
                for workflow in workflows:
                    capability = self._get(Capability, {'model': model, 'workflow': workflow, 'key': key}, {
                        'label': label, 'status': Capability.Status.SUPPORTED, 'input_type': input_type,
                        'value': value, 'allowed_values': allowed, 'unit': unit,
                        'minimum_value': minv, 'maximum_value': maxv,
                        'notes': 'Verified from the Google Cloud model card and pricing documentation.',
                    })
                    source = SOURCES['google_cloud_prices'] if key in ('native_audio', 'video_only') else SOURCES['google_veo_cloud']
                    self._get(Evidence, {'model': model, 'capability': capability, 'source_url': source}, {
                        'classification': Evidence.Classification.OFFICIAL, 'status': Evidence.Status.CURRENT,
                        'source_title': 'Google Cloud Veo 3.1 model and pricing documentation',
                        'verified_at': CHECKED_AT, 'verified_by': 'Task 012 research',
                        'notes': 'The model card lists us-central1, output durations, aspect ratios, resolutions, and modality support. Price table distinguishes audio/video-only outputs.',
                    })
                    for w, _, _, price_table in ((workflows[0], 'text-to-video', '', rates), (workflows[1], 'image-to-video', '', rates)):
                        for audio_mode in ('native_audio', 'video_only'):
                            for resolution in resolution_values:
                                for aspect in ('16:9', '9:16'):
                                    for duration in ('4', '6', '8'):
                                        configuration = {'audio_mode': audio_mode, 'resolution': resolution,
                                                         'aspect_ratio': aspect, 'generation_duration_seconds': duration}
                                        self._get(ModelPricing, {'video_model': model, 'workflow': w,
                                                'access_route': route, 'method': ModelPricing.Method.FIXED_GENERATION,
                                                'configuration': configuration, 'effective_from': EFFECTIVE_FROM}, {
                                            'rate': Decimal(price_table[(audio_mode, resolution)]),
                                            'unit': ModelPricing.Unit.GENERATION, 'currency': 'USD',
                                            'is_active': True, 'verification_status': 'officially_documented',
                                            'source_url': SOURCES['google_cloud_prices'], 'checked_at': CHECKED_AT,
                                            'evidence_description': 'Official Google Cloud per-output-count price. The same published rate applies at each supported duration and aspect ratio.',
                                            'administrative_notes': f'Requires {route.name}; US endpoint; confirm the project quota, account billing currency, and taxes.',
                                        })

        eleven = self._provider('ElevenLabs', 'elevenlabs', 'Voice and audio platform', 'https://elevenlabs.io', [voice],
            'ElevenLabs publishes API text-to-speech rates per 1,000 characters.')
        eleven_api = self._offering(eleven, 'ElevenAPI', 'elevenapi', ProviderOffering.OfferingType.API,
            [voice], 'https://elevenlabs.io/pricing/api', SOURCES['elevenlabs_api'],
            'Developer API for speech synthesis. Voice is an optional production service, not a required video-generation charge.')
        for title, slug, rate in [('Text to Speech v3', 'elevenlabs-tts-v3', '0.10'),
                                  ('Text to Speech Flash/Turbo', 'elevenlabs-tts-flash-turbo', '0.05')]:
            tool = self._get(ProductionTool, {'slug': slug}, {
                'provider': eleven, 'offering': eleven_api, 'name': title,
                'kind': ProductionTool.Kind.METERED_SERVICE, 'activities': ['voice_narration'],
                'description': 'Optional externally invoked ElevenLabs TTS API service; the calculator makes no API call.',
                'is_active': True,
            })
            self._get(ProductionToolPricing, {'tool': tool, 'name': title + ' API usage',
                    'cost_type': ProductionToolPricing.CostType.USAGE,
                    'method': ProductionToolPricing.Method.PER_1000_UNITS, 'effective_from': EFFECTIVE_FROM}, {
                'rate': Decimal(rate), 'currency': 'USD', 'unit': 'characters', 'is_active': True,
                'verification_status': 'officially_documented', 'source_url': SOURCES['elevenlabs_api'],
                'checked_at': CHECKED_AT, 'evidence_description': f'Official published API rate: ${rate} per 1,000 characters.',
            })
        self.stdout.write('ElevenLabs tools attached to specialties: voice-narration, editing-finishing research pending.')

        # These US-listed subscriptions are retained for admin research, inactive
        # until regional checkout/pricing is captured for the customer location.
        canva = self._provider('Canva', 'canva', 'Design and editing platform', 'https://www.canva.com', [image, editing],
            'Canva supplies design, visual and video editing tools; prices and allowances vary by plan/region.')
        canva_offer = self._offering(canva, 'Canva', 'canva-web', ProviderOffering.OfferingType.SOFTWARE,
            [image, editing], 'https://www.canva.com', SOURCES['canva_plans'], 'Design and video finishing software.')
        self._plan(canva, canva_offer, 'Canva Pro (US annual list price)', 'canva-pro-us-annual', '144.00',
            SubscriptionPlan.Period.ANNUAL, SOURCES['canva_plans'],
            'US countryCode=us USD listing, $144/year. Regional and monthly checkout prices not inferred; inactive pending localized verification.', active=False)

        capcut = self._provider('CapCut', 'capcut', 'Video editing platform', 'https://www.capcut.com', [editing],
            'CapCut provides video editing and finishing software; official help states subscription pricing varies by region, device and promotions.')
        capcut_offer = self._offering(capcut, 'CapCut', 'capcut-app', ProviderOffering.OfferingType.SOFTWARE,
            [editing], 'https://www.capcut.com', SOURCES['capcut_plans'], 'Video editing and finishing software.')
        self._plan(capcut, capcut_offer, 'CapCut Pro (USD list price)', 'capcut-pro-us', '19.99',
            SubscriptionPlan.Period.MONTHLY, SOURCES['capcut_plans'],
            'Official page displays USD $19.99/month; official help says price varies by region, device and promotions. Inactive pending localized checkout verification.', active=False)

        # Kling's official site blocked automated source review; avoid creating a
        # catalogue row without a first-party-verifiable offering/pricing source.
        self.stdout.write('Research note: Kling AI omitted because current official pricing/capability pages were not verifiable in this run.')
