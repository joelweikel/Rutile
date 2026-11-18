# Reference research in Alloy Studio

Run equilibrium and **Phase Assignment**, then choose **Find missing data** in the Phase Assignment Inspector. Select the missing density and elasticity targets you want to share. The request is pinned to that saved equilibrium, including the actual fractions and conditions of each phase. **Find reference** starts with one phase selected.

Choose **Start Codex research** to send the batch to Codex. Rutile shows startup, agent output, recent activity, and the number of targets with findings. Output tokens and average output tokens per second appear when the host reports usage. The rate uses elapsed run time, including startup and tool calls. Choose **Close view** to return to the Inspector during a run or **Stop agent** to end the run.

Source links and archived attachments appear on the phase findings. Choose **Apply and rerun** to attach selected Phase Data and refresh Phase Assignment and connected Density nodes using the saved equilibrium. A density draft can be applied while elasticity is unresolved.

## Set up Codex or another harness

Rutile includes the local stdio MCP server. Open **Settings → Research agents** to see whether Rutile found your Codex executable. Install Codex and sign in, then enter the full executable path if detection needs help. **Start Codex research** opens an App Server session, configures the bundled MCP for the current Rutile port, and sends the task.

To use a separate Codex chat, choose **Install Rutile MCP in Codex**, restart Codex, and check for the `get_reference_request` tool in a new chat. For another MCP client, choose **Prepare MCP connection**, then register the displayed executable and argument array as a stdio server named `rutile`. Keep Rutile running.

For either external case, select **Manual MCP handoff** in Alloy Studio. Copy the research task from the overlay, paste it into your connected chat, and send it. Rutile shows **Waiting for manual handoff** until it sees a connector call. Read the transcript in the external chat and review proposals in Rutile.

Rutile prepares a connector token in its Git-ignored local `.env`. The registered connector reads that token from the file. Set the Materials Project key once in **Settings → Materials Project**. Lookups use the key through Rutile’s server. [Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

## Research files and review

Rutile generates a research `AGENTS.md` under `workspace/research/<project-id>/`, or inside the configured workspace. The MCP request supplies the location of the instructions and the batch’s scratch folder. Ask the host to work in that scope. Save source files, scripts, and output in scratch and submit their filenames with a proposal. Rutile accepts supported regular files directly in scratch, up to 10 MiB each and 30 MiB per proposal. Keep citations even if the full source cannot be retained.

For a Python-derived candidate, the proposal includes the script and output JSON, the phase structure and actual evaluated conditions, and the derivation and applicability limits. The output JSON contains a `values` object, for example `{"values":{"density":{"value":10.37,"unit":"g/cm³"}}}`. Rutile checks consistency, composition, structure, ordering evidence, conditions, and units. Read the cited passage and review the calculation before applying an estimate. Rutile stores the script as evidence and the approved scalar value as a normal Phase Data input.

The project library indexes evidence by chemistry, structure, ordering, and property. It records the original conditions and the stated applicability of each candidate. A later session can retrieve relevant metadata through `get_reference_request`. Supply up to eight matching artifact hashes in `restore_artifacts` to copy those files into the new scratch folder. A reused source still needs screening at the current phase conditions.

## Custom launchers and session policy

**Add a launch command** in Settings accepts an absolute executable path and a JSON array of arguments. Select **Pi RPC** for a Pi-compatible stdio launcher or **Codex App Server** for a Codex-compatible launcher. Configure model access, Rutile MCP, and permissions in that trusted launcher. The existing `RUTILE_RESEARCH_PI_COMMAND` and `RUTILE_RESEARCH_CODEX_COMMAND` values also work for custom launchers. Rutile starts the host in the project’s research folder and supplies the batch scratch directory in `RUTILE_RESEARCH_SCRATCH`.

The bundled Codex launcher uses Codex web search and a research permission profile for shell commands. It requests local writes in the batch scratch directory, denies reads of Rutile’s credential file, and disables shell network access. Download and extraction options depend on the host’s web tools and sandbox. Custom launchers use their own permission profiles. [Codex permissions](https://learn.chatgpt.com/docs/permissions)

Direct runs can **Always resume**, **Always start fresh**, or **Start fresh after inactivity**. The default idle interval is 30 minutes and begins when a run ends. Host compaction uses its normal settings, and research on disk survives new sessions. When changing the account, provider, or permission scope of a launcher, set `RUTILE_RESEARCH_PI_SESSION_SCOPE` or `RUTILE_RESEARCH_CODEX_SESSION_SCOPE` to give it a separate saved conversation. [Pi RPC](https://docs.pi.dev/latest/rpc-commands) · [Codex App Server](https://learn.chatgpt.com/docs/app-server)
