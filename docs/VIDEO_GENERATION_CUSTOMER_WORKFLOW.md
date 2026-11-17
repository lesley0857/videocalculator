# Video Generation customer workflow

The customer-facing Video Generation Calculator is mounted at
`/calculators/video-generation/`. It is a separate product from Talking Flyer and
uses the shared Task 009 catalogue and production-cost engine.

Customers enter a video brief, choose a self-written or externally AI-assisted
script workflow, edit an ordered scene list, select a registered video specialty,
provider, offering, access route, model version, and verified supported
configuration, then set generation quantities and cost assumptions. Optional
production tools/services and overheads are included only when selected.

AI assistance prepares a provider-neutral prompt in the browser for the customer
to copy into a separately opened provider. No AI or media generation API is
called. The customer pastes the returned script into the calculator. Self-written
scripts do not select a scriptwriting cost by default.

The version 1 `video_generation` contract snapshots project metadata, script
preparation, and ordered scenes. It calculates scene duration from scene inputs
and validates that the contract's finished-duration target matches the shared
production assumptions. Scene duration and model-billable generated duration
remain separate values; the shared pricing engine applies each selected model's
effective billing method, minimums, subscription allocations, configured
overheads, and FX records.

Guest estimates are calculated without persistence. The browser retains estimate
inputs through the sign-in/registration return path; an authenticated customer
can select an owned active project or create one and calculate a new immutable
estimate. Reuse restores the saved brief and scene plan as a starting point and
resolves current active catalogue/pricing records for the new calculation.
