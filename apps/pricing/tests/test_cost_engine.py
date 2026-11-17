from decimal import Decimal
from unittest import TestCase

from apps.pricing.engines.production_cost import ProductionCostEngine


class ProductionCostEngineTests(TestCase):
    def setUp(self):
        self.engine = ProductionCostEngine()

    def component(self, method='fixed_generation', rate='0.50', currency='USD', **overrides):
        pricing = {'id': 'synthetic-rate', 'method': method, 'rate': rate, 'currency': currency,
                   'unit': 'generation' if 'generation' in method else 'second',
                   'failed_attempt_billing': 'billable', 'verification_status': 'independently_tested', 'evidence': []}
        pricing.update(overrides.pop('pricing', {}))
        return {'model': {'id': 'synthetic-model-v1', 'provider': 'Synthetic Lab', 'name': 'Sample', 'version': '1'},
                'workflow': {'slug': 'text-to-video'}, 'pricing': pricing,
                'duration_seconds': '5', 'generation_requests': 1, 'clip_count': 1,
                'retry_allowance': 0, **overrides}

    def calculate(self, components=None, **kwargs):
        return self.engine.calculate({'components': components or [self.component()], 'output_currency': 'USD', **kwargs})

    def test_fixed_generation_and_markup_profit_and_margin(self):
        result = self.calculate([self.component(generation_requests=2, clip_count=2)], markup_percentage='30')
        self.assertEqual(result['commercial']['base_production_cost'], '1.00')
        self.assertEqual(result['commercial']['suggested_selling_price'], '1.30')
        self.assertEqual(result['commercial']['gross_profit'], '0.30')
        self.assertEqual(result['commercial']['gross_margin_percentage'], '23.08')

    def test_complete_video_cost_includes_tool_allocations_overhead_and_cash_split(self):
        component = self.component(method='per_second', rate='0.40', duration_seconds='16', clip_count=1)
        tools = [
            {'id': 'chatgpt', 'name': 'ChatGPT Plus', 'activities': ['script'], 'subscription_pricing': {
                'rate': '20', 'currency': 'USD', 'allocation_method': 'monthly_projects', 'expected_monthly_projects': 20,
                'verification_status': 'independently_tested', 'evidence': []}, 'usage_quantity': '0'},
            {'id': 'capcut', 'name': 'CapCut Pro', 'activities': ['editing'], 'subscription_pricing': {
                'rate': '20', 'currency': 'USD', 'allocation_method': 'monthly_projects', 'expected_monthly_projects': 20,
                'verification_status': 'independently_tested', 'evidence': []}, 'usage_quantity': '0'},
        ]
        result = self.calculate([component], tools=tools, overheads=[{'category': 'electricity', 'name': 'Electricity', 'user_amount': '2'}],
            production={'desired_final_duration_seconds': '12', 'expected_usable_duration_seconds': '8'})
        self.assertEqual(result['commercial']['total_estimated_production_cost'], '10.40')
        self.assertEqual(result['commercial']['cost_per_finished_video'], '10.40')
        self.assertEqual(result['commercial']['additional_cash_expenditure'], '8.40')
        self.assertEqual(result['summary']['billable_generated_seconds'], '16')
        self.assertEqual(result['production_tool_costs'][0]['subscription_allocation'], '1.00')

    def test_native_audio_path_does_not_add_elevenlabs_unless_selected(self):
        native = self.calculate([self.component(method='per_second', rate='0.20', duration_seconds='16')],
            production={'desired_final_duration_seconds': '8', 'expected_usable_duration_seconds': '8'})
        self.assertEqual(native['commercial']['total_estimated_production_cost'], '3.20')
        self.assertEqual(native['production_tool_costs'], [])
        elevenlabs = {'id': 'elevenlabs', 'name': 'ElevenLabs', 'activities': ['voice_narration'], 'usage_quantity': '1000',
            'usage_pricing': {'method': 'per_1000_units', 'rate': '0.08', 'currency': 'USD', 'unit': 'characters',
                              'verification_status': 'officially_documented', 'evidence': []}}
        voiced = self.calculate([self.component(method='per_second', rate='0.20', duration_seconds='16')], tools=[elevenlabs],
            production={'desired_final_duration_seconds': '8', 'expected_usable_duration_seconds': '8'})
        self.assertEqual(voiced['commercial']['total_estimated_production_cost'], '3.28')

    def test_blank_included_allowance_uses_configured_plan_allowance(self):
        tool = {'id': 'tool', 'name': 'Synthetic subscription tool', 'usage_quantity': '150',
            'subscription_pricing': {'rate': '20', 'currency': 'USD', 'allocation_method': 'monthly_projects',
                'expected_monthly_projects': 20, 'included_quantity': '100', 'included_unit': 'credits'},
            'usage_pricing': {'method': 'per_unit', 'rate': '0.02', 'currency': 'USD', 'unit': 'credit'},
            'included_allowance_remaining': None}
        result = self.calculate(tools=[tool])
        line = result['production_tool_costs'][0]
        self.assertEqual(line['included_allowance_used'], '100')
        self.assertEqual(line['billable_usage_quantity'], '50')
        self.assertEqual(line['usage_cost'], '1.00')

    def test_missing_allowance_with_subscription_and_usage_is_incomplete(self):
        tool = {'id': 'tool', 'name': 'Synthetic tool', 'usage_quantity': '10',
            'subscription_pricing': {'rate': '20', 'currency': 'USD', 'allocation_method': 'monthly_projects',
                'expected_monthly_projects': 20},
            'usage_pricing': {'method': 'per_unit', 'rate': '0.02', 'currency': 'USD', 'unit': 'credit'}}
        result = self.calculate(tools=[tool])
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(any('allowance' in item.lower() for item in result['missing_information']))

    def test_per_second_minimum_and_billing_increment(self):
        result = self.calculate([self.component(method='per_second', rate='0.10', duration_seconds='4',
            pricing={'minimum_billable_seconds': '5', 'billing_increment_seconds': '2'})])
        self.assertEqual(result['commercial']['total_estimated_production_cost'], '0.60')
        self.assertEqual(result['model_costs'][0]['base_units'], '6')

    def test_credit_package_marginal_cash_and_subscription_allocation_are_distinct(self):
        component = self.component(method='credits_per_generation', rate='40', currency='CRD',
            pricing={'unit': 'generation'}, credit_packages=[{'id':'pack','credit_quantity':'100','price':'20','currency':'USD'}])
        result = self.calculate([component])
        self.assertEqual(result['model_costs'][0]['credits_consumed'], '40')
        self.assertEqual(result['model_costs'][0]['marginal_cash_cost'], '20')

    def test_subscription_balance_addon_and_allocated_economic_cost(self):
        component = self.component(method='credits_per_generation', rate='40', currency='CRD',
            pricing={'unit':'generation'}, credits_remaining='30',
            subscription_plan={'name':'Synthetic Plan','subscription_price':'20','currency':'USD','included_credits':'1000',
                               'additional_credit_quantity':'100','additional_credit_price':'3'},
            credit_cost_basis='allocated_economic')
        result = self.calculate([component])
        line = result['model_costs'][0]
        self.assertEqual(line['marginal_cash_cost'], '3')
        self.assertEqual(line['allocated_subscription_cost'], '0.8')
        self.assertEqual(result['commercial']['total_estimated_production_cost'], '0.80')

    def test_missing_subscription_balance_is_explicitly_incomplete(self):
        component = self.component(method='credits_per_generation', rate='40', currency='CRD', pricing={'unit':'generation'},
            subscription_plan={'name':'Synthetic Plan','subscription_price':'20','currency':'USD','included_credits':'1000'})
        result = self.calculate([component])
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['commercial']['suggested_selling_price'])
        self.assertTrue(any('Remaining credit balance' in item for item in result['missing_information']))

    def test_currency_conversion_uses_decimal_exchange_rate(self):
        result = self.engine.calculate({'components':[self.component()], 'output_currency':'NGN',
            'exchange_rates':[{'id':'fx','base_currency':'USD','quote_currency':'NGN','rate':'1500',
                               'effective_at':'2026-11-15T00:00:00+00:00','verification_status':'independently_tested'}],
            'as_of':'2026-11-15T12:00:00+00:00'})
        self.assertEqual(result['commercial']['total_estimated_production_cost'], '750.00')
        self.assertEqual(result['model_costs'][0]['exchange_rate']['rate'], '1500')

    def test_missing_and_stale_exchange_rates_make_estimate_incomplete(self):
        missing = self.engine.calculate({'components':[self.component()], 'output_currency':'EUR'})
        self.assertEqual(missing['status'], 'incomplete')
        stale = self.engine.calculate({'components':[self.component()], 'output_currency':'NGN',
            'as_of':'2026-11-15T00:00:00+00:00', 'max_exchange_rate_age_days':7,
            'exchange_rates':[{'id':'old','base_currency':'USD','quote_currency':'NGN','rate':'1500',
                               'effective_at':'2026-11-01T00:00:00+00:00'}]})
        self.assertEqual(stale['status'], 'incomplete')

    def test_retry_allowance_is_separately_costed_when_failed_attempts_billable(self):
        result = self.calculate([self.component(retry_allowance=2)])
        self.assertEqual(result['commercial']['base_production_cost'], '0.50')
        self.assertEqual(result['commercial']['retry_allowance_cost'], '1.00')
        self.assertEqual(result['commercial']['total_estimated_production_cost'], '1.50')

    def test_unknown_failed_attempt_billing_does_not_assume_retries_are_free_or_billable(self):
        result = self.calculate([self.component(retry_allowance=2, pricing={'failed_attempt_billing':'unknown'})])
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['known_partial_subtotal'], '0.50')
        self.assertIsNone(result['model_costs'][0]['retry_output_cost'])

    def test_actual_failed_attempts_follow_configured_billing(self):
        result = self.calculate([self.component(pricing={'rate':'0.25'}, actual_attempts=4, successful_attempts=2, failed_attempts=2)])
        self.assertEqual(result['commercial']['base_production_cost'], '0.50')
        self.assertEqual(result['commercial']['retry_allowance_cost'], '0.50')
        with self.assertRaises(ValueError):
            self.calculate([self.component(actual_attempts=3, successful_attempts=2, failed_attempts=0)])

    def test_operations_multiple_models_and_target_margin(self):
        second = self.component(method='per_second', rate='0.10', duration_seconds='10',
                                model={'id':'synthetic-model-v2','provider':'Synthetic Lab','name':'Sample','version':'2'})
        result = self.engine.calculate({'components':[self.component(), second], 'output_currency':'USD',
            'operations':[{'operation_key':'tts','quantity':'1000','operation_requests':1,'retry_allowance':0,
                           'pricing':{'id':'tts','method':'per_unit','rate':'0.002','currency':'USD','unit':'character',
                                      'failed_attempt_billing':'billable','verification_status':'calculated_or_derived'}}],
            'target_margin_percentage':'50'})
        self.assertEqual(result['summary']['model_version_count'], 2)
        self.assertEqual(result['commercial']['base_production_cost'], '3.50')
        self.assertEqual(result['commercial']['suggested_selling_price'], '7.00')
        self.assertEqual(result['commercial']['gross_margin_percentage'], '50.00')
        self.assertEqual(result['operation_costs'][0]['known_cost'], '2.000')

    def test_missing_price_and_missing_operation_are_not_zero_cost(self):
        result = self.engine.calculate({'components':[{'model':{'name':'Missing','version':'1'},'duration_seconds':'5','pricing':None}],
            'operations':[{'operation_key':'missing-tts','quantity':'10','pricing':None}], 'output_currency':'USD'})
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(len(result['missing_information']), 2)
        self.assertIsNone(result['commercial']['suggested_selling_price'])

    def test_target_margin_validation_and_decimal_input(self):
        with self.assertRaises(ValueError):
            self.calculate(target_margin_percentage='100')
        with self.assertRaises(ValueError):
            self.calculate(markup_percentage='10', target_margin_percentage='20')
        with self.assertRaises(ValueError):
            self.calculate([self.component(rate=0.50)])
        self.assertEqual(self.calculate([self.component(rate=Decimal('0.50'))])['commercial']['base_production_cost'], '0.50')

