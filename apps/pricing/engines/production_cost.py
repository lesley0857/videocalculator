"""Deterministic cost calculations; accepts validated, database-free snapshots."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from typing import Any

from apps.calculators.engines.base import BaseCalculationEngine

ZERO = Decimal('0')
ONE = Decimal('1')
CENT = Decimal('0.01')


def decimal_value(value: Any, name: str, *, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f'{name} must be supplied as a decimal-safe string or number.')
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{name} must be a valid decimal value.')
    if not result.is_finite() or (minimum is not None and result < minimum):
        raise ValueError(f'{name} must be at least {minimum}.' if minimum is not None else f'{name} must be finite.')
    return result


def _amount(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


class ProductionCostEngine(BaseCalculationEngine):
    """Calculate model, credit, operation, retry, FX and commercial totals.

    Input is a normalized mapping containing `components`, optional `operations`,
    `exchange_rates`, `output_currency`, and markup or target-margin data. Prices
    and identities arrive as snapshots created by the pricing service.
    """

    def calculate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(inputs, dict):
            raise ValueError('Calculation input must be an object.')
        output_currency = inputs.get('output_currency')
        if not isinstance(output_currency, str) or len(output_currency) != 3 or not output_currency.isalpha() or output_currency != output_currency.upper():
            raise ValueError('output_currency must be a three-letter uppercase currency code.')
        components = inputs.get('components')
        operations = inputs.get('operations', [])
        if not isinstance(components, list) or not components:
            raise ValueError('At least one model component is required.')
        if not isinstance(operations, list):
            raise ValueError('operations must be a list.')

        rates = inputs.get('exchange_rates', [])
        if not isinstance(rates, list):
            raise ValueError('exchange_rates must be a list.')
        as_of = inputs.get('as_of')
        max_rate_age = self._integer(inputs.get('max_exchange_rate_age_days', 7), 'max_exchange_rate_age_days', 0)
        warnings: list[str] = []
        missing: list[str] = []
        assumptions: list[str] = []
        model_lines = []
        operation_lines = []
        base_total = ZERO
        retry_total = ZERO
        known_subtotal = ZERO
        credits_consumed = ZERO
        clips_count = 0
        total_duration = ZERO
        generation_requests = 0
        model_ids: set[str] = set()
        credit_basis = inputs.get('credit_cost_basis', 'marginal_cash')
        if credit_basis not in ('marginal_cash', 'allocated_economic'):
            raise ValueError('credit_cost_basis must be marginal_cash or allocated_economic.')

        for index, component in enumerate(components):
            if not isinstance(component, dict):
                raise ValueError(f'components[{index}] must be an object.')
            duration = decimal_value(component.get('duration_seconds'), f'components[{index}].duration_seconds', minimum=ZERO)
            requests = self._integer(component.get('generation_requests', 1), f'components[{index}].generation_requests', minimum=1)
            retries = self._integer(component.get('retry_allowance', 0), f'components[{index}].retry_allowance', minimum=0)
            clips = self._integer(component.get('clip_count', requests), f'components[{index}].clip_count', minimum=1)
            clips_count += clips
            exact_clip_durations = component.get('clip_durations_seconds')
            if exact_clip_durations is not None:
                if not isinstance(exact_clip_durations, list) or len(exact_clip_durations) != requests or not exact_clip_durations:
                    raise ValueError(f'components[{index}].clip_durations_seconds must contain one duration per generation request.')
                total_duration += sum((decimal_value(value, f'components[{index}].clip_durations_seconds', minimum=Decimal('0.001')) for value in exact_clip_durations), ZERO)
            else:
                total_duration += duration * requests
            generation_requests += requests
            model = component.get('model', {})
            model_ids.add(str(model.get('id', 'unknown')))
            pricing = component.get('pricing')
            if not pricing:
                missing.append(f'Model pricing is missing for {model.get("name", "selected model")} version {model.get("version", "unknown")}.')
                model_lines.append({'model': model, 'workflow': component.get('workflow'), 'pricing': None, 'status': 'unpriced'})
                continue
            line = self._model_line(component, pricing, output_currency, rates, as_of, max_rate_age, missing, warnings)
            model_lines.append(line)
            if line.get('attempts_expected_or_actual', 0) > 3:
                warnings.append(f'Model component {index + 1} reaches more than three generation attempts.')
            if line.get('known_cost') is not None:
                base_total += decimal_value(line['base_output_cost'], 'base_output_cost', minimum=ZERO)
                if line.get('retry_output_cost') is not None:
                    retry_total += decimal_value(line['retry_output_cost'], 'retry_output_cost', minimum=ZERO)
                known_subtotal += decimal_value(line['known_cost'], 'known_cost', minimum=ZERO)
            credits_consumed += decimal_value(line.get('credits_consumed', '0'), 'credits_consumed', minimum=ZERO)

        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                raise ValueError(f'operations[{index}] must be an object.')
            quantity = decimal_value(operation.get('quantity'), f'operations[{index}].quantity', minimum=ZERO)
            pricing = operation.get('pricing')
            if not pricing:
                missing.append(f'Operation pricing is missing for {operation.get("label", operation.get("operation_key", "selected operation"))}.')
                operation_lines.append({'operation': operation.get('operation_key'), 'quantity': str(quantity), 'pricing': None, 'status': 'unpriced'})
                continue
            line = self._operation_line(operation, pricing, output_currency, rates, as_of, max_rate_age, missing, warnings)
            operation_lines.append(line)
            if line.get('attempts_expected_or_actual', 0) > 3:
                warnings.append(f'Operation {operation.get("operation_key")} reaches more than three attempts.')
            if line.get('known_cost') is not None:
                base_total += decimal_value(line['base_output_cost'], 'base_output_cost', minimum=ZERO)
                if line.get('retry_output_cost') is not None:
                    retry_total += decimal_value(line['retry_output_cost'], 'retry_output_cost', minimum=ZERO)
                known_subtotal += decimal_value(line['known_cost'], 'known_cost', minimum=ZERO)

        clips_count = sum(self._integer(item.get('clip_count', 1), 'clip_count', 1) for item in components)
        total_duration = sum((sum((decimal_value(value, 'clip duration', minimum=Decimal('0.001')) for value in item['clip_durations_seconds']), ZERO) if item.get('clip_durations_seconds') else decimal_value(item.get('duration_seconds', '0'), 'duration_seconds', minimum=ZERO) * self._integer(item.get('generation_requests', 1), 'generation_requests', 1) for item in components), ZERO)
        project_hours = decimal_value(inputs.get('project_hours', '0'), 'project_hours', minimum=ZERO)
        production = inputs.get('production', {})
        final_duration = decimal_value(production.get('desired_final_duration_seconds', '0'), 'desired_final_duration_seconds', minimum=ZERO)
        expected_usable = decimal_value(production.get('expected_usable_duration_seconds', final_duration), 'expected_usable_duration_seconds', minimum=ZERO)
        if final_duration and expected_usable > final_duration:
            raise ValueError('Expected usable duration cannot exceed the desired final video duration.')
        direct_cost = base_total + retry_total
        tool_lines, overhead_lines = [], []
        tool_economic_total = tool_cash_total = overhead_total = ZERO
        for index, tool in enumerate(inputs.get('tools', [])):
            line = self._production_tool_line(tool, output_currency, rates, as_of, max_rate_age, project_hours, missing)
            tool_lines.append(line)
            if line.get('known_cost') is not None:
                amount = decimal_value(line['known_cost'], f'tools[{index}].known_cost', minimum=ZERO)
                tool_economic_total += amount
                known_subtotal += amount
            if line.get('additional_cash_cost') is not None:
                tool_cash_total += decimal_value(line['additional_cash_cost'], f'tools[{index}].additional_cash_cost', minimum=ZERO)
        for index, overhead in enumerate(inputs.get('overheads', [])):
            line = self._overhead_line(overhead, output_currency, rates, as_of, max_rate_age,
                                       direct_cost + tool_economic_total, clips_count, final_duration,
                                       project_hours, missing)
            overhead_lines.append(line)
            if line.get('known_cost') is not None:
                amount = decimal_value(line['known_cost'], f'overheads[{index}].known_cost', minimum=ZERO)
                overhead_total += amount
                known_subtotal += amount

        complete = not missing
        production_cost = base_total + retry_total + tool_economic_total + overhead_total
        commercial = self._commercial(base_total + tool_economic_total + overhead_total, retry_total, inputs, output_currency, complete, missing)
        model_cash_total = ZERO
        for line in model_lines:
            cash_value = line.get('marginal_cash_cost') if line.get('marginal_cash_cost') is not None else line.get('known_cost')
            if cash_value is not None:
                model_cash_total += decimal_value(cash_value, 'model cash cost', minimum=ZERO)
        operation_cash_total = sum((decimal_value(line['known_cost'], 'operation cash cost', minimum=ZERO) for line in operation_lines if line.get('known_cost') is not None), ZERO)
        overhead_cash_total = sum((decimal_value(line['cash_cost'], 'overhead cash cost', minimum=ZERO) for line in overhead_lines if line.get('cash_cost') is not None), ZERO)
        additional_cash = model_cash_total + operation_cash_total + tool_cash_total + overhead_cash_total
        commercial.update({
            'ai_provider_cost': _amount(sum((decimal_value(line['known_cost'], 'model known cost', minimum=ZERO) for line in model_lines if line.get('known_cost') is not None), ZERO)),
            'optional_service_cost': _amount(operation_cash_total),
            'production_tool_cost': _amount(tool_economic_total),
            'production_overhead_cost': _amount(overhead_total),
            'direct_production_cost': _amount(base_total + retry_total + tool_economic_total),
            'additional_cash_expenditure': _amount(additional_cash),
            'cost_per_finished_video': _amount(production_cost) if complete else None,
            'cost_per_finished_video_second': _amount(production_cost / final_duration) if complete and final_duration > ZERO else None,
        })
        if not complete:
            commercial.update({'total_estimated_production_cost': None, 'suggested_selling_price': None,
                               'gross_profit': None, 'gross_margin_percentage': None,
                               'known_partial_cost': _amount(known_subtotal)})
        if any(line.get('verification_status') not in (None, 'officially_documented', 'independently_tested') for line in model_lines + operation_lines + tool_lines + overhead_lines):
            warnings.append('One or more prices are derived, unverified, or unavailable; verify evidence before treating this estimate as a quote.')
        if any(line.get('billing_uncertain') for line in model_lines + operation_lines):
            warnings.append('Billing for one or more failed attempts is unknown; the retry estimate is incomplete.')
        if any((line.get('exchange_rate') or {}).get('verification_status') in ('unverified', 'not_available') for line in model_lines + operation_lines):
            warnings.append('One or more exchange rates are unverified.')
        return {
            'status': 'complete' if complete else 'incomplete',
            'output_currency': output_currency,
            'summary': {
                'clip_count': clips_count,
                'model_version_count': len(model_ids),
                'operation_count': len(operation_lines),
                'billable_duration_seconds': str(total_duration),
                'generation_requests': generation_requests,
                'credits_consumed': str(credits_consumed),
                'desired_final_duration_seconds': str(final_duration) if final_duration else None,
                'expected_usable_duration_seconds': str(expected_usable) if final_duration else None,
                'billable_generated_seconds': str(total_duration),
            },
            'model_costs': model_lines,
            'operation_costs': operation_lines,
            'production_tool_costs': tool_lines,
            'production_overheads': overhead_lines,
            'credit_cost_basis': inputs.get('credit_cost_basis', 'marginal_cash'),
            'commercial': commercial,
            'known_partial_subtotal': _amount(known_subtotal),
            'missing_information': missing,
            'warnings': sorted(set(warnings)),
            'assumptions': assumptions,
            'rounding': 'Final monetary values are rounded to 0.01 using ROUND_HALF_UP; intermediate Decimal calculations are not rounded.',
        }

    @staticmethod
    def _integer(value, name, minimum):
        if isinstance(value, bool):
            raise ValueError(f'{name} must be an integer.')
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError(f'{name} must be an integer.')
        if str(number) != str(value) and not isinstance(value, int):
            raise ValueError(f'{name} must be a whole number.')
        if number < minimum:
            raise ValueError(f'{name} must be at least {minimum}.')
        return number

    def _fx(self, amount, source, target, rates, as_of, max_age, missing, missing_key):
        if source == target:
            return amount, {'rate': '1', 'base_currency': source, 'quote_currency': target, 'exchange_rate_id': None}
        candidates = []
        for rate in rates:
            if rate.get('base_currency') == source and rate.get('quote_currency') == target:
                candidates.append((0, decimal_value(rate['rate'], 'exchange rate', minimum=ZERO), rate))
            elif rate.get('base_currency') == target and rate.get('quote_currency') == source:
                candidates.append((1, ONE / decimal_value(rate['rate'], 'exchange rate', minimum=ZERO), rate))
        if not candidates:
            missing.append(f'No exchange rate is available for {source} to {target} as of {as_of or "the estimate date"}.')
            return None, None
        _, rate_value, record = sorted(candidates, key=lambda item: item[0])[0]
        if as_of and record.get('effective_at') and max_age >= 0:
            from datetime import datetime
            parsed_asof = datetime.fromisoformat(as_of.replace('Z', '+00:00'))
            parsed_rate = datetime.fromisoformat(record['effective_at'].replace('Z', '+00:00'))
            if (parsed_asof - parsed_rate).days > max_age:
                missing.append(f'Exchange rate {record.get("id")} is stale for {source} to {target}.')
                return None, None
        return amount * rate_value, {'rate': str(rate_value), 'base_currency': source, 'quote_currency': target,
                                    'exchange_rate_id': record.get('id'), 'effective_at': record.get('effective_at'),
                                    'verification_status': record.get('verification_status')}

    @staticmethod
    def _billed_seconds(duration, pricing):
        minimum = decimal_value(pricing.get('minimum_billable_seconds') or '0', 'minimum_billable_seconds', minimum=ZERO)
        increment = pricing.get('billing_increment_seconds')
        billed = max(duration, minimum)
        if increment:
            step = decimal_value(increment, 'billing_increment_seconds', minimum=ZERO)
            billed = (billed / step).to_integral_value(rounding=ROUND_CEILING) * step
        return billed

    @staticmethod
    def _attempt_counts(component, requests, retries, pricing, missing):
        billing = pricing.get('failed_attempt_billing', 'unknown')
        if 'actual_attempts' in component:
            actual = ProductionCostEngine._integer(component['actual_attempts'], 'actual_attempts', 1)
            successes = ProductionCostEngine._integer(component.get('successful_attempts'), 'successful_attempts', 0)
            failures = ProductionCostEngine._integer(component.get('failed_attempts'), 'failed_attempts', 0)
            if successes + failures != actual:
                raise ValueError('successful_attempts plus failed_attempts must equal actual_attempts.')
            if billing == 'billable':
                return successes + failures, successes, failures, actual
            if billing == 'free':
                return successes, successes, 0, actual
            if failures:
                missing.append('Failed-attempt billing is unknown; actual failed-attempt charges cannot be priced.')
            return successes, successes, 0, actual
        expected = requests * (1 + retries)
        if billing == 'billable':
            return expected, requests, expected - requests, expected
        if billing == 'free':
            return requests, requests, 0, expected
        if retries:
            missing.append('Failed-attempt billing is unknown; retry allowance cannot be fully priced.')
        return requests, requests, 0, expected

    def _model_line(self, component, pricing, output, rates, as_of, max_age, missing, warnings):
        model = component.get('model', {})
        requests = self._integer(component.get('generation_requests', 1), 'generation_requests', 1)
        retries = self._integer(component.get('retry_allowance', 0), 'retry_allowance', 0)
        duration = decimal_value(component['duration_seconds'], 'duration_seconds', minimum=ZERO)
        exact_clip_durations = component.get('clip_durations_seconds')
        billable, base_attempts, retry_attempts, attempts = self._attempt_counts(component, requests, retries, pricing, missing)
        method = pricing['method']
        rate = decimal_value(pricing['rate'], 'pricing rate', minimum=Decimal('0.000000000000000001'))
        if method in ('fixed_generation', 'credits_per_generation'):
            base_units, retry_units = Decimal(base_attempts), Decimal(retry_attempts)
        elif method in ('per_second', 'credits_per_second'):
            if exact_clip_durations is not None:
                if base_attempts != requests:
                    raise ValueError('Exact clip pricing with observed attempts requires failed clip identifiers.')
                base_units = sum((self._billed_seconds(decimal_value(value, 'clip duration', minimum=Decimal('0.001')), pricing) for value in exact_clip_durations), ZERO)
                retry_units = self._billed_seconds(sum((decimal_value(value, 'clip duration', minimum=Decimal('0.001')) for value in exact_clip_durations), ZERO) / Decimal(requests), pricing) * retry_attempts
            else:
                seconds = self._billed_seconds(duration, pricing)
                base_units, retry_units = seconds * base_attempts, seconds * retry_attempts
        else:
            missing.append(f'Unsupported model pricing method {method}.')
            return {'model': model, 'workflow': component.get('workflow'), 'pricing_method': method, 'status': 'unpriced', 'known_cost': None}
        credit = method.startswith('credits_')
        base_native, retry_native = rate * base_units, rate * retry_units
        currency = pricing['currency']
        detail = {
            'model': model, 'workflow': component.get('workflow'), 'pricing_id': pricing.get('id'),
            'model_family': model.get('family'), 'specialty': component.get('specialty'),
            'offering': component.get('offering'), 'access_route': component.get('access_route'),
            'configuration': component.get('configuration', {}),
            'pricing_snapshot': pricing,
            'subscription_plan_snapshot': component.get('subscription_plan'),
            'clip_durations_seconds': exact_clip_durations,
            'retry_duration_basis': 'average_clip_duration' if exact_clip_durations and retry_attempts else None,
            'pricing_method': method, 'unit': pricing.get('unit'), 'unit_rate': str(rate),
            'currency': currency, 'base_units': str(base_units), 'retry_units': str(retry_units),
            'attempts_expected_or_actual': attempts, 'billable_attempts': billable,
            'verification_status': pricing.get('verification_status'), 'evidence': pricing.get('evidence', []),
        }
        if credit:
            credits = base_native + retry_native
            detail.update(self._credit_cost(component, pricing, base_native, retry_native, output, rates, as_of, max_age, missing, warnings))
            detail['credits_consumed'] = str(credits)
            return detail
        base_out, fx = self._fx(base_native, currency, output, rates, as_of, max_age, missing, 'model')
        retry_out, retry_fx = self._fx(retry_native, currency, output, rates, as_of, max_age, missing, 'model retry') if retry_native else (ZERO, fx)
        has_failed_attempts = (component.get('failed_attempts', 0) or 0) > 0 if 'actual_attempts' in component else retries > 0
        if pricing.get('failed_attempt_billing') == 'unknown' and has_failed_attempts:
            retry_out = None
        if pricing.get('verification_status') == 'not_available':
            missing.append(f'Pricing is marked not available for {model.get("name")} version {model.get("version")}.' )
            return {**detail, 'status': 'incomplete', 'known_cost': None, 'exchange_rate': fx}
        if base_out is None:
            return {**detail, 'status': 'incomplete', 'known_cost': None, 'exchange_rate': fx}
        total = base_out + retry_out if retry_out is not None else base_out
        detail.update({'base_output_cost': str(base_out), 'retry_output_cost': str(retry_out) if retry_out is not None else None,
                       'original_base_cost': str(base_native), 'original_retry_cost': str(retry_native) if retry_out is not None else None,
                       'original_currency': currency,
                       'known_cost': str(total), 'exchange_rate': fx or retry_fx,
                       'status': 'priced' if retry_out is not None else 'incomplete'})
        if billable != attempts:
            warnings.append('Some failed attempts were configured as non-billable.')
        return detail

    def _credit_cost(self, component, pricing, base_credits, retry_credits, output, rates, as_of, max_age, missing, warnings):
        basis = component.get('credit_cost_basis', 'marginal_cash')
        if basis not in ('marginal_cash', 'allocated_economic'):
            raise ValueError('credit_cost_basis must be marginal_cash or allocated_economic.')
        plan = component.get('subscription_plan')
        balance_value = component.get('credits_remaining')
        total_credits = base_credits + retry_credits
        allocated_base = allocated_retry = None
        if plan:
            plan_price = decimal_value(plan['subscription_price'], 'subscription_price', minimum=ZERO)
            if plan.get('included_credits') in (None, ''):
                missing.append(f'Subscription plan {plan["name"]} has no configured credit allowance for credit-priced usage.')
                allocated_currency = plan['currency']
            else:
                plan_credits = decimal_value(plan['included_credits'], 'included_credits', minimum=Decimal('0.0001'))
                allocated_base = base_credits * plan_price / plan_credits
                allocated_retry = retry_credits * plan_price / plan_credits
                allocated_currency = plan['currency']
            if balance_value is None:
                missing.append(f'Remaining credit balance is required to calculate marginal cash cost for plan {plan["name"]}.')
                cash_base = cash_total = None
            else:
                balance = decimal_value(balance_value, 'credits_remaining', minimum=ZERO)
                cash_base = self._purchase_cost(max(ZERO, base_credits - balance), component, plan, output, rates, as_of, max_age, missing)
                cash_total = self._purchase_cost(max(ZERO, total_credits - balance), component, plan, output, rates, as_of, max_age, missing)
        else:
            allocated_currency = None
            packages = component.get('credit_packages') or []
            if not packages:
                missing.append('Credit usage has no applicable subscription plan or credit package for monetary valuation.')
                cash_base = cash_total = None
            else:
                cash_base = self._purchase_cost(base_credits, component, None, output, rates, as_of, max_age, missing)
                cash_total = self._purchase_cost(total_credits, component, None, output, rates, as_of, max_age, missing)
        allocated_base_out = allocated_retry_out = None
        if plan and allocated_base is not None:
            allocated_base_out, _ = self._fx(allocated_base, allocated_currency, output, rates, as_of, max_age, missing, 'allocated subscription cost')
            allocated_total_out, _ = self._fx(allocated_base + allocated_retry, allocated_currency, output, rates, as_of, max_age, missing, 'allocated subscription cost')
            if allocated_base_out is not None and allocated_total_out is not None:
                allocated_retry_out = allocated_total_out - allocated_base_out
        if basis == 'allocated_economic':
            if not plan:
                missing.append('Allocated subscription cost requires a subscription plan.')
            base_out, retry_out = allocated_base_out, allocated_retry_out
        else:
            base_out = cash_base
            retry_out = (cash_total - cash_base) if cash_base is not None and cash_total is not None else None
        if base_out is None or retry_out is None:
            return {'credit_cost_basis': basis, 'marginal_cash_cost': str(cash_total) if cash_total is not None else None,
                    'allocated_subscription_cost': str(allocated_base + allocated_retry) if allocated_base is not None else None,
                    'base_output_cost': str(base_out) if base_out is not None else '0',
                    'retry_output_cost': str(retry_out) if retry_out is not None else '0',
                    'known_cost': '0', 'status': 'incomplete', 'subscription_plan': plan and plan.get('name'),
                    'credits_remaining': str(balance_value) if balance_value is not None else None}
        return {'credit_cost_basis': basis, 'marginal_cash_cost': str(cash_total) if cash_total is not None else None,
                'allocated_subscription_cost': str(allocated_base_out + allocated_retry_out) if allocated_base_out is not None else None,
                'base_output_cost': str(base_out), 'retry_output_cost': str(retry_out),
                'known_cost': str(base_out + retry_out), 'status': 'priced',
                'subscription_plan': plan and plan.get('name'), 'included_credits': plan and plan.get('included_credits'),
                'credits_remaining': str(balance_value) if balance_value is not None else None,
                'additional_credits_required': str(max(ZERO, total_credits - decimal_value(balance_value, 'credits_remaining', minimum=ZERO))) if balance_value is not None else None}

    def _purchase_cost(self, credits, component, plan, output, rates, as_of, max_age, missing):
        if credits <= 0:
            return ZERO
        if plan and plan.get('additional_credit_quantity') and plan.get('additional_credit_price'):
            package_qty = decimal_value(plan['additional_credit_quantity'], 'additional_credit_quantity', minimum=Decimal('0.0001'))
            package_price = decimal_value(plan['additional_credit_price'], 'additional_credit_price', minimum=ZERO)
            packages = (credits / package_qty).to_integral_value(rounding=ROUND_CEILING)
            native = package_price * packages
            result, _ = self._fx(native, plan['currency'], output, rates, as_of, max_age, missing, 'additional subscription credits')
            return result
        packages = component.get('credit_packages') or []
        if not packages:
            missing.append('Additional credits are required but no credit package/add-on price is available.')
            return None
        choices = []
        for package in packages:
            qty = decimal_value(package['credit_quantity'], 'credit_quantity', minimum=Decimal('0.0001'))
            price = decimal_value(package['price'], 'credit package price', minimum=ZERO)
            count = (credits / qty).to_integral_value(rounding=ROUND_CEILING)
            native = price * count
            converted, fx = self._fx(native, package['currency'], output, rates, as_of, max_age, missing, 'credit package')
            if converted is not None:
                choices.append((converted, package, count, fx))
        if not choices:
            return None
        choices.sort(key=lambda item: (item[0], item[1].get('id', '')))
        return choices[0][0]

    def _operation_line(self, operation, pricing, output, rates, as_of, max_age, missing, warnings):
        quantity = decimal_value(operation['quantity'], 'operation quantity', minimum=Decimal('0.000000000000000001'))
        operation_requests = self._integer(operation.get('operation_requests', 1), 'operation_requests', 1)
        attempts, base_attempts, retry_attempts, total_attempts = self._attempt_counts(operation, operation_requests, self._integer(operation.get('retry_allowance', 0), 'operation retry_allowance', 0), pricing, missing)
        method = pricing['method']
        rate = decimal_value(pricing['rate'], 'operation rate', minimum=Decimal('0.000000000000000001'))
        unit_quantity = quantity
        if method == 'per_second':
            unit_quantity = decimal_value(operation.get('duration_seconds', quantity), 'operation duration', minimum=ZERO)
        if method not in ('fixed', 'per_unit', 'per_second'):
            missing.append(f'Unsupported operation method {method}.')
            return {'operation': operation.get('operation_key'), 'status': 'unpriced', 'known_cost': None}
        base_native = rate * unit_quantity * base_attempts
        retry_native = rate * unit_quantity * retry_attempts
        base_out, fx = self._fx(base_native, pricing['currency'], output, rates, as_of, max_age, missing, 'operation')
        retry_out, retry_fx = self._fx(retry_native, pricing['currency'], output, rates, as_of, max_age, missing, 'operation retry') if retry_native else (ZERO, fx)
        has_failed_attempts = (operation.get('failed_attempts', 0) or 0) > 0 if 'actual_attempts' in operation else operation.get('retry_allowance', 0) > 0
        if pricing.get('failed_attempt_billing') == 'unknown' and has_failed_attempts:
            retry_out = None
        total = (base_out + retry_out) if base_out is not None and retry_out is not None else base_out
        if attempts != total_attempts:
            warnings.append('Some operation failed attempts were configured as non-billable.')
        if pricing.get('verification_status') == 'not_available':
            missing.append(f'Pricing is marked not available for operation {operation.get("operation_key")}.' )
            return {'operation': operation.get('operation_key'), 'status': 'unpriced', 'known_cost': None}
        return {'operation': operation.get('operation_key'), 'label': pricing.get('label'), 'pricing_id': pricing.get('id'),
                'method': method, 'quantity': str(unit_quantity), 'unit': pricing.get('unit'), 'unit_rate': str(rate),
                'currency': pricing['currency'], 'base_output_cost': str(base_out) if base_out is not None else '0',
                'retry_output_cost': str(retry_out) if retry_out is not None else None, 'known_cost': str(total) if total is not None else None,
                'original_base_cost': str(base_native), 'original_retry_cost': str(retry_native) if retry_out is not None else None,
                'original_currency': pricing['currency'],
                'verification_status': pricing.get('verification_status'), 'evidence': pricing.get('evidence', []),
                'attempts_expected_or_actual': total_attempts, 'billable_attempts': attempts, 'exchange_rate': fx or retry_fx,
                'status': 'priced' if total is not None and retry_out is not None else 'incomplete'}

    def _production_tool_line(self, tool, output, rates, as_of, max_age, project_hours, missing):
        missing_start = len(missing)
        subscription = tool.get('subscription_pricing')
        usage = tool.get('usage_pricing')
        economic = cash = subscription_allocation = usage_cost = ZERO
        fx_details = []
        if subscription:
            monthly = decimal_value(subscription['rate'], 'subscription rate', minimum=ZERO)
            method = subscription.get('allocation_method')
            if method == 'monthly_projects':
                projects = decimal_value(tool.get('expected_monthly_projects') or subscription.get('expected_monthly_projects'), 'expected_monthly_projects', minimum=Decimal('1'))
                allocated = monthly / projects
            elif method == 'monthly_hours':
                denominator = decimal_value(tool.get('expected_monthly_hours') or subscription.get('expected_monthly_hours'), 'expected_monthly_hours', minimum=Decimal('0.0001'))
                if project_hours <= ZERO:
                    missing.append(f'Project production hours are required to allocate {tool.get("name")} subscription cost.')
                    allocated = ZERO
                else:
                    allocated = monthly * project_hours / denominator
            elif method == 'manual':
                allocated = decimal_value(tool.get('manual_allocation'), 'manual_allocation', minimum=ZERO)
            else:
                missing.append(f'Subscription allocation method is missing for {tool.get("name")}.')
                allocated = ZERO
            converted, fx = self._fx(allocated, subscription['currency'], output, rates, as_of, max_age, missing, 'production tool subscription allocation')
            if converted is not None:
                subscription_allocation = converted
                economic += converted
                fx_details.append(fx)
            if tool.get('subscription_purchased_for_project'):
                purchase_amount = decimal_value(subscription.get('cash_price', subscription['rate']), 'subscription cash price', minimum=ZERO)
                purchase, purchase_fx = self._fx(purchase_amount, subscription['currency'], output, rates, as_of, max_age, missing, 'production tool subscription purchase')
                if purchase is not None:
                    cash += purchase
                    fx_details.append(purchase_fx)
        quantity = decimal_value(tool.get('usage_quantity', '0'), 'tool usage quantity', minimum=ZERO)
        allowance_value = tool.get('included_allowance_remaining')
        if allowance_value in (None, ''):
            allowance_value = (subscription.get('included_quantity') or subscription.get('included_credits')) if subscription else None
        if allowance_value in (None, ''):
            if subscription and usage:
                missing.append(f'Included allowance is not configured for {tool.get("name")}; enter the remaining allowance or configure the plan.')
            allowance_value = '0'
        included = decimal_value(allowance_value, 'included_allowance_remaining', minimum=ZERO)
        billable_quantity = max(ZERO, quantity - included)
        if usage:
            rate = decimal_value(usage['rate'], 'tool usage rate', minimum=ZERO)
            method = usage.get('method')
            if method == 'per_1000_units':
                native_usage = rate * billable_quantity / Decimal('1000')
            elif method == 'per_unit':
                native_usage = rate * billable_quantity
            elif method == 'fixed_project':
                native_usage = rate if billable_quantity or not subscription else ZERO
            else:
                raise ValueError(f'Unsupported production-tool pricing method {method}.')
            converted, fx = self._fx(native_usage, usage['currency'], output, rates, as_of, max_age, missing, 'production tool usage')
            if converted is not None:
                usage_cost = converted
                economic += converted
                cash += converted
                fx_details.append(fx)
        elif billable_quantity > ZERO:
            missing.append(f'Additional usage pricing is missing for {tool.get("name")} above its included allowance.')
        if not subscription and not usage:
            missing.append(f'No effective subscription or usage pricing is selected for {tool.get("name")}.' )
        verification = [item.get('verification_status') for item in (subscription, usage) if item]
        verification_status = 'unverified' if any(value not in ('officially_documented', 'independently_tested') for value in verification) else (verification[0] if verification else None)
        return {'tool_id': tool.get('id'), 'provider': tool.get('provider'), 'name': tool.get('name'),
                'activities': tool.get('activities', []), 'status': 'incomplete' if len(missing) > missing_start else 'priced',
                'offering': tool.get('offering'), 'specialty': tool.get('specialty'),
                'subscription_pricing_snapshot': subscription, 'usage_pricing_snapshot': usage,
                'subscription_allocation': _amount(subscription_allocation), 'usage_quantity': str(quantity),
                'included_allowance_used': str(min(quantity, included)), 'billable_usage_quantity': str(billable_quantity),
                'usage_cost': _amount(usage_cost), 'known_cost': _amount(economic),
                'additional_cash_cost': _amount(cash), 'fx': fx_details,
                'verification_status': verification_status,
                'evidence': [e for item in (subscription, usage) if item for e in item.get('evidence', [])]}

    def _overhead_line(self, overhead, output, rates, as_of, max_age, direct_cost, clip_count, final_duration, project_hours, missing):
        category = overhead.get('category')
        pricing = overhead.get('pricing')
        if overhead.get('user_amount') is not None:
            amount = decimal_value(overhead['user_amount'], 'user overhead amount', minimum=ZERO)
            return {'category': category, 'name': overhead.get('name') or 'Project estimate', 'method': 'user_provided',
                    'quantity': '1', 'known_cost': _amount(amount), 'cash_cost': _amount(amount),
                    'source': 'user_provided_estimate', 'verification_status': 'user_provided', 'status': 'estimated'}
        if not pricing:
            missing.append(f'No overhead pricing is available for {overhead.get("name") or category}.')
            return {'category': category, 'name': overhead.get('name'), 'status': 'unpriced', 'known_cost': None, 'cash_cost': None}
        method = pricing['method']
        rate = decimal_value(pricing['rate'], 'overhead rate', minimum=ZERO)
        supplied_quantity = overhead.get('quantity')
        quantity = decimal_value(supplied_quantity if supplied_quantity is not None else '1', 'overhead quantity', minimum=ZERO)
        if method == 'fixed_project':
            native = rate
        elif method == 'per_hour':
            quantity = decimal_value(supplied_quantity if supplied_quantity is not None else project_hours, 'overhead hours', minimum=ZERO)
            native = rate * quantity
        elif method == 'per_clip':
            quantity = decimal_value(supplied_quantity if supplied_quantity is not None else clip_count, 'overhead clip count', minimum=ZERO)
            native = rate * quantity
        elif method == 'per_video_minute':
            quantity = decimal_value(supplied_quantity if supplied_quantity is not None else final_duration / Decimal('60'), 'final video minutes', minimum=ZERO)
            native = rate * quantity
        elif method == 'per_unit':
            if supplied_quantity is None:
                missing.append(f'A quantity is required for {pricing.get("name")} ({pricing.get("unit")}).')
            native = rate * quantity
        elif method == 'monthly_projects':
            projects = decimal_value(overhead.get('expected_monthly_projects') or pricing.get('expected_monthly_projects'), 'expected_monthly_projects', minimum=Decimal('1'))
            native = rate / projects
        elif method == 'monthly_hours':
            denominator = decimal_value(overhead.get('expected_monthly_hours') or pricing.get('expected_monthly_hours'), 'expected_monthly_hours', minimum=Decimal('0.0001'))
            if project_hours <= ZERO:
                missing.append(f'Project hours are required to allocate {pricing.get("name")} overhead.')
                native = ZERO
            else:
                native = rate * project_hours / denominator
        elif method == 'percentage':
            native = direct_cost * rate / Decimal('100')
            quantity = rate
        else:
            raise ValueError(f'Unsupported overhead pricing method {method}.')
        if method == 'percentage':
            converted, fx = native, {'rate': '1', 'base_currency': output, 'quote_currency': output, 'exchange_rate_id': None}
        else:
            converted, fx = self._fx(native, pricing['currency'], output, rates, as_of, max_age, missing, 'production overhead')
        amount = converted if converted is not None else ZERO
        cash_amount = amount
        if method in ('monthly_projects', 'monthly_hours') and not overhead.get('subscription_purchased_for_project'):
            cash_amount = ZERO
        elif method in ('monthly_projects', 'monthly_hours') and overhead.get('subscription_purchased_for_project'):
            full_price, _ = self._fx(rate, pricing['currency'], output, rates, as_of, max_age, missing, 'overhead subscription purchase')
            cash_amount = full_price if full_price is not None else ZERO
        return {'pricing_id': pricing.get('id'), 'category': category, 'name': pricing.get('name'), 'method': method,
                'quantity': str(quantity), 'unit': pricing.get('unit'), 'unit_rate': str(rate),
                'source_currency': pricing.get('currency'), 'known_cost': _amount(amount) if converted is not None else None,
                'cash_cost': _amount(cash_amount) if converted is not None else None, 'exchange_rate': fx,
                'verification_status': pricing.get('verification_status'), 'evidence': pricing.get('evidence', []),
                'source': 'admin_configured', 'status': 'priced' if converted is not None else 'incomplete'}

    @staticmethod
    def _commercial(base_cost, retry_cost, inputs, currency, complete, missing):
        cost = base_cost + retry_cost
        markup = inputs.get('markup_percentage')
        margin = inputs.get('target_margin_percentage')
        if markup is not None and margin is not None:
            raise ValueError('Choose markup_percentage or target_margin_percentage, not both.')
        if markup is not None:
            markup = decimal_value(markup, 'markup_percentage', minimum=ZERO)
            price = cost * (ONE + markup / Decimal('100'))
            basis = {'markup_percentage': str(markup)}
        elif margin is not None:
            margin = decimal_value(margin, 'target_margin_percentage', minimum=ZERO)
            if margin >= 100:
                raise ValueError('target_margin_percentage must be less than 100.')
            price = cost / (ONE - margin / Decimal('100'))
            basis = {'target_margin_percentage': str(margin)}
        else:
            price = None
            basis = {}
        profit = price - cost if price is not None else None
        gross_margin = (profit / price * Decimal('100')) if price else None
        return {'base_production_cost': _amount(base_cost), 'retry_allowance_cost': _amount(retry_cost),
                'total_estimated_production_cost': _amount(cost) if complete else None,
                'known_partial_cost': _amount(cost) if not complete else None,
                'suggested_selling_price': _amount(price) if price is not None and complete else None,
                'gross_profit': _amount(profit) if profit is not None and complete else None,
                'gross_margin_percentage': _amount(gross_margin) if gross_margin is not None and complete else None,
                'currency': currency, 'pricing_basis': basis,
                'partial_selling_price': _amount(price) if price is not None and not complete else None,
                'status': 'complete' if complete else 'incomplete', 'missing_information': list(missing)}
