(() => {
  const root = document.getElementById('talking-flyer-calculator');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const toolsData = JSON.parse($('tf-tools-data')?.textContent || '[]');
  const overheadData = JSON.parse($('tf-overheads-data')?.textContent || '[]');
  const starting = JSON.parse($('tf-starting-data')?.textContent || 'null');
  const state = { step: 0, plan: null, narration: null, groups: new Map(), services: [], overheads: [], result: null, payload: null, busy: false };
  const safe = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const csrf = () => document.cookie.split('; ').find((x) => x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';
  const message = (text = '', kind = '') => { const el = $('tf-message'); el.textContent = text; el.className = `tf-message ${kind}`; };
  const alertBox = (target, text = '') => { target.textContent = text; target.hidden = !text; };
  const api = async (url, body) => {
    const response = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json', 'X-CSRFToken':csrf()}, body: JSON.stringify(body) });
    const data = await response.json();
    if ((!response.ok && !(response.status === 422 && data.status === 'incomplete')) || data.success === false) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  };
  const getJson = async (url) => { const response = await fetch(url, {credentials:'same-origin'}); const data = await response.json(); if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`); return data; };
  const step = (index) => {
    if (index > 0 && !state.plan) { message('Calculate a valid clip plan before continuing.', 'error'); return; }
    if (index > 1 && !selectedGroups().length) { message('Choose at least one active model version before continuing.', 'error'); return; }
    state.step = index;
    document.querySelectorAll('.tf-step').forEach((el) => { const active = Number(el.dataset.step) === index; el.hidden = !active; el.classList.toggle('is-active', active); });
    document.querySelectorAll('[data-progress]').forEach((el) => { const n = Number(el.dataset.progress); el.classList.toggle('is-current', n === index); el.classList.toggle('is-done', n < index); });
    message('');
    window.scrollTo({top: root.offsetTop - 16, behavior:'smooth'});
  };
  const invalidateEstimate = () => { state.result = null; $('tf-review-next').disabled = true; $('tf-save-estimate').disabled = true; $('tf-cost-result').hidden = true; };
  const wpm = () => $('tf-wpm').value === 'custom' ? $('tf-custom-wpm').value : $('tf-wpm').value;
  const selectedDurations = () => [...document.querySelectorAll('input[name="tf-duration"]:checked')].map((el) => Number(el.value));
  const invalidatePlan = () => { state.plan = null; state.narration = null; $('tf-plan-clips').disabled = true; $('tf-plan-summary').hidden = true; $('tf-clips').replaceChildren(); document.querySelector('[data-next]').disabled = true; invalidateEstimate(); };
  const countWords = (text) => text.trim() ? text.trim().split(/\s+/).length : 0;
  const renderTiming = (data) => { $('tf-timing').innerHTML = `<strong>${data.word_count} words</strong><span>${data.duration_display} estimated narration</span><span>${data.wpm} words per minute</span><p>This timing is calculated by the narration service from your script and selected speaking speed.</p>`; $('tf-timing').hidden = false; };

  $('tf-script').addEventListener('input', () => { $('tf-word-count').textContent = `${countWords($('tf-script').value).toLocaleString()} words`; invalidatePlan(); });
  $('tf-clear-script').addEventListener('click', () => { $('tf-script').value = ''; $('tf-script').dispatchEvent(new Event('input')); $('tf-timing').hidden = true; $('tf-script').focus(); });
  $('tf-wpm').addEventListener('change', () => { $('tf-custom-wpm-wrap').hidden = $('tf-wpm').value !== 'custom'; invalidatePlan(); });
  $('tf-custom-wpm').addEventListener('input', invalidatePlan);
  document.querySelectorAll('input[name="tf-duration"]').forEach((el) => el.addEventListener('change', invalidatePlan));
  $('tf-reserved').addEventListener('input', invalidatePlan);
  $('tf-time-script').addEventListener('click', async () => {
    if (!$('tf-script').value.trim()) { message('Enter a script before calculating narration timing.', 'error'); $('tf-script').focus(); return; }
    try { message('Calculating narration timing…'); const data = await api(root.dataset.narrationUrl, {text:$('tf-script').value, wpm:wpm()}); state.narration = data.data; renderTiming(data.data); message('Narration timing is ready.', 'success'); $('tf-plan-clips').disabled = false; }
    catch (error) { message(error.message, 'error'); }
  });
  $('tf-add-duration').addEventListener('click', () => {
    const input = $('tf-custom-duration'), value = Number(input.value);
    if (!Number.isInteger(value) || value < Number(root.dataset.minClipDuration || 1) || value > Number(root.dataset.maxClipDuration || 600)) { message('Enter a whole clip duration within the displayed limits.', 'error'); return; }
    if (document.querySelector(`input[name="tf-duration"][value="${value}"]`)) { message('That duration is already selected.', 'error'); return; }
    const label = document.createElement('label'); label.innerHTML = `<input type="checkbox" name="tf-duration" value="${value}" checked><span>${value} seconds (custom)</span>`; label.querySelector('input').addEventListener('change', invalidatePlan); $('tf-custom-duration').value = ''; document.querySelector('.tf-duration-list').append(label); invalidatePlan(); message('Custom clip duration added.', 'success');
  });
  $('tf-plan-clips').addEventListener('click', async () => {
    const script = $('tf-script').value.trim(), options = selectedDurations(), reserved = $('tf-reserved').value || '0';
    if (!script) { message('Enter a script before planning clips.', 'error'); return; }
    if (!options.length) { message('Select at least one clip duration.', 'error'); return; }
    if (!state.narration || state.narration.wpm !== Number(wpm())) {
      try { message('Calculating narration timing…'); const timed = await api(root.dataset.narrationUrl, {text:script, wpm:wpm()}); state.narration = timed.data; renderTiming(timed.data); }
      catch (error) { message(error.message, 'error'); return; }
    }
    try {
      message('Planning clips and checking script segments…');
      const data = await api(root.dataset.clipUrl, {narration:script, wpm:wpm(), clip_options:options.map((duration_seconds) => ({duration_seconds, reserved_seconds:reserved})), segmentation:{sentence_boundary_preference:true, sentence_boundary_tolerance:0.2}});
      if (!data.validation?.is_valid) throw new Error('The server could not validate the complete narration-to-clip assignment.');
      state.plan = data; renderPlan(data); renderToolOptions(); renderClipAssignments(); document.querySelector('[data-next]').disabled = false; invalidateEstimate(); message('Your clip plan is ready. Review each segment below.', 'success');
    } catch (error) { state.plan = null; message(error.message, 'error'); }
  });
  function renderPlan(data) {
    const p = data.plan, narration = data.narration;
    $('tf-timing').hidden = false; renderTiming(narration);
    $('tf-plan-summary').innerHTML = `<div><strong>${p.clip_count}</strong><span>recommended clips</span></div><div><strong>${p.total_generated_duration_seconds}s</strong><span>planned generated time</span></div><div><strong>${p.total_reserved_duration_seconds}s</strong><span>reserved time</span></div><div><strong>${p.total_usable_narration_duration_seconds}s</strong><span>usable narration time</span></div><div><strong>${p.total_unused_narration_duration_seconds}s</strong><span>unused narration capacity</span></div>`;
    $('tf-plan-summary').hidden = false;
    $('tf-clips').innerHTML = data.clips.map((clip) => `<article class="tf-clip"><div class="tf-clip-heading"><b>Clip ${clip.sequence_number}</b><span>${clip.generated_duration_seconds}s generated · ${clip.usable_narration_duration_seconds}s usable</span></div><p>${safe(clip.narration_text)}</p><small>${clip.word_count} words · ${clip.reserved_duration_seconds}s reserved · ${clip.unused_narration_duration_seconds}s remaining narration capacity</small></article>`).join('');
  }
  document.querySelectorAll('[data-next]').forEach((el) => el.addEventListener('click', () => step(state.step + 1)));
  document.querySelectorAll('[data-back]').forEach((el) => el.addEventListener('click', () => step(Math.max(0, state.step - 1))));

  const specialtyBoxes = [...document.querySelectorAll('#tf-specialty-choices input[type="checkbox"]')];
  specialtyBoxes.forEach((input) => input.addEventListener('change', () => { if (input.checked) createGroup(input.value, input.nextElementSibling.textContent.trim()); else removeGroup(input.value); renderToolOptions(); renderClipAssignments(); invalidateEstimate(); }));
  const selectedGroups = () => [...state.groups.values()].filter((group) => group.model);
  function removeGroup(slug) { state.groups.get(slug)?.element.remove(); state.groups.delete(slug); }
  function makeSelect(id, label) { return `<div class="tf-select-field"><label for="${id}">${label}</label><select id="${id}" disabled><option value="">Choose ${label.toLowerCase()}</option></select></div>`; }
  function createGroup(slug, name) {
    if (state.groups.has(slug)) return;
    const id = slug.replace(/[^a-z0-9-]/g, '-');
    const article = document.createElement('article'); article.className = 'tf-catalogue-group'; article.innerHTML = `<h3>${safe(name)}</h3><p class="tf-group-status">Loading active providers…</p><div class="tf-select-grid">${makeSelect(`tf-provider-${id}`, 'Provider')}${makeSelect(`tf-offering-${id}`, 'Offering')}${makeSelect(`tf-route-${id}`, 'Access route')}${makeSelect(`tf-plan-${id}`, 'Subscription plan (optional)')}${makeSelect(`tf-model-${id}`, 'Model version')}</div><div class="tf-config-fields" id="tf-config-${id}"></div><div class="tf-price-choice" id="tf-price-${id}"></div>`;
    $('tf-selection-groups').append(article); const group = {slug, id, name, element:article, model:null, config:{}, route:null, plan:null, prices:[], capabilities:[]}; state.groups.set(slug, group);
    const provider = $(`tf-provider-${id}`), offering = $(`tf-offering-${id}`), route = $(`tf-route-${id}`), plan = $(`tf-plan-${id}`), model = $(`tf-model-${id}`);
    getJson(root.dataset.providersUrl.replace('__specialty__', encodeURIComponent(slug))).then((data) => { fillSelect(provider, data.results, 'id', 'name', 'Choose provider'); if (!data.results.length) status(group, 'No active providers are configured for this specialty.'); }).catch((e) => status(group, e.message));
    provider.addEventListener('change', async () => {
      group.model=null; group.config={}; group.route=null; group.plan=null; clearAfter(provider); renderClipAssignments();
      if (!provider.value) return;
      try { const query = new URLSearchParams({specialty:slug, provider:provider.options[provider.selectedIndex].dataset.slug}); const data = await getJson(`${root.dataset.offeringsUrl}?${query}`); fillSelect(offering, data.results, 'id', 'name', 'Choose offering'); status(group, data.results.length ? 'Choose the access route and model supported by this offering.' : 'No active offerings match this specialty and provider.'); }
      catch (e) { status(group,e.message); }
      invalidateEstimate();
    });
    offering.addEventListener('change', async () => {
      group.model=null; group.route=null; group.plan=null; clearSelect(route,'Choose access route'); clearSelect(plan,'Choose subscription plan (optional)'); clearSelect(model,'Choose model version'); $(`tf-config-${id}`).replaceChildren(); $(`tf-price-${id}`).replaceChildren(); renderClipAssignments();
      if (!offering.value) return;
      try {
        const params = new URLSearchParams({specialty:slug, offering:offering.value});
        const [routes, plans] = await Promise.all([getJson(`${root.dataset.routesUrl}?${params}`), getJson(`${root.dataset.plansUrl}?${params}`)]);
        fillSelect(route,routes.results,'id','name',routes.results.length?'Choose access route':'No active access routes configured');
        fillSelect(plan,plans.results,'id','name','No subscription plan');
        if (routes.results.length) route.value=routes.results[0].id;
        await loadModels(); status(group, 'Only active model versions linked to this offering are shown.');
      } catch(e) { status(group,e.message); }
      invalidateEstimate();
    });
    route.addEventListener('change', () => { group.route=route.value || null; renderClipAssignments(); loadModels().catch((e)=>status(group,e.message)); invalidateEstimate(); });
    plan.addEventListener('change', () => { group.plan=plan.value || null; invalidateEstimate(); });
    model.addEventListener('change', () => { group.model=null; group.config={}; $(`tf-config-${id}`).replaceChildren(); $(`tf-price-${id}`).replaceChildren(); renderClipAssignments(); if(model.value) loadModelDetails(group, model.value).catch((e)=>status(group,e.message)); invalidateEstimate(); });
    async function loadModels() {
      group.model=null; clearSelect(model,'Loading model versions…');
      const params = new URLSearchParams({specialty:slug, provider:provider.options[provider.selectedIndex].dataset.slug, offering:offering.value}); if(route.value) params.set('access_route',route.value);
      const data=await getJson(`${root.dataset.modelsUrl}?${params}`); model.innerHTML='<option value="">Choose model version</option>'+data.results.map((item)=>`<option value="${safe(item.id)}" data-slug="${safe(item.slug)}" data-version="${safe(item.version)}" data-workflows="${safe(JSON.stringify(item.workflows||[]))}">${safe(item.name)} · ${safe(item.version)}</option>`).join('');model.disabled=false;
      if(!data.results.length) status(group,'No active model versions are configured for this offering and route.');
    }
  }
  function status(group, text) { group.element.querySelector('.tf-group-status').textContent=text; }
  function clearSelect(select, placeholder) { select.innerHTML=`<option value="">${safe(placeholder)}</option>`; select.disabled=true; }
  function clearAfter(select) { const group=state.groups.get([...state.groups.keys()].find((slug)=>slug.replace(/[^a-z0-9-]/g,'-')===select.id.replace('tf-provider-',''))); if(!group)return; for(const prefix of ['offering','route','plan','model']) clearSelect($(`tf-${prefix}-${group.id}`),`Choose ${prefix}`); $(`tf-config-${group.id}`).replaceChildren(); $(`tf-price-${group.id}`).replaceChildren(); }
  function fillSelect(select, rows, valueKey, labelKey, placeholder) { select.innerHTML=`<option value="">${safe(placeholder)}</option>`+rows.map((item)=>`<option value="${safe(item[valueKey])}" data-slug="${safe(item.slug || '')}">${safe(typeof labelKey==='function'?labelKey(item):item[labelKey])}</option>`).join(''); select.disabled=false; }
  async function loadModelDetails(group, modelId) {
    const select=$(`tf-model-${group.id}`), option=select.options[select.selectedIndex], providerSlug=$(`tf-provider-${group.id}`).options[$(`tf-provider-${group.id}`).selectedIndex].dataset.slug, modelSlug=option.dataset.slug;
    const capsUrl=root.dataset.capabilitiesTemplate.replace('__provider__',encodeURIComponent(providerSlug)).replace('__model__',encodeURIComponent(modelSlug));
    const query=new URLSearchParams({version:option.dataset.version || option.textContent.split('·').pop().trim()});
    const [capData, priceData]=await Promise.all([getJson(`${capsUrl}?${query}`),getJson(`${root.dataset.pricingUrl}?video_model_id=${encodeURIComponent(modelId)}${group.route?`&access_route=${encodeURIComponent(group.route)}`:''}`)]);
    const workflows=JSON.parse(option.dataset.workflows||'[]');
    group.model={id:modelId,provider:providerSlug,slug:modelSlug,version:query.get('version'), workflow:workflows[0]?.slug || '', name:option.textContent.split('·')[0].trim()};
    group.capabilities=capData.capabilities.filter((c)=>c.configuration?.selectable && ['select','number','boolean'].includes(c.configuration.input_type));
    group.prices=(priceData.results||[]).filter((p)=>group.route ? p.access_route?.id===group.route : !p.access_route);
    renderConfigurations(group); renderPriceChoice(group); status(group, group.capabilities.length?'Choose verified supported settings for this model version.':'This model has no verified configuration choices available.');
    renderClipAssignments(); invalidateEstimate();
  }
  function renderConfigurations(group) {
    const target=$(`tf-config-${group.id}`);
    target.innerHTML=group.capabilities.map((cap)=>{
      const conf=cap.configuration, id=`tf-conf-${group.id}-${cap.key}`;
      if(conf.input_type==='select') return `<div class="tf-select-field"><label for="${id}">${safe(cap.label)}</label><select id="${id}" data-config-key="${safe(cap.key)}"><option value="">Use default (if priced)</option>${conf.allowed_values.map((v)=>`<option value="${safe(v)}">${safe(v)}</option>`).join('')}</select></div>`;
      if(conf.input_type==='boolean') return `<label class="tf-boolean"><input type="checkbox" id="${id}" data-config-key="${safe(cap.key)}"><span>${safe(cap.label)}</span></label>`;
      return `<div class="tf-select-field"><label for="${id}">${safe(cap.label)}${cap.unit?` (${safe(cap.unit)})`:''}</label><input id="${id}" type="number" data-config-key="${safe(cap.key)}" min="${safe(conf.minimum_value??'')}" max="${safe(conf.maximum_value??'')}" step="any"></div>`;
    }).join('');
    target.querySelectorAll('[data-config-key]').forEach((el)=>el.addEventListener('change',()=>{group.config=readConfig(group); renderPriceChoice(group);invalidateEstimate();}));
  }
  function readConfig(group) { const data={}; $(`tf-config-${group.id}`).querySelectorAll('[data-config-key]').forEach((el)=>{ if(el.type==='checkbox'){if(el.checked)data[el.dataset.configKey]=true;} else if(el.value!=='')data[el.dataset.configKey]=el.type==='number'?String(el.value):el.value; });return data; }
  function renderPriceChoice(group) {
    group.config=readConfig(group); const box=$(`tf-price-${group.id}`), matching=group.prices.filter((p)=>Object.entries(p.configuration||{}).every(([k,v])=>String(group.config[k]??'')===String(v)) && Object.keys(p.configuration||{}).length===Object.keys(group.config).filter((k)=>group.config[k]!==undefined).length);
    if(!matching.length){box.innerHTML='<p class="tf-empty">No current price is configured for this access route and selected configuration. The estimate will be marked incomplete if you continue.</p>';group.priceId=null;return;}
    box.innerHTML=`<label for="tf-price-select-${group.id}">Pricing record</label><select id="tf-price-select-${group.id}">${matching.map((p)=>`<option value="${safe(p.id)}">${safe(p.method.replaceAll('_',' '))} · ${safe(p.rate)} ${safe(p.currency)} per ${safe(p.unit)} · ${safe(p.verification_status)}</option>`).join('')}</select>`;
    group.priceId=matching[0].id; $(`tf-price-select-${group.id}`).addEventListener('change',(e)=>{group.priceId=e.target.value;invalidateEstimate();});
  }
  function renderToolOptions() {
    const chosen=specialtyBoxes.filter((x)=>x.checked).map((x)=>x.value), target=$('tf-tool-options');
    const matches=toolsData.filter((tool)=>tool.specialties.some((slug)=>chosen.includes(slug)));
    if(!matches.length){target.innerHTML='<p class="tf-empty">No configured production tools match the selected specialties. Continue without them, or ask an administrator to configure a verified offering and price.</p>';return;}
    target.innerHTML=matches.map((tool)=>{
      const prices=tool.pricing||[], subs=prices.filter((p)=>p.cost_type==='subscription'), usage=prices.filter((p)=>p.cost_type==='usage');
      return `<article class="tf-tool-card"><label class="tf-tool-check"><input type="checkbox" data-tool="${safe(tool.id)}"><span><strong>${safe(tool.name)}</strong><small>${safe(tool.provider)} · ${safe(tool.activities.join(', '))}</small></span></label><div class="tf-tool-fields" data-tool-fields="${safe(tool.id)}" hidden><label>Subscription allocation<select data-sub="${safe(tool.id)}"><option value="">No subscription selected</option>${subs.map((p)=>`<option value="${safe(p.id)}">${safe(p.name)} · ${safe(p.rate)} ${safe(p.currency)} / month${p.included_quantity?` · ${safe(p.included_quantity)} included`:''}</option>`).join('')}</select></label><label>Usage price<select data-usage="${safe(tool.id)}"><option value="">No usage price selected</option>${usage.map((p)=>`<option value="${safe(p.id)}">${safe(p.name)} · ${safe(p.rate)} ${safe(p.currency)} / ${safe(p.unit)}</option>`).join('')}</select></label><label>Usage quantity<input type="number" data-quantity="${safe(tool.id)}" min="0" step="0.01" value="0"></label><label>Remaining included allowance<input type="number" data-allowance="${safe(tool.id)}" min="0" step="0.01" placeholder="Uses configured plan allowance"></label><label>Manual subscription allocation amount<input type="number" data-manual-allocation="${safe(tool.id)}" min="0" step="0.01" placeholder="Only needed for manual allocation"></label><label class="tf-boolean"><input type="checkbox" data-purchase="${safe(tool.id)}"><span>Buy subscription for this project</span></label></div></article>`;
    }).join('');
    target.querySelectorAll('[data-tool]').forEach((checkbox)=>checkbox.addEventListener('change',()=>{const fields=target.querySelector(`[data-tool-fields="${checkbox.dataset.tool}"]`);fields.hidden=!checkbox.checked;invalidateEstimate();})); target.querySelectorAll('select,input').forEach((el)=>el.addEventListener('change',invalidateEstimate));
  }
  function renderClipAssignments() {
    const target=$('tf-clip-assignments'), groups=selectedGroups();
    if(!state.plan||!groups.length){target.hidden=true;target.replaceChildren();return;}
    const old=new Map([...target.querySelectorAll('[data-clip-model]')].map((el)=>[el.dataset.sequence,el.value]));
    target.hidden=false; target.innerHTML='<h2>Assign clips to model versions</h2><p class="tf-help">Each clip is billed using its selected model’s effective pricing. Clips start on the first selected model; change assignments here when you use more than one.</p><div class="tf-clip-model-map">'+state.plan.clips.map((clip)=>{const value=old.get(String(clip.sequence_number));return `<label>Clip ${clip.sequence_number} · ${safe(clip.generated_duration_seconds)} seconds<select data-clip-model data-sequence="${clip.sequence_number}">${groups.map((g,i)=>`<option value="${safe(g.slug)}" ${value===g.slug||(!value&&i===0)?'selected':''}>${safe(g.name)} · ${safe(g.model.version)}</option>`).join('')}</select></label>`;}).join('')+'</div>';
    target.querySelectorAll('[data-clip-model]').forEach((el)=>el.addEventListener('change',invalidateEstimate));
  }

  let operationRows=[];
  getJson('/pricing/api/operations/').then((data)=>{operationRows=data.results||[];const select=$('tf-service-options');select.innerHTML='<option value="">Choose an optional service</option>'+operationRows.map((row)=>`<option value="${safe(row.id)}">${safe(row.label)} · ${safe(row.rate)} ${safe(row.currency)} per ${safe(row.unit)}</option>`).join(''); if(!operationRows.length)select.innerHTML='<option value="">No configured optional services</option>';}).catch(()=>{$('tf-service-options').innerHTML='<option value="">Optional service catalogue unavailable</option>';});
  $('tf-add-service').addEventListener('click',()=>{const id=$('tf-service-options').value,row=operationRows.find((x)=>x.id===id);if(!row){message('Select an available optional service.', 'error');return;}state.services.push({id:row.id,operation_key:row.operation_key,label:row.label,quantity:$('tf-service-quantity').value||'1'});renderServices();invalidateEstimate();});
  function renderServices(){ $('tf-selected-services').innerHTML=state.services.map((row,i)=>`<li>${safe(row.label)} · quantity ${safe(row.quantity)} <button type="button" data-remove-service="${i}" aria-label="Remove ${safe(row.label)}">Remove</button></li>`).join('');$('tf-selected-services').querySelectorAll('[data-remove-service]').forEach((b)=>b.addEventListener('click',()=>{state.services.splice(Number(b.dataset.removeService),1);renderServices();invalidateEstimate();})); }
  function updateOverheadRates(){ const cat=$('tf-overhead-category').value;const rows=overheadData.filter((row)=>row.category===cat);$('tf-overhead-rate').innerHTML='<option value="">Manual amount</option>'+rows.map((r)=>`<option value="${safe(r.id)}">${safe(r.name)} · ${safe(r.rate)} ${safe(r.currency)} per ${safe(r.unit||r.method)}</option>`).join(''); }
  $('tf-overhead-category').addEventListener('change',updateOverheadRates); updateOverheadRates();
  $('tf-add-overhead').addEventListener('click',()=>{const cat=$('tf-overhead-category').value,pricingId=$('tf-overhead-rate').value,amount=$('tf-overhead-amount').value,name=$('tf-overhead-name').value.trim();if(!pricingId&&amount===''){message('Choose a configured rate or enter a manual project amount.','error');return;} state.overheads.push({category:cat,pricing_id:pricingId||undefined,user_amount:pricingId?undefined:amount,name:name||undefined});renderOverheads();invalidateEstimate();});
  function renderOverheads(){ $('tf-overheads').innerHTML=state.overheads.map((row,i)=>`<li>${safe(row.name||row.category)} · ${row.user_amount!==undefined?`${safe(row.user_amount)} ${safe($('tf-currency').value)} (your estimate)`:'configured rate'} <button type="button" data-remove-overhead="${i}">Remove</button></li>`).join('');$('tf-overheads').querySelectorAll('[data-remove-overhead]').forEach((b)=>b.addEventListener('click',()=>{state.overheads.splice(Number(b.dataset.removeOverhead),1);renderOverheads();invalidateEstimate();})); }

  function buildPayload() {
    const groups=selectedGroups(); if(!groups.length) throw new Error('Select at least one verified model version.');
    const clips=state.plan.clips; const assignments=new Map();
    const selects=$('tf-clip-assignments').querySelectorAll('[data-clip-model]'); clips.forEach((clip,i)=>{const slug=selects[i]?.value||groups[0].slug;assignments.set(slug,[...(assignments.get(slug)||[]),clip.sequence_number]);});
    const components=groups.map((group)=>{
      const sequences=assignments.get(group.slug)||[];if(!sequences.length)return null;
      const durations=clips.filter((clip)=>sequences.includes(clip.sequence_number)).map((clip)=>clip.generated_duration_seconds);
      const average=durations.reduce((a,b)=>a+Number(b),0)/durations.length;
      const selectedPlan=$(`tf-plan-${group.id}`).value;
      const selectedOffering=$(`tf-offering-${group.id}`).value;
      const providerSelect=$(`tf-provider-${group.id}`);
      return {video_model_id:group.model.id,workflow_slug:group.model.workflow||undefined,specialty_slug:group.slug,provider_id:providerSelect.value,offering_id:selectedOffering,access_route_id:group.route||undefined,subscription_plan_id:selectedPlan||undefined,configuration:readConfig(group),pricing_record_id:group.priceId||undefined,clip_sequences:sequences,duration_seconds:String(average),generation_requests:durations.length,clip_count:durations.length,retry_allowance:0};
    }).filter(Boolean);
    if(components.length===0)throw new Error('Assign each clip to a selected model.');
    const selectedTools=toolsData.filter((tool)=>document.querySelector(`[data-tool="${tool.id}"]`)?.checked).map((tool)=>({
      tool_id:tool.id,offering_id:tool.offering_id||undefined,provider_id:tool.provider_id,
      specialty_slug:tool.specialties.find((slug)=>specialtyBoxes.some((box)=>box.checked&&box.value===slug)),activities:tool.activities,
      subscription_pricing_id:document.querySelector(`[data-sub="${tool.id}"]`)?.value||undefined,
      usage_pricing_id:document.querySelector(`[data-usage="${tool.id}"]`)?.value||undefined,
      usage_quantity:document.querySelector(`[data-quantity="${tool.id}"]`)?.value||'0',
      included_allowance_remaining:document.querySelector(`[data-allowance="${tool.id}"]`)?.value||undefined,
      manual_allocation:document.querySelector(`[data-manual-allocation="${tool.id}"]`)?.value||undefined,
      subscription_purchased_for_project:document.querySelector(`[data-purchase="${tool.id}"]`)?.checked||false,
      expected_monthly_projects:document.querySelector(`[data-sub="${tool.id}"] option:checked`)?.textContent.match(/(\d+) projects/ )?.[1]
    }));
    const payload={calculator_type:'talking_flyer',talking_flyer:{schema_version:1,script:state.narration.normalized_text,word_count:state.narration.word_count,narration_wpm:state.narration.wpm,narration_duration_seconds:state.narration.duration_seconds,clip_plan:{schema_version:1,clip_count:clips.length,clips:clips.map((clip)=>({sequence:clip.sequence_number,word_count:clip.word_count,text:clip.narration_text,duration_seconds:clip.generated_duration_seconds,reserved_duration_seconds:clip.reserved_duration_seconds,usable_duration_seconds:clip.usable_narration_duration_seconds})),total_planned_generated_duration_seconds:state.plan.plan.total_generated_duration_seconds,total_reserved_duration_seconds:state.plan.plan.total_reserved_duration_seconds,total_usable_duration_seconds:state.plan.plan.total_usable_narration_duration_seconds}},components,operations:state.services.map((row)=>({operation_key:row.operation_key,quantity:row.quantity,pricing_record_id:row.id})),tools:selectedTools,overheads:state.overheads,output_currency:$('tf-currency').value,project_hours:$('tf-project-hours').value||'0',production:{desired_final_duration_seconds:$('tf-final-duration').value||state.plan.plan.total_usable_narration_duration_seconds,expected_usable_duration_seconds:state.plan.plan.total_usable_narration_duration_seconds}};
    if($('tf-markup').value!=='')payload.markup_percentage=$('tf-markup').value;
    return payload;
  }
  $('tf-calculate-cost').addEventListener('click',async()=>{
    alertBox($('tf-cost-error'));try{if(!state.plan)throw new Error('Create a clip plan before calculating production cost.');state.payload=buildPayload();message('Resolving catalogue prices and calculating…');$('tf-calculate-cost').disabled=true;$('tf-calculate-cost').textContent='Calculating…';const data=await api(root.dataset.estimateUrl,state.payload);state.result=data;renderCost(data);$('tf-review-next').disabled=false;$('tf-save-estimate').disabled=false;message(data.status==='complete'?'Estimate calculated.':'Estimate is incomplete because some catalogue prices or exchange rates are missing.',data.status==='complete'?'success':'warning');}catch(error){alertBox($('tf-cost-error'),error.message);message('Review the highlighted assumptions and try again.','error');}finally{$('tf-calculate-cost').disabled=false;$('tf-calculate-cost').textContent='Calculate production cost';}});
  function renderCost(data){const c=data.commercial, cur=data.output_currency;const val=(x)=>x==null?'Not available':`${safe(x)} ${safe(cur)}`;const rows=[['Estimated production cost',c.total_estimated_production_cost!=null?val(c.total_estimated_production_cost):`Incomplete · known portion ${val(c.known_partial_cost)}`],['Cash expenditure',val(c.additional_cash_expenditure)],['Allocated production-tool subscriptions',val(c.production_tool_cost)],['Optional service costs',val(c.optional_service_cost)],['Operational overheads',val(c.production_overhead_cost)],['Cost per finished video',val(c.cost_per_finished_video)],['Cost per finished second',c.cost_per_finished_video_second?`${val(c.cost_per_finished_video_second)} / second`:'Not available'],['Suggested selling price',val(c.suggested_selling_price)],['Estimated gross profit',val(c.gross_profit)],['Estimated gross margin',c.gross_margin_percentage==null?'Not available':`${safe(c.gross_margin_percentage)}%`]];
    const fx=[...(data.model_costs||[]),...(data.operation_costs||[]),...(data.production_tool_costs||[])].flatMap((line)=>line.exchange_rate?[line.exchange_rate]:line.fx||[]);
    $('tf-cost-result').hidden=false;$('tf-cost-result').innerHTML=`<div class="tf-result-banner ${data.status==='complete'?'is-complete':'is-incomplete'}"><strong>${data.status==='complete'?'Estimate ready':'Incomplete estimate'}</strong><span>${data.status==='complete'?'All required prices are available.':'Missing prices or exchange rates are not treated as zero.'}</span></div><div class="tf-cost-grid">${rows.map(([a,b])=>`<div><span>${safe(a)}</span><strong>${b}</strong></div>`).join('')}</div><h3>Cost breakdown</h3>${[['Model/API usage',data.model_costs],['Subscriptions and additional usage',data.production_tool_costs],['Optional production services',data.operation_costs],['Project overheads',data.production_overheads]].map(([name,lines])=>`<section class="tf-breakdown"><h4>${safe(name)}</h4>${(lines||[]).length?(lines||[]).map((line)=>`<p><b>${safe(line.model?.name||line.name||line.label||line.operation||line.category||'Selected cost')}</b> · ${safe(line.known_cost??line.base_output_cost??line.allocation??'Incomplete')} ${safe(cur)} · ${safe(line.status||'priced')}${line.verification_status?` · ${safe(line.verification_status)}`:''}</p>`).join(''):'<p>None selected.</p>'}</section>`).join('')}<h3>Currency and exchange-rate assumptions</h3><p>${fx.length?fx.map((rate)=>`1 ${safe(rate.base_currency)} = ${safe(rate.rate)} ${safe(rate.quote_currency)} (${safe(rate.verification_status||'unverified')})`).join('<br>'):'No conversion was required or an exchange rate is unavailable.'}</p>${data.missing_information?.length?`<div class="tf-alert"><b>Missing information</b><ul>${data.missing_information.map((x)=>`<li>${safe(x)}</li>`).join('')}</ul></div>`:''}${data.warnings?.length?`<p class="tf-note">${data.warnings.map(safe).join('<br>')}</p>`:''}`; $('tf-review-summary').innerHTML=`<p>${safe(state.narration.word_count)} words · ${safe(state.narration.duration_display)} narration · ${safe(state.plan.plan.clip_count)} planned clips · ${safe(state.plan.plan.total_generated_duration_seconds)} generated seconds · ${safe(data.status)} estimate.</p><p>Specialties: ${safe(specialtyBoxes.filter((x)=>x.checked).map((x)=>x.nextElementSibling.textContent.trim()).join(', ')||'None selected')}.</p><p>Selected tools: ${safe(toolsData.filter((tool)=>document.querySelector(`[data-tool="${tool.id}"]`)?.checked).map((tool)=>tool.name).join(', ')||'None')}.</p><p>${safe(selectedGroups().map((g)=>`${g.name} ${g.model.version}`).join(', '))}</p><p>${val(c.total_estimated_production_cost)} estimated production cost · ${val(c.additional_cash_expenditure)} cash expenditure.</p>`;}
  $('tf-review-next').addEventListener('click',()=>step(3));
  $('tf-recalculate').addEventListener('click',()=>{invalidateEstimate();step(2);});
  $('tf-save-estimate').addEventListener('click',async()=>{try{if(!state.payload||!state.result)throw new Error('Calculate the estimate before saving.');$('tf-save-estimate').disabled=true;message('Preparing your estimate for project saving…');const data=await api(root.dataset.saveUrl,state.payload);window.location.assign(data.next_url);}catch(e){message(e.message,'error');$('tf-save-estimate').disabled=false;}});

  if(starting?.talking_flyer){const source=starting.talking_flyer;$('tf-script').value=source.script||'';$('tf-word-count').textContent=`${countWords($('tf-script').value).toLocaleString()} words`;$('tf-wpm').value=[120,135,150,165,180].includes(Number(source.narration_wpm))?String(source.narration_wpm):'custom';if($('tf-wpm').value==='custom'){$('tf-custom-wpm-wrap').hidden=false;$('tf-custom-wpm').value=source.narration_wpm;}const durations=new Set((source.clip_plan?.clips||[]).map((c)=>Number(c.duration_seconds)));document.querySelectorAll('input[name="tf-duration"]').forEach((el)=>{el.checked=durations.has(Number(el.value));});$('tf-wpm').dispatchEvent(new Event('change'));$('tf-time-script').click();message('Saved script and narration settings restored. Re-plan clips and reselect current catalogue prices to create a new estimate.','success');}
})();
