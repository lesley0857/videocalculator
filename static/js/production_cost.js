(() => {
  const app = document.getElementById('pricing-app');
  if (!app) return;
  const videoGenerationMode = app.dataset.calculatorType === 'video_generation';
  const $ = (id) => document.getElementById(id);
  const models = JSON.parse($('registered-models').textContent || '[]');
  const productionTools = JSON.parse($('production-tools-data')?.textContent || '[]');
  const productionOverheads = JSON.parse($('production-overheads-data')?.textContent || '[]');
  const starting = JSON.parse($('starting-inputs').textContent || 'null');
  const components = [];
  const operations = (starting?.operations || []).map((item) => ({ ...item }));
  const tools = [], overheads = [];
  const videoScenes = [];
  let editingScene = -1;
  let selectedCapabilityConfiguration = {};
  let primarySelection = { specialty_slug: '', provider: null, offering_id: null, access_route_id: null, plan_id: null };
  let redrawVideoScenes = () => {};
  const modelSelect = $('model');
  const workflowSelect = $('workflow');
  const priceSelect = $('pricing-record');
  const message = $('message');
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  let lastPayload = null;

  const escapeText = (value) => String(value ?? '—');
  const fmt = (value, currency) => value == null ? '—' : `${currency || ''} ${value}`.trim();
  const addText = (parent, tag, value, className) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = escapeText(value);
    parent.appendChild(node);
    return node;
  };

  const resetSelect = (select, prompt) => { if (!select) return; select.replaceChildren(new Option(prompt, '')); select.disabled = true; };
  const fillOptions = (select, rows, prompt, label, value = 'id') => { resetSelect(select, prompt); rows.forEach((item) => select.add(new Option(label(item), item[value]))); select.disabled = !rows.length; };
  const getJson = async (url) => { const response = await fetch(url, {credentials:'same-origin'}); const data = await response.json(); if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`); return data; };
  const buildProviderOptions = async () => {
    const specialty = $('vg-primary-specialty').value;
    primarySelection = { specialty_slug: specialty, provider: null, offering_id: null, access_route_id: null, plan_id: null };
    const providerSelect = $('vg-primary-provider'); resetSelect(providerSelect, 'Loading active providers…');
    resetSelect($('vg-primary-offering'), 'Choose provider first'); resetSelect($('vg-primary-route'), 'Choose offering first');
    resetSelect(modelSelect, 'Choose an access route first'); resetSelect(workflowSelect, 'Choose a model version first'); resetSelect(priceSelect, 'Select a model and workflow first');
    try { const data = await getJson(`${app.dataset.specialtiesUrl.replace(/specialties\/$/, '')}specialties/${encodeURIComponent(specialty)}/providers/`);
      resetSelect(providerSelect, 'Choose an active provider');
      (data.results || []).forEach((row) => { const option = new Option(row.name, row.slug); option.dataset.providerId = row.id; providerSelect.add(option); });
      providerSelect.disabled = !(data.results || []).length;
      if (!(data.results || []).length) message.textContent = 'No active providers are configured for this specialty yet.';
    } catch (error) { resetSelect(providerSelect, 'Provider catalogue unavailable'); message.textContent = error.message; }
  };
  const loadOfferings = async () => {
    const provider = $('vg-primary-provider').value; primarySelection.provider = provider || null; primarySelection.provider_id = $('vg-primary-provider').selectedOptions[0]?.dataset.providerId || null; primarySelection.offering_id = null; primarySelection.access_route_id = null; primarySelection.plan_id = null;
    const qs = new URLSearchParams({ specialty: primarySelection.specialty_slug, provider });
    resetSelect($('vg-primary-offering'), 'Loading offerings…'); resetSelect($('vg-primary-route'), 'Choose offering first'); resetSelect(modelSelect, 'Choose an access route first');
    if (!provider) return;
    try { const data = await getJson(`${app.dataset.offeringsUrl}?${qs}`); fillOptions($('vg-primary-offering'), data.results || [], 'Choose an active offering', (row) => row.name); }
    catch (error) { resetSelect($('vg-primary-offering'), 'No applicable offerings'); message.textContent = error.message; }
  };
  const loadRoutesAndPlans = async () => {
    const offering = $('vg-primary-offering').value; primarySelection.offering_id = offering || null; primarySelection.access_route_id = null; primarySelection.plan_id = null;
    resetSelect($('vg-primary-route'), 'Loading access routes…'); resetSelect(modelSelect, 'Choose an access route first');
    if (!offering) return;
    const qs = new URLSearchParams({ specialty: primarySelection.specialty_slug, offering });
    try {
      const [routes, plans] = await Promise.all([getJson(`${app.dataset.routesUrl}?${qs}`), getJson(`/api/video-registry/plans/?${qs}`)]);
      const routeSelect = $('vg-primary-route'); resetSelect(routeSelect, 'Choose an access route');
      (routes.results || []).forEach((route) => { const option = new Option(`${route.name} · ${route.pricing_method}`, route.id); option.dataset.route = JSON.stringify(route); routeSelect.add(option); });
      routeSelect.disabled = !(routes.results || []).length;
      const planSelect = $('subscription-plan'); planSelect.replaceChildren(new Option('No subscription assumption', ''));
      (plans.results || []).forEach((plan) => planSelect.add(new Option(`${plan.name} · ${plan.price} ${plan.currency}`, plan.id)));
      planSelect.disabled = false;
    } catch (error) { resetSelect($('vg-primary-route'), 'No applicable access routes'); message.textContent = error.message; }
  };
  const loadModelsForRoute = async () => {
    const routeId = $('vg-primary-route').value; primarySelection.access_route_id = routeId || null;
    const route = $('vg-primary-route').selectedOptions[0];
    resetSelect(modelSelect, 'Loading model versions…'); resetSelect(workflowSelect, 'Choose a model version first');
    resetSelect(priceSelect, 'Select a model and workflow first');
    if (!routeId) return;
    const qs = new URLSearchParams({ specialty: primarySelection.specialty_slug, provider: primarySelection.provider,
      offering: primarySelection.offering_id, access_route: routeId });
    try {
      const data = await getJson(`${app.dataset.modelsUrl}?${qs}`);
      const matches = data.results || [];
      models.splice(0, models.length, ...models.filter((model) => !model._videoGenerationCatalogue), ...matches.map((row) => ({
        id: row.id, name: row.name, slug: row.slug, version: row.version, provider: row.provider.name,
        provider_slug: row.provider.slug, provider_id: null, workflows: row.workflows, _videoGenerationCatalogue: true,
      })));
      fillOptions(modelSelect, matches, 'Choose a model version', (row) => `${row.provider.name} · ${row.name} v${row.version}`);
      const selectedPlan = JSON.parse(route.dataset.route || '{}').subscription_plan_id;
      if (selectedPlan && [...$('subscription-plan').options].some((option) => option.value === selectedPlan)) $('subscription-plan').value = selectedPlan;
      if (!matches.length) message.textContent = 'No active model version is registered on this route.';
    } catch (error) { resetSelect(modelSelect, 'No applicable model versions'); message.textContent = error.message; }
  };
  const restoreVideoSelection = async (source) => {
    if (!source?.specialty_slug || !source?.offering_id || !source?.access_route_id || !source?.video_model_id) return;
    try {
      await buildProviderOptions();
      const providers = await getJson(app.dataset.providersUrl);
      const provider = (providers.results || []).find((row) => row.id === source.provider_id);
      if (!provider) return;
      $('vg-primary-provider').value = provider.slug; await loadOfferings();
      $('vg-primary-offering').value = source.offering_id; await loadRoutesAndPlans();
      $('vg-primary-route').value = source.access_route_id; await loadModelsForRoute();
      modelSelect.value = source.video_model_id; modelSelect.dispatchEvent(new Event('change'));
      workflowSelect.value = source.workflow_slug || '';
      $('clip-count').value = source.clip_count || source.generation_requests || 1;
      $('requests').value = source.generation_requests || 1; $('duration').value = source.duration_seconds || 5;
      $('retries').value = source.retry_allowance || 0;
      if (source.configuration) selectedCapabilityConfiguration = { ...source.configuration };
      if (source.subscription_plan_id) $('subscription-plan').value = source.subscription_plan_id;
      if (!components.some((item) => item.video_model_id === source.video_model_id)) {
        const component = { ...source, label: `${provider.name} · ${models.find((item) => item.id === source.video_model_id)?.name || 'Selected model'}` };
        delete component.pricing_record_id;
        components.push(component);
      }
      renderLists();
    } catch (error) { message(`Some saved model selections need to be chosen again: ${error.message}`); }
  };
  const renderCapabilityControls = (details) => {
    const container = $('vg-supported-configurations'); if (!container) return;
    container.replaceChildren(); selectedCapabilityConfiguration = {};
    const allCaps = details.capabilities || [];
    const audioOptions = allCaps.filter((cap) => cap.configuration?.selectable && cap.status === 'supported' && cap.configuration.input_type === 'flag' && ['native_audio', 'video_only'].includes(cap.key));
    const caps = allCaps.filter((cap) => cap.configuration?.selectable && cap.configuration.input_type !== 'flag');
    if (audioOptions.length && !caps.some((cap) => cap.key === 'audio_mode')) {
      const label = document.createElement('label'); label.textContent = 'Audio mode'; const control = document.createElement('select'); control.add(new Option('Choose an audio mode', ''));
      audioOptions.forEach((cap) => control.add(new Option(cap.label, cap.key)));
      control.dataset.capabilityKey = 'audio_mode'; control.addEventListener('change', () => { if (control.value) selectedCapabilityConfiguration.audio_mode = control.value; else delete selectedCapabilityConfiguration.audio_mode; if (workflowSelect.value) loadPricing(); });
      label.appendChild(control); container.appendChild(label);
    }
    caps.forEach((cap) => {
      const label = document.createElement('label'); label.textContent = `${cap.label}${cap.unit ? ` (${cap.unit})` : ''}`;
      const config = cap.configuration; let control;
      if (config.input_type === 'select' && config.allowed_values.length) {
        control = document.createElement('select'); control.add(new Option('Choose an option', ''));
        config.allowed_values.forEach((value) => control.add(new Option(String(value), String(value))));
      } else if (config.input_type === 'boolean') {
        control = document.createElement('input'); control.type = 'checkbox';
      } else {
        control = document.createElement('input'); control.type = config.input_type === 'number' ? 'number' : 'text';
        if (config.minimum_value) control.min = config.minimum_value; if (config.maximum_value) control.max = config.maximum_value;
      }
      control.dataset.capabilityKey = cap.key; control.addEventListener('change', () => { const value = config.input_type === 'boolean' ? control.checked : control.value; if (value !== '' && value !== false) selectedCapabilityConfiguration[cap.key] = value; else delete selectedCapabilityConfiguration[cap.key]; if (cap.key === 'generation_duration_seconds' && control.value) $('duration').value = control.value; if (workflowSelect.value) loadPricing(); });
      label.appendChild(control); container.appendChild(label);
    });
    container.hidden = false;
    if (!caps.length) addText(container, 'p', 'This model version has no verified selectable configuration options.');
  };

  if (videoGenerationMode) {
    $('vg-primary-specialty').addEventListener('change', buildProviderOptions);
    $('vg-primary-provider').addEventListener('change', loadOfferings);
    $('vg-primary-offering').addEventListener('change', loadRoutesAndPlans);
    $('vg-primary-route').addEventListener('change', loadModelsForRoute);
    buildProviderOptions();
  }

  const renderLists = () => {
    $('components').replaceChildren();
    $('empty-components').hidden = components.length > 0;
    components.forEach((item, index) => {
      const li = document.createElement('li');
      addText(li, 'span', `${item.label} · ${item.workflow_slug || 'No workflow'} · ${item.clip_count} clip(s) · ${item.generation_requests} request(s) × ${item.duration_seconds}s`);
      const remove = addText(li, 'button', 'Remove');
      remove.type = 'button'; remove.className = 'remove-item'; remove.addEventListener('click', () => { components.splice(index, 1); renderLists(); });
      $('components').appendChild(li);
    });
    $('operations').replaceChildren();
    operations.forEach((item, index) => {
      const li = document.createElement('li');
      addText(li, 'span', `${item.label || item.operation_key} · quantity ${item.quantity}`);
      const remove = addText(li, 'button', 'Remove');
      remove.type = 'button'; remove.className = 'remove-item'; remove.addEventListener('click', () => { operations.splice(index, 1); renderLists(); });
      $('operations').appendChild(li);
    });
    const renderSimple = (id, rows, describe) => {
      $(id).replaceChildren(); rows.forEach((row, index) => { const li = document.createElement('li'); addText(li, 'span', describe(row)); const remove = addText(li, 'button', 'Remove'); remove.type = 'button'; remove.className = 'remove-item'; remove.addEventListener('click', () => { rows.splice(index, 1); renderLists(); }); $(id).appendChild(li); });
    };
    renderSimple('production-tools', (tools), (row) => `${row.name || productionTools.find((t) => t.id === row.tool_id)?.name} · ${row.activities.join(', ')} · configured rates selected`);
    renderSimple('overheads', overheads, (row) => `${row.name || row.category} · ${row.user_amount != null ? `${row.user_amount} ${$('currency').value} (your estimate)` : 'configured rate'}`);
  };

  const setSelectMessage = (select, text, disabled = true) => {
    select.replaceChildren(new Option(text, ''));
    select.disabled = disabled;
  };

  $('provider').addEventListener('change', () => {
    const provider = $('provider').value;
    setSelectMessage(modelSelect, provider ? 'Choose a model version' : 'Choose a provider first', !provider);
    const providerModels = models.filter((m) => m.provider === provider);
    providerModels.forEach((item) => modelSelect.add(new Option(`${item.name} v${item.version}`, item.id)));
    if (provider && !providerModels.length) setSelectMessage(modelSelect, 'No active model versions for this provider');
    setSelectMessage(workflowSelect, 'Choose a compatible workflow');
    setSelectMessage(priceSelect, 'Select a model and workflow first');
    $('model-info').textContent = 'Choose a model version to see its registry and verification details.';
    [...$('subscription-plan').options].forEach((option) => { if (option.value) option.hidden = option.dataset.providerId !== (models.find((m) => m.id === modelSelect.value)?.provider_id || ''); });
  });

  modelSelect.addEventListener('change', async () => {
    const item = models.find((m) => m.id === modelSelect.value);
    setSelectMessage(workflowSelect, item ? 'Choose a compatible workflow' : 'Choose a model version');
    if (!item) return;
    (item.workflows || []).forEach((wf) => workflowSelect.add(new Option(wf.name, wf.slug)));
    workflowSelect.disabled = !(item.workflows || []).length;
    if (!(item.workflows || []).length) $('model-info').textContent = 'No workflow compatibility is registered for this model version. Ask an administrator to configure its registry relationships.';
    if (!videoGenerationMode) { $('subscription-plan').value = ''; [...$('subscription-plan').options].forEach((option) => { if (option.value) option.hidden = option.dataset.providerId !== item.provider_id; }); }
    try {
      const url = `/api/video-registry/models/${encodeURIComponent(item.provider_slug)}/${encodeURIComponent(item.slug)}/?version=${encodeURIComponent(item.version)}`;
      const response = await fetch(url);
      const details = await response.json();
      const info = $('model-info');
      info.replaceChildren();
      addText(info, 'strong', `${details.provider?.name || item.provider} · ${details.name} v${details.version}`);
      addText(info, 'p', `Registry verification: ${details.verification_status || 'unknown'}. ${details.description || 'No model description is configured.'}`);
      const caps = details.capabilities || [];
      if (videoGenerationMode) renderCapabilityControls(details);
      addText(info, 'p', caps.length ? `Capabilities: ${caps.map((cap) => `${cap.label}: ${cap.status}${cap.value ? ` (${cap.value}${cap.unit ? ` ${cap.unit}` : ''})` : ''}`).join('; ')}` : 'No capability evidence is configured. Do not infer unsupported or unknown capabilities.');
      if (!response.ok) info.textContent = 'Could not load model verification details. Workflow availability still follows the registered model version.';
    } catch { $('model-info').textContent = 'Could not load model verification details.'; }
    await loadPricing();
  });

  const loadPricing = async () => {
    setSelectMessage(priceSelect, 'Checking effective pricing…');
    const query = new URLSearchParams({ workflow: workflowSelect.value });
    if (videoGenerationMode && primarySelection.access_route_id) query.set('access_route', primarySelection.access_route_id);
    try {
      const response = await fetch(`/pricing/api/models/${encodeURIComponent(modelSelect.value)}/?${query}`);
      const data = await response.json();
      const configuration = videoGenerationMode ? { ...selectedCapabilityConfiguration } : Object.fromEntries([['resolution', $('resolution').value.trim()], ['aspect_ratio', $('aspect-ratio').value.trim()], ['audio_mode', $('audio-mode').value], ['generation_duration_seconds', $('generation-duration').value]].filter(([, v]) => v !== ''));
      const matching = (data.results || []).filter((item) => (!item.workflow || item.workflow === workflowSelect.value) && JSON.stringify(item.configuration || {}) === JSON.stringify(configuration));
      setSelectMessage(priceSelect, matching.length ? 'Use effective applicable pricing' : 'No effective price for this configuration', false);
      matching.forEach((item) => {
        const label = `${item.method.replaceAll('_', ' ')} ${JSON.stringify(item.configuration || {})} · ${item.rate} ${item.currency}/${item.unit} · ${item.verification_status}`;
        priceSelect.add(new Option(label, item.id));
      });
      if (!(data.results || []).length) $('model-info').append(document.createTextNode(' No effective pricing is configured for this model and workflow.'));
    } catch { setSelectMessage(priceSelect, 'Pricing information could not be loaded'); }
  };
  workflowSelect.addEventListener('change', () => { if (workflowSelect.value) loadPricing(); });
  ['resolution', 'aspect-ratio', 'audio-mode', 'generation-duration'].forEach((id) => $(id).addEventListener('change', () => { if (modelSelect.value && workflowSelect.value) loadPricing(); }));

  $('add-component').addEventListener('click', () => {
    const item = models.find((m) => m.id === modelSelect.value);
    if (!item || !workflowSelect.value) { message.textContent = 'Choose a provider, model version, and registered workflow.'; return; }
    const clipCount = Number($('clip-count').value);
    const requests = Number($('requests').value);
    const duration = $('duration').value;
    const retries = Number($('retries').value);
    if (!Number.isInteger(clipCount) || clipCount < 1 || !Number.isInteger(requests) || requests < 1 || Number(duration) <= 0 || !Number.isInteger(retries) || retries < 0) {
      message.textContent = 'Enter a positive clip count, request count, and duration. Additional billable attempts must be zero or more.'; return;
    }
    const workflow = workflowSelect.selectedOptions[0];
    if (videoGenerationMode && videoScenes.length === 0) { message.textContent = 'Add at least one scene before selecting a video model component.'; return; }
    components.push({ video_model_id: item.id, workflow_slug: workflow.value, duration_seconds: duration,
      generation_requests: requests, clip_count: clipCount, retry_allowance: retries,
      pricing_record_id: priceSelect.value || undefined,
      configuration: videoGenerationMode ? { ...selectedCapabilityConfiguration } : Object.fromEntries([['resolution', $('resolution').value.trim()], ['aspect_ratio', $('aspect-ratio').value.trim()], ['audio_mode', $('audio-mode').value], ['generation_duration_seconds', $('generation-duration').value]].filter(([, v]) => v !== '')),
      subscription_plan_id: $('subscription-plan').value || undefined,
      specialty_slug: videoGenerationMode ? primarySelection.specialty_slug : undefined,
      provider_id: videoGenerationMode ? primarySelection.provider_id : undefined,
      offering_id: videoGenerationMode ? primarySelection.offering_id : undefined,
      access_route_id: videoGenerationMode ? primarySelection.access_route_id : undefined,
      credits_remaining: $('credits-remaining').value || undefined,
      label: `${item.provider} · ${item.name} v${item.version}` });
    message.textContent = '';
    renderLists();
  });

  $('add-operation').addEventListener('click', () => {
    const select = $('operation');
    if (!select.value) { message.textContent = 'No configured optional service is available to add.'; return; }
    operations.push({ operation_key: select.value, quantity: $('operation-quantity').value, duration_seconds: $('operation-duration').value, provider_id: models.find((m) => m.id === modelSelect.value)?.provider_id });
    renderLists();
  });

  const fillToolPrices = () => {
    const tool = productionTools.find((item) => item.id === $('tool-choice').value);
    const sub = $('tool-subscription'), usage = $('tool-usage');
    setSelectMessage(sub, 'No subscription selected', false); setSelectMessage(usage, 'No usage price selected', false);
    if (!tool) return;
    tool.pricing.filter((p) => p.cost_type === 'subscription').forEach((p) => sub.add(new Option(`${p.name} · ${p.rate} ${p.currency} · ${p.allocation_method}`, p.id)));
    tool.pricing.filter((p) => p.cost_type === 'usage').forEach((p) => usage.add(new Option(`${p.name} · ${p.rate} ${p.currency}/${p.unit}`, p.id)));
    $('tool-activities').value = tool.activities.join(', ');
  };
  productionTools.forEach((item) => { const option = new Option(`${item.provider} · ${item.name}`, item.id); option.dataset.specialties = JSON.stringify(item.specialties || []); $('tool-choice').add(option); });
  $('tool-choice').addEventListener('change', fillToolPrices);
  if (videoGenerationMode) {
    const specialtySelect = $('vg-optional-specialty'), providerSelect = $('vg-optional-provider'), offeringSelect = $('vg-optional-offering');
    const refreshProductionTools = () => {
      const specialty = specialtySelect.value, providerId = providerSelect.value, offeringId = offeringSelect.value;
      [...$('tool-choice').options].forEach((option) => {
        if (!option.value) return;
        const tool = productionTools.find((item) => item.id === option.value);
        option.hidden = !specialty || !providerId || !offeringId || !tool || !tool.specialties?.includes(specialty) || tool.provider_id !== providerId || tool.offering_id !== offeringId;
      });
      if ($('tool-choice').selectedOptions[0]?.hidden) { $('tool-choice').value = ''; fillToolPrices(); }
    };
    specialtySelect.addEventListener('change', async () => {
      resetSelect(providerSelect, 'Loading specialty providers…'); resetSelect(offeringSelect, 'Choose a provider first'); refreshProductionTools();
      if (!specialtySelect.value) return;
      try { const data = await getJson(`${app.dataset.specialtiesUrl}${encodeURIComponent(specialtySelect.value)}/providers/`);
        resetSelect(providerSelect, 'Choose an active provider');
        (data.results || []).forEach((row) => { const option = new Option(row.name, row.id); option.dataset.slug = row.slug; providerSelect.add(option); });
        providerSelect.disabled = !(data.results || []).length;
        if (!data.results?.length) message.textContent = 'No active provider is configured for this optional specialty.';
      } catch (error) { resetSelect(providerSelect, 'Provider catalogue unavailable'); message.textContent = error.message; }
    });
    providerSelect.addEventListener('change', async () => {
      resetSelect(offeringSelect, 'Loading provider offerings…'); refreshProductionTools();
      if (!providerSelect.value) return;
      const qs = new URLSearchParams({ specialty: specialtySelect.value, provider: providerSelect.selectedOptions[0].dataset.slug });
      try { const data = await getJson(`${app.dataset.offeringsUrl}?${qs}`); fillOptions(offeringSelect, data.results || [], 'Choose an active offering', (row) => row.name); refreshProductionTools(); }
      catch (error) { resetSelect(offeringSelect, 'No applicable offerings'); message.textContent = error.message; }
    });
    offeringSelect.addEventListener('change', refreshProductionTools);
  }
  if (videoGenerationMode) {
    const scriptTools = productionTools.filter((item) => item.specialties?.includes('scriptwriting-creative-development') && item.activities?.includes('script') && item.pricing?.length);
    scriptTools.forEach((item) => $('vg-script-tool').add(new Option(`${item.provider} · ${item.name}`, item.id)));
    const method = () => document.querySelector('input[name="vg-script-method"]:checked').value;
    const syncScriptTool = () => {
      const selected = $('vg-script-tool').value;
      $('tool-choice').value = selected;
      $('tool-choice').dispatchEvent(new Event('change'));
      const tool = productionTools.find((item) => item.id === selected);
      $('vg-provider-link').replaceChildren();
      if (tool?.provider_website_url) { const link = document.createElement('a'); link.href = tool.provider_website_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `Open ${tool.provider} website`; $('vg-provider-link').appendChild(link); }
      if (tool) $('tool-activities').value = [...new Set([...tool.activities, 'script'])].join(', ');
      $('vg-script-status').textContent = selected ? `AI-assisted preparation selected using ${tool?.provider} · ${tool?.name}. Add its verified subscription or usage allocation under Production tools.` : 'Choose a configured scriptwriting tool. No AI service will be called by this calculator.';
    };
    $('vg-script-tool').addEventListener('change', syncScriptTool);
    document.querySelectorAll('input[name="vg-script-method"]').forEach((radio) => radio.addEventListener('change', () => {
      const assisted = method() === 'ai_assisted'; $('vg-ai-panel').hidden = !assisted;
      if (!assisted) {
        tools.splice(0, tools.length, ...tools.filter((item) => !item.__videoScriptwriting));
        $('vg-script-tool').value = ''; $('tool-choice').value = ''; $('tool-subscription').value = ''; $('tool-usage').value = '';
        $('vg-script-status').textContent = 'Self-written script selected. Scriptwriting tool selection and its estimated cost were removed.'; renderLists();
      } else syncScriptTool();
    }));
    const buildPrompt = () => {
      const brief = $('vg-brief').value.trim(), tool = scriptTools.find((item) => item.id === $('vg-script-tool').value);
      if (!brief) { message.textContent = 'Write a video brief before preparing the prompt.'; $('vg-brief').focus(); return; }
      if (!tool) { message.textContent = 'Choose an active configured scriptwriting tool first.'; $('vg-script-tool').focus(); return; }
      const format = $('vg-script-format').selectedOptions[0].textContent;
      $('vg-prompt').value = `Prepare a ${format.toLowerCase()} for the following video project. Return a usable script with clearly numbered scenes, spoken words (if any), visual directions, camera notes, generation prompts, and approximate duration per scene. Do not invent product facts; mark missing information as questions.\n\nTitle: ${$('vg-title').value || 'Untitled video'}\nBrief: ${brief}\nPurpose: ${$('vg-purpose').value}\nAudience: ${$('vg-audience').value}\nDestination: ${$('vg-platform').value}\nTarget finished duration: ${$('vg-finished-duration').value} seconds\nPreferred aspect ratio: ${$('vg-aspect').value}\nPreferred output resolution: ${$('vg-resolution').value}\nVisual direction: ${$('vg-style').value}\nTone: ${$('vg-tone').value}\nNarrative direction: ${$('vg-narrative').value}\nAdditional instructions: ${$('vg-instructions').value}\n\nReturn provider-neutral scene content that can be reviewed and edited by the customer.`;
      $('vg-copy-prompt').disabled = false; message.textContent = `Prompt prepared for external use with ${tool.provider} · ${tool.name}. No request was sent.`;
    };
    $('vg-build-prompt').addEventListener('click', buildPrompt);
    $('vg-copy-prompt').addEventListener('click', async () => {
      const prompt = $('vg-prompt').value; if (!prompt) return;
      try { await navigator.clipboard.writeText(prompt); message.textContent = 'Prompt copied. Open the provider separately and paste it there.'; }
      catch { $('vg-prompt').focus(); $('vg-prompt').select(); try { document.execCommand('copy'); message.textContent = 'Prompt copied. Open the provider separately and paste it there.'; } catch { message.textContent = 'Select and copy the prompt manually.'; } }
    });
    const sceneFields = [['title','vg-scene-title'],['description','vg-scene-description'],['visual_direction','vg-scene-visual'],['camera_direction','vg-scene-camera'],['generation_prompt','vg-scene-prompt'],['planned_duration_seconds','vg-scene-duration'],['required_visual_assets','vg-scene-assets'],['required_voice_audio','vg-scene-audio'],['production_notes','vg-scene-notes']];
    const renderScenes = () => {
      const list = $('vg-scenes'); list.replaceChildren();
      videoScenes.forEach((scene, index) => {
        const li = document.createElement('li'), article = document.createElement('article'); addText(article, 'h3', `Scene ${index + 1}${scene.title ? ` · ${scene.title}` : ''}`);
        addText(article, 'p', scene.description); addText(article, 'p', `Planned scene duration: ${scene.planned_duration_seconds} seconds`);
        if (scene.visual_direction) addText(article, 'p', `Visual direction: ${scene.visual_direction}`);
        const actions = document.createElement('div'); actions.className = 'vg-scene-actions';
        const action = (label, fn) => { const button = addText(actions, 'button', label); button.type = 'button'; button.className = 'button button-secondary'; button.addEventListener('click', fn); };
        action('Edit', () => { editingScene = index; sceneFields.forEach(([key,id]) => { $(id).value = scene[key] || ''; }); $('vg-add-scene').textContent = 'Save scene changes'; $('vg-scene-title').focus(); });
        action('Duplicate', () => { videoScenes.splice(index + 1, 0, { ...scene }); renderScenes(); });
        action('Move up', () => { if (index) [videoScenes[index - 1],videoScenes[index]] = [videoScenes[index],videoScenes[index - 1]]; renderScenes(); });
        action('Move down', () => { if (index < videoScenes.length - 1) [videoScenes[index + 1],videoScenes[index]] = [videoScenes[index],videoScenes[index + 1]]; renderScenes(); });
        action('Delete', () => { videoScenes.splice(index, 1); renderScenes(); });
        article.appendChild(actions); li.appendChild(article); list.appendChild(li);
      });
      const total = videoScenes.reduce((sum, scene) => sum + Number(scene.planned_duration_seconds || 0), 0);
      const finished = Number($('vg-finished-duration').value) || 0, delta = total - finished;
      const difference = delta ? ` Scene total differs from finished target by ${delta > 0 ? '+' : ''}${delta.toFixed(2)} seconds.` : '';
      $('vg-scene-total').textContent = videoScenes.length ? `${videoScenes.length} scene(s) · ${total.toFixed(2)} seconds planned scene duration; finished target ${finished.toFixed(2)} seconds.${difference} This is separate from billable generated footage.` : 'No scenes planned.';
    };
    redrawVideoScenes = renderScenes;
    $('vg-add-scene').addEventListener('click', () => {
      const values = Object.fromEntries(sceneFields.map(([key,id]) => [key,$(id).value.trim()]));
      if (!values.description || !Number.isFinite(Number(values.planned_duration_seconds)) || Number(values.planned_duration_seconds) <= 0) { message('Each scene needs a description and positive planned duration.'); return; }
      if (editingScene < 0 && videoScenes.length >= 100) { message('A video plan can contain at most 100 scenes.'); return; }
      if (editingScene >= 0) videoScenes[editingScene] = values; else videoScenes.push(values);
      editingScene = -1; sceneFields.forEach(([,id]) => { if (id !== 'vg-scene-duration') $(id).value = ''; }); $('vg-scene-duration').value = '5'; $('vg-add-scene').textContent = 'Add scene'; renderScenes(); message('Scene plan updated.');
    });
    $('vg-finished-duration').addEventListener('input', () => { $('final-duration').value = $('vg-finished-duration').value; });
    $('vg-brief').addEventListener('input', () => { if ($('vg-brief').value.length > 4000) message('The video brief can contain up to 4,000 characters.'); });
    renderScenes();
    if (starting?.video_generation) {
      const v = starting.video_generation;
      for (const [id, key] of [['vg-title','title'],['vg-brief','video_brief'],['vg-purpose','purpose'],['vg-audience','target_audience'],['vg-platform','destination_platform'],['vg-aspect','aspect_ratio'],['vg-resolution','output_resolution'],['vg-finished-duration','target_finished_duration_seconds'],['vg-style','visual_style'],['vg-instructions','production_instructions'],['vg-tone','tone'],['vg-narrative','narrative_direction'],['vg-script-directions','script_directions'],['vg-script','script']]) if (v[key] != null) $(id).value = v[key];
      const radio = document.querySelector(`input[name="vg-script-method"][value="${v.script_preparation_method}"]`); if (radio) { radio.checked = true; radio.dispatchEvent(new Event('change')); }
      (v.scenes || []).forEach((scene) => videoScenes.push({ ...scene })); renderScenes();
      if (v.scriptwriting_tool_id) $('vg-script-tool').value = v.scriptwriting_tool_id;
      $('final-duration').value = v.target_finished_duration_seconds || $('final-duration').value;
    }
  }
  $('add-tool').addEventListener('click', () => {
    const tool = productionTools.find((item) => item.id === $('tool-choice').value);
    if (!tool) { message.textContent = 'Choose a configured production tool.'; return; }
    const activities = $('tool-activities').value.split(',').map((x) => x.trim()).filter(Boolean);
    const scriptToolSelected = videoGenerationMode && document.querySelector('input[name="vg-script-method"]:checked').value === 'ai_assisted' && tool.id === $('vg-script-tool').value;
    if (scriptToolSelected && !activities.includes('script')) activities.push('script');
    const subscription = $('tool-subscription').value, usage = $('tool-usage').value;
    if (!subscription && !usage) { message.textContent = 'Select an effective subscription or usage rate for this tool.'; return; }
    const chosenSpecialty = scriptToolSelected ? 'scriptwriting-creative-development' : (videoGenerationMode ? $('vg-optional-specialty').value : '');
    if (videoGenerationMode && (!chosenSpecialty || !tool.specialties?.includes(chosenSpecialty))) { message.textContent = 'Choose the tool specialty it supports in the active catalogue.'; return; }
    tools.push({ tool_id: tool.id, activities, specialty_slug: chosenSpecialty || undefined,
      provider_id: tool.provider_id, offering_id: tool.offering_id || undefined, subscription_pricing_id: subscription || undefined, usage_pricing_id: usage || undefined,
      usage_quantity: $('tool-quantity').value || '0', included_allowance_remaining: $('tool-allowance').value || undefined,
      subscription_purchased_for_project: $('tool-purchased').checked, __videoScriptwriting: !!scriptToolSelected });
    renderLists(); message.textContent = '';
  });
  const fillOverheadPrices = () => {
    const category = $('overhead-category').value, select = $('overhead-price');
    setSelectMessage(select, 'Manual project estimate', false);
    productionOverheads.filter((p) => p.category === category).forEach((p) => select.add(new Option(`${p.name} · ${p.method.replaceAll('_', ' ')} · ${p.rate} ${p.currency}/${p.unit || p.method}`, p.id)));
  };
  fillOverheadPrices(); $('overhead-category').addEventListener('change', fillOverheadPrices);
  $('add-overhead').addEventListener('click', () => {
    const priceId = $('overhead-price').value, amount = $('overhead-amount').value;
    if (!priceId && amount === '') { message.textContent = 'Choose a configured overhead rate or enter your project amount.'; return; }
    overheads.push({ category: $('overhead-category').value, pricing_id: priceId || undefined, user_amount: amount || undefined,
      quantity: $('overhead-quantity').value || undefined, name: $('overhead-name').value.trim() || undefined });
    $('overhead-amount').value = ''; $('overhead-quantity').value = ''; $('overhead-name').value = ''; renderLists(); message.textContent = '';
  });

  const selectedModels = () => components.map((c) => ({ ...c }));
  const makePayload = () => {
    if (videoGenerationMode) {
      const brief = $('vg-brief').value.trim(), method = document.querySelector('input[name="vg-script-method"]:checked').value;
      if (!brief) throw new Error('Enter a video brief before calculating.');
      if (!$('vg-script').value.trim()) throw new Error('Write or paste a script before calculating the production estimate.');
      if (!(Number($('vg-finished-duration').value) > 0)) throw new Error('Enter the target finished video duration.');
      if (!videoScenes.length) throw new Error('Add at least one scene before calculating.');
      if (method === 'ai_assisted' && !$('vg-script-tool').value) throw new Error('Choose a configured scriptwriting tool for AI-assisted preparation.');
      if (method === 'ai_assisted' && !tools.some((tool) => tool.tool_id === $('vg-script-tool').value && tool.activities.includes('script'))) throw new Error('Add the selected scriptwriting tool and its verified allocation under Production tools.');
      if (method === 'self_written') tools.splice(0, tools.length, ...tools.filter((item) => !item.__videoScriptwriting));
    }
    const payload = { components: selectedModels(), operations: operations.map((o) => ({ ...o })), tools: tools.map((x) => ({ ...x })), overheads: overheads.map((x) => ({ ...x })), output_currency: $('currency').value, credit_cost_basis: $('credit-basis').value,
      production: { desired_final_duration_seconds: $('final-duration').value, expected_usable_duration_seconds: $('usable-duration').value }, project_hours: $('project-hours').value };
    if (videoGenerationMode) {
      payload.calculator_type = 'video_generation';
      payload.video_generation = { schema_version: 1, title: $('vg-title').value.trim(), video_brief: $('vg-brief').value.trim(),
        purpose: $('vg-purpose').value.trim(), target_audience: $('vg-audience').value.trim(), destination_platform: $('vg-platform').value.trim(),
        aspect_ratio: $('vg-aspect').value.trim(), output_resolution: $('vg-resolution').value.trim(), target_finished_duration_seconds: $('vg-finished-duration').value,
        visual_style: $('vg-style').value.trim(), production_instructions: $('vg-instructions').value.trim(),
        script_preparation_method: document.querySelector('input[name="vg-script-method"]:checked').value,
        tone: $('vg-tone').value.trim(), narrative_direction: $('vg-narrative').value.trim(), script_directions: $('vg-script-directions').value.trim(),
        script: $('vg-script').value, scriptwriting_tool_id: $('vg-script-tool').value || null,
        scenes: videoScenes.map((scene, index) => ({ ...scene, sequence: index + 1 })) };
      payload.production.desired_final_duration_seconds = $('vg-finished-duration').value;
      payload.tools = tools.map(({ __videoScriptwriting, ...item }) => item);
    }
    const markup = $('markup').value;
    const margin = $('margin').value;
    if (markup && margin) throw new Error('Choose markup or target margin, not both.');
    if (markup) payload.markup_percentage = markup;
    if (margin) payload.target_margin_percentage = margin;
    const project = $('project')?.value || app.dataset.projectId;
    if (project) payload.project_id = project;
    return payload;
  };

  const renderResult = (data) => {
    const panel = $('result-panel'); panel.hidden = false;
    const status = data.status || 'unavailable';
    $('result-status').textContent = status === 'complete' ? `Complete planning estimate · ${data.output_currency}` : `Incomplete estimate · ${data.output_currency || ''}`;
    const summary = $('result-summary'); summary.replaceChildren();
    const commercial = data.commercial || {};
    const metrics = [
      ['Estimated production cost', commercial.total_estimated_production_cost != null ? fmt(commercial.total_estimated_production_cost, commercial.currency) : 'Not available'],
      ['Known partial cost', commercial.known_partial_cost != null ? fmt(commercial.known_partial_cost, commercial.currency) : '—'],
      ['Suggested selling price', commercial.suggested_selling_price != null ? fmt(commercial.suggested_selling_price, commercial.currency) : 'Not available'],
      ['Estimated gross profit', commercial.gross_profit != null ? fmt(commercial.gross_profit, commercial.currency) : 'Not available'],
      ['Estimated gross margin', commercial.gross_margin_percentage != null ? `${commercial.gross_margin_percentage}%` : '—'],
      ['Model / provider cost', fmt(commercial.ai_provider_cost, commercial.currency)],
      ['Optional service cost', fmt(commercial.optional_service_cost, commercial.currency)],
      ['Production tool cost', fmt(commercial.production_tool_cost, commercial.currency)],
      ['Production overhead', fmt(commercial.production_overhead_cost, commercial.currency)],
      ['Additional cash expenditure', fmt(commercial.additional_cash_expenditure, commercial.currency)],
      ['Cost per finished video', fmt(commercial.cost_per_finished_video, commercial.currency)],
      ['Cost per finished video second', fmt(commercial.cost_per_finished_video_second, commercial.currency)],
      ['Credits consumed', data.summary?.credits_consumed ?? '—'],
    ];
    metrics.forEach(([label, value]) => { const card = document.createElement('article'); card.className = 'result-metric'; addText(card, 'span', label); addText(card, 'strong', value); summary.appendChild(card); });
    const details = $('result-details'); details.replaceChildren();
    if (videoGenerationMode && lastPayload?.video_generation) {
      const project = lastPayload.video_generation, section = document.createElement('section'); addText(section, 'h3', 'Video project summary');
      addText(section, 'p', `${project.title || 'Untitled video'} · ${project.purpose || 'Purpose not specified'} · ${project.target_audience || 'Audience not specified'}`);
      addText(section, 'p', project.video_brief);
      addText(section, 'p', `Script preparation: ${project.script_preparation_method === 'ai_assisted' ? 'external AI assistant; script pasted by customer' : 'customer written'}. Target finished duration: ${project.target_finished_duration_seconds}s. Planned scene duration: ${project.total_planned_scene_duration_seconds || project.scenes.reduce((sum, scene) => sum + Number(scene.planned_duration_seconds || 0), 0)}s. Planned billable generation duration: ${data.summary?.billable_generated_seconds ?? 'not available'}s.`);
      addText(section, 'p', `Script: ${project.script || 'No script supplied'}${project.script_directions ? ` · Directions: ${project.script_directions}` : ''}`);
      project.scenes.forEach((scene, index) => addText(section, 'p', `Scene ${index + 1}${scene.title ? ` · ${scene.title}` : ''}: ${scene.description} · ${scene.planned_duration_seconds}s`));
      if (project.scriptwriting_tool_id) { const tool = productionTools.find((item) => item.id === project.scriptwriting_tool_id); addText(section, 'p', `Selected scriptwriting tool: ${tool ? `${tool.provider} · ${tool.name}` : 'Configured tool'}; its allocation appears under production tools.`); }
      details.appendChild(section);
    }
    const missing = commercial.missing_information || data.missing_information || [];
    if (missing.length) { const section = document.createElement('section'); addText(section, 'h3', 'What is missing'); const list = document.createElement('ul'); missing.forEach((item) => addText(list, 'li', item)); section.appendChild(list); details.appendChild(section); }
    const costGroups = [['Model components', data.model_costs || []], ['Optional services', data.operation_costs || []], ['Production tools', data.production_tool_costs || []], ['Production overheads', data.production_overheads || []]];
    costGroups.forEach(([title, rows]) => { const section = document.createElement('section'); addText(section, 'h3', title); if (!rows.length) addText(section, 'p', 'None configured.'); rows.forEach((row) => {
      const identity = row.model ? `${row.specialty?.name ? `${row.specialty.name} · ` : ''}${row.model.provider} · ${row.model.name} v${row.model.version} · ${row.workflow?.name || 'workflow'}${row.offering?.name ? ` · ${row.offering.name}` : ''}${row.access_route?.name ? ` · ${row.access_route.name}` : ''}${Object.keys(row.configuration || {}).length ? ` · config ${JSON.stringify(row.configuration)}` : ''}` : `${row.label || row.operation || 'Service'}`;
      const method = row.pricing_method || row.method || 'pricing unavailable';
      const native = row.original_base_cost != null ? ` · source ${row.original_base_cost} ${row.original_currency || row.currency || ''}` : '';
      const fx = row.exchange_rate ? ` · FX ${row.exchange_rate.rate} (${row.exchange_rate.base_currency}/${row.exchange_rate.quote_currency}, ${row.exchange_rate.effective_at || 'date unavailable'})` : '';
      const credits = row.credits_consumed != null ? ` · ${row.credits_consumed} credits consumed` : '';
      const retry = row.retry_output_cost != null ? ` · retry allowance ${row.retry_output_cost} ${commercial.currency || ''}` : '';
      const base = row.base_output_cost != null ? ` · base ${row.base_output_cost} ${commercial.currency || ''}` : '';
      const line = `${identity} · ${method} · ${row.status || ''} · ${row.known_cost ?? 'unpriced'} ${commercial.currency || ''}${base}${retry}${native}${fx}${credits}${row.additional_cash_cost != null ? ` · additional cash ${row.additional_cash_cost}` : ''}${row.billable_usage_quantity != null ? ` · billable quantity ${row.billable_usage_quantity}` : ''}${row.source ? ` · ${row.source}` : ''}`;
      addText(section, 'p', line);
    }); details.appendChild(section); });
    if (Object.keys(commercial.pricing_basis || {}).length) addText(details, 'p', `Selling price assumption: ${JSON.stringify(commercial.pricing_basis)}`, 'field-note');
    if (data.warnings?.length) { const section = document.createElement('section'); addText(section, 'h3', 'Notes'); data.warnings.forEach((item) => addText(section, 'p', item)); details.appendChild(section); }
    const semantics = data.input_semantics || 'Costs are estimates based on configured pricing and the assumptions entered above.';
    addText(details, 'p', semantics, 'field-note');
    $('save-result-note').textContent = data.estimate_id ? `Saved as a new historical estimate (${data.estimate_id}).` : 'This estimate is not saved. Select a project and calculate again, or sign in to save it.';
    if (data.estimate_id) { const a = document.createElement('a'); a.href = `/workspace/estimates/${encodeURIComponent(data.estimate_id)}/`; a.textContent = 'Open saved estimate'; a.className = 'button button-secondary'; $('save-result-note').append(' ', a); }
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  $('calculate').addEventListener('click', async () => {
    if (!components.length) { message.textContent = 'Add at least one model component before calculating.'; return; }
    let payload;
    try { payload = makePayload(); } catch (error) { message.textContent = error.message; return; }
    lastPayload = payload;
    message.textContent = 'Calculating from the current registry…';
    $('calculate').disabled = true;
    try {
      const response = await fetch(app.dataset.calcUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok && response.status !== 422) { message.textContent = data.error || 'The estimate could not be calculated.'; return; }
      message.textContent = '';
      renderResult(data);
      if (!data.estimate_id) {
        const save = document.createElement('button'); save.type = 'button'; save.className = 'button button-secondary'; save.textContent = 'Sign in to save this estimate';
        save.addEventListener('click', () => { sessionStorage.setItem('videoCalculatorEstimate', JSON.stringify(payload)); const next = `${location.pathname}?resume=1`; location.href = `${app.dataset.loginUrl}?next=${encodeURIComponent(next)}`; });
        $('save-result-note').append(' ', save);
      }
    } catch { message.textContent = 'Network error while calculating. Please try again.'; }
    finally { $('calculate').disabled = false; }
  });

  $('new-project-for-estimate')?.addEventListener('click', () => {
    try {
      if (components.length) sessionStorage.setItem('videoCalculatorEstimate', JSON.stringify(makePayload()));
    } catch { /* Continue project creation even if local storage is unavailable. */ }
  });

  const operationSelect = $('operation');
  fetch('/pricing/api/operations/').then((r) => r.json()).then((data) => {
    (data.results || []).forEach((item) => operationSelect.add(new Option(`${item.label} (${item.currency}/${item.unit})`, item.operation_key)));
    if (!(data.results || []).length) operationSelect.options[0].textContent = 'No effective optional service prices configured';
  }).catch(() => { operationSelect.options[0].textContent = 'Service price list unavailable'; });

  if (starting) {
    $('currency').value = starting.output_currency || $('currency').value;
    $('markup').value = starting.markup_percentage ?? '';
    $('margin').value = starting.target_margin_percentage ?? '';
    $('credit-basis').value = starting.credit_cost_basis || 'marginal_cash';
    if (videoGenerationMode) {
      $('final-duration').value = starting.production?.desired_final_duration_seconds || $('final-duration').value;
      $('usable-duration').value = starting.production?.expected_usable_duration_seconds ?? '0';
      $('project-hours').value = starting.project_hours || '0';
      operations.push(...(starting.operations || [])); tools.push(...(starting.tools || []).map((tool) => ({ ...tool,
        __videoScriptwriting: starting.video_generation?.script_preparation_method === 'ai_assisted' && tool.tool_id === starting.video_generation.scriptwriting_tool_id }))); overheads.push(...(starting.overheads || []));
      if (starting.components?.[0]) restoreVideoSelection(starting.components[0]);
    } else {
    (starting.components || []).forEach((source) => {
      const model = models.find((item) => item.id === source.video_model_id);
      if (!model) return;
      const copy = { ...source, label: `${model.provider} · ${model.name} v${model.version}` };
      delete copy.pricing_record_id;
      delete copy.actual_attempts;
      delete copy.successful_attempts;
      delete copy.failed_attempts;
      components.push(copy);
    });
    if (starting.components?.[0]) {
      const source = starting.components[0];
      const model = models.find((item) => item.id === source.video_model_id);
      if (model) {
        $('provider').value = model.provider; $('provider').dispatchEvent(new Event('change'));
        modelSelect.value = model.id; modelSelect.dispatchEvent(new Event('change'));
        workflowSelect.value = source.workflow_slug || '';
      }
      $('clip-count').value = source.clip_count || 1;
      $('requests').value = source.generation_requests || 1;
      $('duration').value = source.duration_seconds || 5;
    }
    }
  }
  const clipPlan = new URLSearchParams(location.search);
  const clipCountFromPlan = Number(clipPlan.get('clip_count'));
  const avgDurationFromPlan = Number(clipPlan.get('duration_seconds'));
  if (Number.isInteger(clipCountFromPlan) && clipCountFromPlan > 0 && Number.isFinite(avgDurationFromPlan) && avgDurationFromPlan > 0) {
    $('clip-count').value = clipCountFromPlan;
    $('requests').value = clipCountFromPlan;
    $('duration').value = avgDurationFromPlan.toFixed(2);
    const note = $('clip-plan-note');
    note.textContent = `Clip plan carried forward: ${clipCountFromPlan} clips at an average ${avgDurationFromPlan.toFixed(2)} seconds each. The estimate uses this average duration. For a mixed-duration plan, add separate components for each duration group and choose their models independently.`;
    note.hidden = false;
  }
  if (app.dataset.resume === 'true') {
    const saved = sessionStorage.getItem('videoCalculatorEstimate');
    if (saved) {
      try {
        const payload = JSON.parse(saved);
        sessionStorage.removeItem('videoCalculatorEstimate');
        if (videoGenerationMode && payload.video_generation) {
          const v = payload.video_generation;
          const fields = {title:'vg-title',video_brief:'vg-brief',purpose:'vg-purpose',target_audience:'vg-audience',destination_platform:'vg-platform',aspect_ratio:'vg-aspect',output_resolution:'vg-resolution',target_finished_duration_seconds:'vg-finished-duration',visual_style:'vg-style',production_instructions:'vg-instructions',tone:'vg-tone',narrative_direction:'vg-narrative',script_directions:'vg-script-directions',script:'vg-script'};
          Object.entries(fields).forEach(([key,id]) => { if (v[key] != null) $(id).value = v[key]; });
          const methodRadio = document.querySelector(`input[name="vg-script-method"][value="${v.script_preparation_method}"]`); if (methodRadio) { methodRadio.checked = true; methodRadio.dispatchEvent(new Event('change')); }
          videoScenes.push(...(v.scenes || [])); redrawVideoScenes();
          $('final-duration').value = v.target_finished_duration_seconds || $('final-duration').value;
          if (v.scriptwriting_tool_id) { $('vg-script-tool').value = v.scriptwriting_tool_id; $('vg-script-tool').dispatchEvent(new Event('change')); }
        }
        if (payload.components?.length) {
          if (videoGenerationMode) {
            operations.push(...(payload.operations || [])); tools.push(...(payload.tools || []).map((tool) => ({ ...tool,
              __videoScriptwriting: payload.video_generation.script_preparation_method === 'ai_assisted' && tool.tool_id === payload.video_generation.scriptwriting_tool_id }))); overheads.push(...(payload.overheads || []));
            $('final-duration').value = payload.production?.desired_final_duration_seconds || $('final-duration').value;
            $('usable-duration').value = payload.production?.expected_usable_duration_seconds ?? '0';
            $('project-hours').value = payload.project_hours || '0';
            restoreVideoSelection(payload.components[0]);
            components.push(...payload.components.map((c) => ({ ...c, label: `${c.label || 'Saved model selection'}` })));
            renderLists(); message.textContent = 'Your estimate inputs and scene plan were restored after sign in. Review them and calculate again to save a new project record.';
          } else {
          const first = payload.components[0];
          const model = models.find((item) => item.id === first.video_model_id);
          if (model) {
            $('provider').value = model.provider; $('provider').dispatchEvent(new Event('change'));
            modelSelect.value = model.id; modelSelect.dispatchEvent(new Event('change'));
            workflowSelect.value = first.workflow_slug;
            setTimeout(() => { if (workflowSelect.value) workflowSelect.dispatchEvent(new Event('change')); }, 0);
          }
          components.push(...payload.components.map((c) => ({ ...c, label: models.find((m) => m.id === c.video_model_id) ? `${models.find((m) => m.id === c.video_model_id).provider} · ${models.find((m) => m.id === c.video_model_id).name} v${models.find((m) => m.id === c.video_model_id).version}` : 'Saved model selection' })));
          operations.push(...(payload.operations || []));
          $('currency').value = payload.output_currency || $('currency').value;
          $('markup').value = payload.markup_percentage || '';
          $('margin').value = payload.target_margin_percentage || '';
          $('credit-basis').value = payload.credit_cost_basis || 'marginal_cash';
          renderLists();
          message.textContent = 'Your previous estimate inputs have been restored. Select a project if you want to save the new estimate.';
          }
        }
      } catch { sessionStorage.removeItem('videoCalculatorEstimate'); }
    }
  }
  renderLists();
})();
