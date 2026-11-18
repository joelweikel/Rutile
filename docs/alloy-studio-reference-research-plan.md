# Alloy Studio reference research plan

Add **Find missing data** to the Alloy Studio Inspector. A connected agent can research several missing properties across a solved phase set in one run. It checks saved research, searches for sources, downloads the files it needs, and runs Python to extract or calculate candidate values. Rutile presents the candidates for review, then applies the selected records and refreshes the affected results using the saved equilibrium.

The batch workflow, stdio MCP bridge, persistent evidence, and review controls are implemented. The optional host launchers use documented Pi and Codex protocols and require a configured local isolation profile. See the setup guide for supported behavior. [Reference research setup](reference-research.md) · [Phase Data](processing.md#phase-assignment)

## Scope and architecture

Start with **density and elastic stiffness across the solid phases in one completed equilibrium result**. Cover disordered BCC, FCC, and HCP solutions where the source establishes the phase identity. Track bulk and shear moduli separately within an elasticity target. Grain size, strength, hardness, and processed-alloy properties follow their own models and are outside this work.

**The agent host runs the research.** Use a local MCP-capable host with web search, download, and Python capabilities. The host chooses queries, follows papers and supplements, and runs Python in a dedicated research directory. Verify Codex and Pi as hosts. Their configured models, accounts, and permissions apply to their own sessions.

**Rutile owns the scientific context and the graph.** Add a thin local stdio MCP adapter for the research tools. It calls narrowly scoped endpoints on the existing loopback FastAPI server, which in turn call ordinary Python services. The Inspector calls the same services through the browser API. Keep research state independent of the single active scientific job slot so that searching and downloading can run while a solver job executes. [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) · [Rutile architecture](architecture.md)

Rutile needs no OpenAI API key for the Codex path. A future in-app runner could use OpenAI API or a local `llama-server` with a compatible tool-calling model and reuse the same request and proposal schemas. Both would need their own research execution and retrieval setup. No model provider is required for the scientific application itself. [Codex authentication](https://learn.chatgpt.com/docs/auth) · [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)

## User workflow

1. **Choose what to research.** **Find missing data** lists missing density and elasticity across the active phase set with checkboxes for each target. **Find reference** opens the same flow with one target selected. Show the phase label, actual atomic fractions, temperature, pressure, and reason for each gap. Preview the selected context before sending it to the agent. Keep manual Phase Data entry available.
2. **Hand off via MCP.** Create a research request and a dedicated scratch directory. **Copy research task** gives the user the request ID, task objective, and instructions to paste into a connected agent host. The host calls Rutile through MCP to get the phase context. The copied text contains no credentials. Setup instructions explain how to open the research directory and connect the local MCP server.
3. **Collect evidence.** Check applicable local models and saved research first. Group related targets so a Materials Project query, reference paper, or download can serve multiple targets. Use the host’s search for literature on the actual solution phase. Follow a DOI, report, or supplement to the value or equation. Identify the table, figure, or equation that supplies each input. A host with search alone can still return cited leads.
4. **Extract or calculate.** Write a short Python script when a table, supplementary file, or published equation needs processing. Use the solved composition and stated conditions. Save the script, its inputs, execution environment, and a machine-readable result in the scratch directory. If the data support only a related composition or structure, record the candidate and explain the gap. Return the evidence already found when part of the request remains unresolved.
5. **Review in the Inspector.** Group candidates by phase and property. Show value, units, source location, original and target conditions, measured or computed origin, assumptions, and applicability. Each target can be ready for review, unresolved, or still in progress. Show usable candidates as they arrive. Keep earlier drafts when a later lookup fails or the run is canceled.
6. **Apply selected results.** Validate the selected revisions against the current graph and phase conditions before writing the graph update. Create or update the connected Phase Data nodes and preserve existing fields outside the accepted changes. **Apply and rerun** schedules Phase Assignment once and refreshes the affected property branches with the same equilibrium job ID. A busy or failed calculation leaves the accepted records in place and the results visibly stale or failed.

## Contracts and persistence

| Record | Required contents |
| --- | --- |
| Research request | Schema version, request UUID, project and graph IDs, completed equilibrium job ID, assessment checksum, disclosure scope, and a list of selected targets. Each target has its own ID, phase instance, phase label, final atomic fractions, temperature in K, pressure in Pa, available structure and ordering evidence, requested property and units, and existing coverage or rejection reason. |
| Evidence item | Source ID, URL, DOI or MP ID when available, retrieval date, property and source conditions, exact page/table/figure/equation, and applicable access or reuse terms. For a local copy, retain its original name, checksum, and artifact ID. State when only an abstract or secondary source was accessible. |
| Proposal | Request ID, target ID, revision, evidence IDs per value, raw and normalized values with units, source and target phase conditions, the derivation or conversion, origin, applicability range, uncertainty if reported, and an explanation for any unresolved entry. Reference any extraction script and output by artifact ID and checksum. |
| Accepted record | Validated Phase Data, approved values and conditions, compact source and derivation summary, proposal revision and checksum, approval event, and the input fingerprint used for validation. Preserve usable values and citations in workflow export and run JSON. Include only references and checksums for raw evidence files in ordinary exports. |

The server builds a fingerprint for each target from the equilibrium artifact, assessment hash, phase instance, composition, conditions, and requested property. The browser also checks the current upstream job and phase input before editing the graph. Both checks matter because a phase instance ID can recur in different solves. Tie approval to the exact proposal revision and current target. A change to the target’s connected data calls for a new preview. UI retries reuse the same accepted records and avoid creating duplicate nodes.

Use the existing atomic JSON storage helpers for requests, drafts, and audit events. Intake copies validated artifacts to managed storage before a proposal is published. Store relative artifact IDs in results, with actionable feedback if a referenced artifact is missing. Preserve drafts across restart. Track target and draft status independently from solver status. Retry unresolved targets without repeating completed work.

## Research work folder and library

Keep research under the configured `RUTILE_WORKSPACE`, which defaults to `workspace/`. Each project gets a stable research directory so a host session can resume there. Generate `AGENTS.md` from a versioned Rutile template. It explains how to read the active request, check the library, label evidence and estimates, save a reproducible calculation, and submit drafts for review. Record the instruction version with each run.

```text
workspace/research/<project-id>/
  AGENTS.md
  library/                      saved sources and indexed research notes
  runs/<request-id>/
    scratch/                    downloaded files, scripts, notes, and outputs
    request.json
    proposals/
```

Expose only the active request’s writable scratch and relevant library records to the agent. Protect the instructions and managed records from agent writes. Treat saved research notes and downloaded files as evidence. Keep agent-authored files out of instruction and extension discovery, and permit script execution only within the scoped runtime. For Pi, which fixes the working directory when creating a session, resume from the stable project research directory and verify that each run gets fresh access to only the required files. [Pi sessions](https://docs.pi.dev/latest/sessions) · [Pi context files](https://docs.pi.dev/latest/configuration#context-files) · [Pi security](https://docs.pi.dev/latest/security)

Index saved evidence by chemical system, phase structure and ordering, property, composition and condition ranges, and DOI, MP ID, or artifact checksum. Keep useful papers, extracted tables, Python scripts and inputs, and notes about rejected sources. Store original provenance, including when a citation has no local copy. Keep draft leads identifiable alongside reviewed evidence. A later run looks up relevant records before going online, even in a new chat. Recheck applicability for each new phase or condition and recalculate a published model at the new point when supported. Reuse identical sources by checksum and keep their original attribution.

## MCP tools

Register the adapter as an opt-in local stdio server using the project virtual environment. Add the Python MCP dependency as an optional extra. Preserve the existing application startup and native JavaScript frontend.

| Proposed tool | Behavior |
| --- | --- |
| `get_reference_request` | Return the permitted phase and property targets, known coverage, relevant saved evidence, and the research-directory handle for an explicitly started request. Allow reading selected targets and limit how much evidence each call returns. Verify that the request belongs to the configured workspace and is eligible for agent access. |
| `search_materials_project` | Reuse the existing backend summary, explicit-ID, and elasticity lookups. Query by phase chemistry or supported material ID. Return structure, composition, property coverage, and query provenance. Preserve numeric/alphabetical ID aliases and handle missing credentials, rate limits, and truncated or ambiguous replies. Credentials stay in the running Rutile backend. |
| `stage_phase_data_proposal` | Submit a candidate or a documented unresolved result for a target in the batch. Pass the request and target IDs, values and units, source and target conditions, citations, derivation, applicability notes, and optional files from that request’s scratch directory. The server returns the proposal ID, revision, and validation results. |

**Staging creates a reviewable draft.** Rutile resolves the saved target, checks the payload and applicable phase constraints, normalizes supported units, and copies and hashes any attached files. It saves an immutable revision with the citations and flags whether the proposal is eligible to apply or contains leads that still need evidence. Invalid inputs get field-level feedback. The Inspector previews the proposed values and any changes to existing Phase Data. Applying the result is a separate action in Rutile.

MCP routes use an installation-local credential available to the trusted adapter, with request-scoped checks on every call. Pass the credential through protected process configuration and keep it out of prompts, tool results, browser storage, and the Python environment. Keep FastAPI bound to loopback and retain host and origin checks. Use separate authorization for the Inspector’s apply operation, which is outside the MCP tool set. [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

## Starting the agent

The host starts the research turn. A server can publish a prompt template such as `find_phase_reference(request_id)` for a compatible host to fetch and offer to the user. MCP prompt discovery and retrieval do not launch a new agent conversation on their own. **Copy research task** works with hosts that only support MCP tools. Sampling is a separate client-dependent capability for requesting model output during a request. It is deprecated in MCP 2026-07-28, so the research flow does not depend on it. [MCP prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts) · [MCP sampling](https://modelcontextprotocol.io/specification/2026-07-28/client/sampling)

When a scoped host is configured, select it under **Handoff** to start, resume, or cancel a research turn from Rutile. The agent calls the same MCP tools during the run. [Codex App Server](https://learn.chatgpt.com/docs/app-server) · [Pi RPC](https://docs.pi.dev/latest/rpc-commands)

### Session settings

| Setting | Behavior |
| --- | --- |
| **Always resume** | Continue the project's saved research conversation for the selected host. Start the first conversation if none exists. |
| **Always start fresh** | Start a new host conversation for each research batch. Load the current targets and matching library references. |
| **Start fresh after inactivity** | Resume if the previous research run in that conversation ended less than the configured idle time ago. Default to **30 minutes**. At or beyond that interval, the next batch starts a new conversation with its targets and relevant library references. |

Store the session choice, idle time, and last research run end time locally for each project and host. Scope the session to the project, configured launcher, and the launcher’s supplied account and permission scope. Measure inactivity from completion, cancellation, or failure of the last research run. An active run can continue past the idle interval. A second launch for the same project and host waits for the user to finish or stop the active run. If the saved session is missing or cannot resume, start fresh and load relevant research from disk. Show why Rutile starts a new session and keep the previous one available where the host supports it.

Automatic session selection uses Pi RPC’s `new_session` and `switch_session`, or Codex App Server’s `thread/start` and `thread/resume`. With **Copy research task**, the user chooses the existing or new chat. Leave context compaction to the host under its normal settings. [Pi RPC session commands](https://docs.pi.dev/latest/rpc-commands) · [Codex App Server](https://learn.chatgpt.com/docs/app-server)

Persist completed targets as they arrive. If a run stops, allow retrying pending targets under the same research request. Drafts and source files stay available across sessions.

## Scientific checks

- **Verify the phase and property.** Use evidence about structure, ordering, and phase composition. For a measurement reported for an alloy specimen, require a single-phase specimen with applicable composition and conditions before treating the value as a phase input. A multiphase, porous, textured, or condition-mismatched bulk value needs an applicable interpretation before it can fill a phase property.
- **Preserve the source conditions.** Store the source composition basis, temperature, and pressure separately from the requested point. Convert basis using identified atomic masses. Existing condition-match checks continue to govern scalar Phase Data. Treat a published equation as a computed estimate only after evaluating it for the actual requested conditions. Keep its reported or inferred fitting range and label extrapolation visibly before approval.
- **Use supported derivations.** Density can come from an applicable measurement, an assessed molar-volume model, or a lattice parameter with a verified number of atoms per unit cell. Elasticity can come from applicable bulk and shear moduli or a supported tensor reduction. Use trusted unit conversion, finite-value checks, and elastic stability checks in Rutile. Keep the original input alongside the conversion.
- **Distinguish leads from applicable values.** A plausible result from a search snippet, an unknown phase composition, or an inaccessible table remains a research lead. Enable **Apply** when the evidence and data support the target within the applicable rules. Offer an extrapolated model result only when the extrapolation is scientifically defensible and its limitation is visible in the preview and saved record.
- **Handle incomplete coverage.** A density-only proposal fills density. For elasticity, only activate a consistent pair of bulk and shear moduli from compatible evidence and conditions. Keep unsupported values unresolved. Retain uncertainty as unknown when the source provides none. Use the existing aggregate coverage rules and preserve measured, computed, and assumed origins.
- **Review reusable models as code.** A one-off script may produce a typed property value. A reusable volume, elasticity, or transport model requires a reviewed adapter, parameter provenance, a validity range, and independent verification before enabling it in scientific jobs.

## Execution and data boundaries

| Boundary | First-release behavior |
| --- | --- |
| Agent context | Share the minimum phase information needed. A cloud model sees data returned by its tools. Explain that disclosure before starting the request. Generate external search queries from the minimum useful terms and omit local filenames, raw TDBs, run logs, and unrelated graph contents. Stop the external path if the user declines to share the target context. |
| Downloads | Use the host’s web and download tools under its existing network permissions. Keep downloaded files in the request directory and open them as data. Rutile intake enforces bounded file count, size, and supported types. Keep a citation-only path when the host cannot save a file or the source’s terms or access prevent retention. Consider a dedicated download tool only if host testing shows a concrete retrieval gap. |
| Python execution | Use a verified host sandbox or isolated local runtime. Give it only the request’s files and runtime libraries, scratch write access, a filtered environment, and no network for Python and its children. Apply time and resource limits. Use trusted dependencies from the project environment or a prepared research environment. Confirm effective access on supported Windows configurations. If the required isolation is unavailable, stage the script for manual execution and report the limitation. |
| Untrusted text and files | Treat pages, paper text, metadata, and downloaded files as untrusted inputs. Render extracted text as text in the Inspector. Execute scripts authored for this task in the isolated runtime. Inspect archives and documents through bounded parsers. Resolve staged files inside the designated root, reject links and reparse-point escapes, and hash the bytes copied into managed storage. |
| Graph changes | Tool calls can read the shared request and stage evidence. Only a user action in Rutile applies a proposal to the graph. Validate the proposal again at apply time. Log the input fingerprint, artifact hashes, decision, and resulting job IDs. Keep proposed code out of the scientific worker’s execution path. |

Once a request starts, approved retrieval and isolated extraction can proceed without a prompt for every file or script. Codex web search, MCP connections, and browser access have separate controls from the command sandbox. Verify each enabled surface independently. Bound download size, file count, execution time, and retries at the service or runtime that enforces them. [Codex approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security) · [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)

## Build order and acceptance

| Stage | Deliverable | Acceptance |
| --- | --- | --- |
| 1. Batch requests and drafts | Pydantic contracts, request and proposal storage, loopback endpoints, and target selection in the Inspector. | Create one request for multiple phases and properties. Stage drafts for selected targets, preserve partial results across restart, and identify stale or invalid targets individually. |
| 2. MCP handoff | Optional stdio adapter, workspace pairing, request lookup, Materials Project query, and proposal staging. | Verify that Pi and Codex can each complete a copied request. Check missing MP credentials, alias IDs, timeouts, and truncated results. The adapter rejects requests outside its authorization and cannot apply drafts. |
| 3. Work folder and library | Host-provided retrieval, generated `AGENTS.md`, scoped Python execution, evidence capture, and indexed reuse. | Reproduce a result from a checksummed source and saved script. Start a new conversation and retrieve the same relevant source from disk without downloading it again. Verify Windows file, environment, and network restrictions. Test an out-of-directory attachment and instructions embedded in a source. |
| 4. Review and apply | Grouped candidate cards, source inspection, approved Phase Data attachment, and downstream rerun. | Apply multiple selected targets in one graph update and rerun Phase Assignment once. Keep unresolved and declined targets visible. Check stale revisions, existing manual fields, busy solver, cancellation, keyboard/mobile access, and export provenance. |
| 5. End-to-end pilot | Real Mo–Hf example, a redistributable multiphase offline fixture, and setup notes. | Request density and elasticity together for Mo–Hf. Reject the pure-Mo transfer, compute the cited BCC density estimate, keep elasticity unresolved, and refresh with the original equilibrium job. Use the multiphase fixture to verify shared source reuse and selective application. Run the project pytest suite and exercise the workflow in Edge. |
| 6. Integrated session controls | Direct host launch, session preferences, and configurable idle rollover. | Verify resume before the idle limit and a fresh session at or after it, including across app restart. An active batch continues through the idle interval. Confirm that a new session preserves completed targets and picks up saved sources. |

The Mo–4 wt% Hf pilot uses the final BCC phase at approximately **2.1906 at% Hf**, **298.15 K**, and **101325 Pa**. `mp-129` and `mp-aaaaaaez` identify the same pure-Mo record. The pure-Mo chemistry exceeds the current two-atomic-percentage-point transfer limit. The published BCC molar-volume model gives approximately **10.37 g/cm³** at the solved composition. Mark the result computed and identify its dilute extrapolation from the binary fitting compositions of 25, 50, and 75 at%. Keep the pilot mandatory and use an offline fixture for normal runs of the test suite. [Bocklund et al., Eq. 23 and Table A.1](https://www.osti.gov/servlets/purl/2427484) · [Materials Project identifier system](https://github.com/materialsproject/public-docs/blob/main/data-production/identifiers.md)

After the pilot, selected calculation nodes can use the same service contracts as MCP tools. Add wider workflow execution when stable operation IDs, artifact inputs, and job permissions are available.
