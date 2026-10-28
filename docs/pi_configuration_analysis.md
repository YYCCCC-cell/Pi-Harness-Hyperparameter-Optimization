# Pi configuration analysis

Prepared 2026-10-25 (Asia/Singapore). This is a static source analysis; no Pi process, model call, dependency installation, or benchmark trial was run.

## Version and scope

The requested `badlogic/pi-mono` URL now resolves to `earendil-works/pi`. The local directory remains `third_party/pi-mono`. The inspected revision is **`f321e5bdd26b3624bfb2ab182a334d0a5edb698a`**, whose package declares **`@earendil-works/pi-coding-agent` 1.4.0** and Node **>=22.19.0**. This is a pinned main snapshot, **not a claim that the checkout equals the published v1.4.0 artifact**. Source checkout identities and clean-tree checks are recorded in [source_lock.json](sources/source_lock.json). [P1] [P2]

**Conclusion:** meaningful harness optimization is possible through existing configuration: thinking effort, compaction thresholds, tool selection, and optional built-in codemode. Retry and cache policies also change runtime behavior but should initially be held constant. Model/provider selection and model sampling are separate experimental factors. The full documented `settings.json` surface is inventoried below, including options that have little relevance to headless evaluation. [P3] [P4]

## Configuration authority, precedence, and validation

- User settings live at `<agent-dir>/settings.json`, where the default agent directory is `~/.pi/agent`; `PI_CODING_AGENT_DIR` changes it. Project `.pi/settings.json` loads after project trust, except `sessionDir`, which is read early to locate sessions. `models.json`, credentials, instructions, resources, and MCP configuration are distinct files. [P5]
- Project values override user values; nested objects merge. Resource lists combine rather than acting as a universal replacement. Tool lists have their own replace/add/remove semantics. For a benchmark, use a fresh container home and explicit settings, and avoid incidental host/project resource discovery. This last sentence is an experimental design recommendation. [P6] [P7] [P8] [P9]
- The TypeBox schema is `src/core/settings-schema.ts`; the published JSON schema explicitly says it is generated from TypeScript. It permits additional properties. Loading settings performs JSON parsing and migrations, **not full schema enforcement**. A misspelled key can therefore survive loading without becoming an effective tuning knob. Use the pinned schema and an external allowlist for candidate generation; do not rely on the live schema URL for reproducibility. [P10] [P11] [P12] [P13]
- Compaction token values are a stronger exception: runtime accessors reject negative, non-integer, or unsafe-integer values. Each model-specific override resolves independently before the ordinary value and built-in default. The schema's very large upper bound is not a sensible search range. [P14]
- Thinking resolution can include SDK/CLI selection, restored sessions, per-model defaults, and global defaults; the result is clamped to model capabilities. A fresh session and logged **effective** thinking level are necessary for a controlled experiment. `defaultThinkingLevel="medium"` is the ordinary startup fallback, not a promise that every model uses medium. [P15] [P16] [P17]

## Recommended optimization parameters

All search values below are **proposed project choices**, not upstream recommendations or measured optima. Hold model ID, provider, task set, skill condition, sandbox resources, and trial budget fixed when comparing configurations.

| Parameter | Type and upstream default | Allowed domain / important constraint | Proposed search / expected effect |
|---|---|---|---|
| `defaultThinkingLevel` | Enum; `medium` fallback | `off,minimal,low,medium,high,xhigh,max`; actual supported levels depend on the model | Start with `low,medium,high` only if all three remain distinct after clamping. More reasoning can change quality, billed output, and latency; no monotonic improvement is assumed. [P18] [P15] |
| `compaction.enabled` | Boolean; `true` | `true,false` | Keep true initially; disabling it is a separate ablation with context-overflow risk. [P19] [P20] |
| `compaction.reserveTokens` | Safe integer; `16384` | `0..9007199254740991`; trigger is context tokens > context window − reserve | Try `8192,16384,32768` only when feasible for the fixed model. Larger reserve triggers summarization earlier, adding summary calls and potentially losing detail. [P14] [P20] |
| `compaction.keepRecentTokens` | Safe integer; `20000` | Same schema domain; retention is selected at valid message boundaries, not an exact byte/token slice | Try `10000,20000,40000`, subject to context feasibility. More retained recent context can preserve detail but increases subsequent input and reduces compression. [P21] [P22] [P23] |
| `defaultTools` | Array of tool selectors; `read,bash,edit,write` | Built-in names and registered extension names; `+`/`-` operations; empty list does not disable extension/SDK tools | Compare defaults with defaults plus `grep,find,ls`. This changes tool affordances and prompt descriptions; it is not a security boundary because bash can still run commands. [P24] [P25] |
| `codemode.mode` | `on` or `only`; `on` | Requires activating the built-in codemode extension/tool; `only` hides direct active tools from the model | Optional later categorical ablation. Scripts can combine tools and filter results, changing tool-call granularity and context use. [P26] [P27] |
| `codemode.inlineBudget` | Number >=0; `3000` | Applies to codemode descriptions; character-count token estimate | Optional `1000,3000,6000`, only with codemode active. Changes inline declarations versus tool discovery. [P28] [P29] |

Recommended first study: a bounded, pre-generated set of at most 12 combinations of thinking, reserve, and retention, including the default baseline. Add tool selection only after validating that those knobs are actually exercised. Use the same predeclared feasibility rule for every candidate: `reserve < C` and `keepRecent + O + M < C - reserve`, where `C` is the verified context window, `O` the fixed output allowance, and `M` a fixed safety margin. **This is a conservative project filter, not Pi's own validator.** Record observed compaction counts: short tasks may never trigger compaction, so their scores alone cannot establish a threshold effect. The trigger and context-clamping code motivate the filter. [P20] [P30]

## Conditional and fixed controls

| Control | Type, default, domain | Constraint and expected runtime effect | Recommendation |
|---|---|---|---|
| `thinkingBudgets.minimal` | Number; `1024` | Numeric token budget where the provider uses budget-based thinking | Do not tune alongside effort in the first study. [P31] [P32] |
| `thinkingBudgets.low` | Number; `2048` | Same; proposed values must be finite nonnegative integers and compatible with provider limits, although the settings schema itself only says number | Conditional only. [P31] [P32] |
| `thinkingBudgets.medium` | Number; `8192` | Same; output and reasoning ceilings interact | Conditional only. [P31] [P32] |
| `thinkingBudgets.high` | Number; `16384` | Generic budget helper maps `xhigh`/`max` to high; it reserves answer room when capped | Conditional only. Adaptive Anthropic models take an effort path instead of this custom-budget path. [P32] [P33] |
| `modelThinkingLevels[provider/modelId]` | Map to thinking enum; absent | Exact model key; overrides global startup default when applicable | Omit or set consistently for the selected model; do not allow stale per-model entries to mask the candidate. [P34] [P15] |
| `compaction.modelOverrides[provider/modelId].reserveTokens` | Safe integer; inherits ordinary reserve | Same validation as ordinary reserve | Omit in a one-model study, or make it the single controlled source. [P14] |
| `compaction.modelOverrides[provider/modelId].keepRecentTokens` | Safe integer; inherits ordinary retention | Each field falls back independently | Same recommendation. [P14] |
| `retry.enabled`, `retry.maxRetries`, `retry.baseDelayMs`, `retry.maxAgentDelayMs` | Boolean=true; numbers=3,2000,60000 | Agent-level transient recovery with backoff; number fields have no schema minimum | Hold fixed; use integer/nonnegative project validation. More retries may turn infrastructure failures into success while increasing time/cost. [P35] [P36] [P37] |
| `retry.provider.timeoutMs`, `.maxRetries`, `.maxRetryDelayMs` | Numbers; defaults HTTP idle timeout, 0,60000 | Provider layer, distinct from agent retries; delay limit 0 disables limit | Hold provider retries at 0. Nested retries can distort budgets. [P38] [P39] |
| `cacheWarming` | `off,streaming,idle`; `streaming` | Global only; eligible refreshes spend money and add usage without entering model context | Set `off` for an initially auditable cost comparison; report this deviation from Pi defaults. [P40] [P41] |
| `images.autoResize`, `images.blockImages` | Booleans; true,false | Resize affects model-visible images; blocking removes them, unlike terminal image display settings | Hold fixed; blocking vision changes capability on multimodal tasks. [P42] |
| `steeringMode`, `followUpMode` | `all,one-at-a-time`; latter default | Controls queued messages, not tool-call concurrency | Keep defaults for an unattended single prompt. [P43] |
| `branchSummary.*` | reserve number=16384, skipPrompt boolean=false | Branch/tree navigation summaries | Exclude from the initial linear benchmark search. [P44] [P45] |

## Model configuration, CLI, and environment surfaces

`settings.json` does not offer a universal `temperature`, `top_p`, `seed`, `maxTurns`, or task-wide token-budget key. Do not invent such settings. The supported model-specific `models.json` surface can express some sampling controls, and the benchmark supplies wall-clock budgets. The settings/schema inventory, CLI reference, and model configuration define these separate surfaces. [P46] [P47] [P48] [B1]

| Name / location | Type and default | Domain / constraint | Runtime effect |
|---|---|---|---|
| `providers.<p>.modelOverrides.<id>.maxTokens` | Number; inherited catalog value | Truthful provider-supported output cap; custom `models[]` default is 16384, **not a universal built-in model default** | Response cap; Pi also fits output to remaining context. [P49] [P50] [P51] |
| `...samplingParams` | Free-form object; absent/inherited | Only `openai-completions`, `openai-responses`, `azure-openai-responses`; keys/ranges validated by the selected backend, not a universal Pi schema | Request-body overrides such as temperature/top_p/top_k. Missing values mean provider/model defaults, not an assumed temperature of 0 or 1. [P52] [P53] |
| `...samplingParamsByThinkingLevel.<level>` | Partial map of sampling objects; absent | Pi effective thinking-level keys; later overrides win per key | Couples sampling to effort; keep fixed unless explicitly studying the interaction. [P52] [P54] |
| `...contextWindow`, `...reasoning`, `...thinkingLevelMap`, `...input` | Number / boolean / mapping / modalities; built-in values inherited | For custom models: context=128000, reasoning=false, input=[text]; capability metadata must match endpoint | These determine clamping and available modalities; **do not optimize by falsifying capabilities**. [P55] |
| `...inputLimits.images.resize.*` | maxWidth/maxHeight/maxBytes positive integers; jpegQuality integer 1..100 | Omitted resize fields default to 2000×2000, 4.5 MiB encoded, JPEG quality 80 | Controls newly encoded images; historic images are not re-encoded. Optional separate vision ablation. [P56] [P57] |
| `...promptCache` and `...cost.*` | Cache lifetimes and numeric pricing metadata; inherited/absent | Accurate endpoint metadata; rates are USD per million tokens | Affects eligibility/estimates, not the provider's actual prices. Keep accurate and fixed. [P58] [P59] |
| `--tools`, `--exclude-tools`, `--no-tools` | Selector lists / flags; normal default tools otherwise | CLI selection semantics differ in details from settings lists; MCP has separate exposure/filter rules | Reversible tool selection without source edits. Prefer explicit `defaultTools` plus no MCP for the initial study. [P60] |
| `--skill`, `--no-skills`, `--no-context-files`, `--no-extensions`, `--no-mcp` | Paths or flags; discovery enabled normally | Explicit skill/extension paths still load when corresponding discovery is disabled | Controls resources and instruction contamination; turning off skill commands alone does not remove skills. [P61] [P62] |
| `--system-prompt`, `--append-system-prompt`, SYSTEM.md / APPEND_SYSTEM.md | Text or paths; built-in prompt / no added text | Replacement versus append; trusted project file can take precedence over user file | Prompt optimization is possible without core edits, but introduces an additional factor. Keep fixed in this project stage. [P63] [P64] |
| `PI_CODING_AGENT_DIR`, fresh session storage | Path; `~/.pi/agent` | Must align with adapter skill/provider paths | Isolates settings and history across trials. [P65] [P66] |
| `PI_OFFLINE` / `--offline` | Process flag; normally unset | Disables automatic network activity/model catalog refresh; **not a sandbox network firewall** | Useful for pinning catalog behavior; validate the catalog used for the chosen model. [P67] [P68] |
| `PI_CACHE_RETENTION` | Documented value `long`; otherwise provider behavior | Provider dependent | Extended prompt caching can change cost; hold the environment constant. [P69] |

Built-in output truncation defaults (`2000` lines, `50*1024` bytes, grep line limit `500` characters) are implementation constants; there is no corresponding ordinary settings field in this revision. A tool extension/replacement could change behavior but would enlarge the harness under study. Exclude such changes from this configuration-only study. [P70] [P46]

## Adapter implications and baseline configuration

BenchFlow already supports `pi-acp`; no new protocol adapter is needed as the first step. Its Pi entry does **not** declare an ACP effort option, so BenchFlow's `--reasoning-effort` path raises for Pi at v0.6.3. Write Pi settings before starting the session, and verify effective thinking after model selection. The companion integration analysis describes version pinning and the external orchestration required. [B2] [B3]

Proposed initial settings (an example only; not installed anywhere):

```json
{
  "defaultThinkingLevel": "medium",
  "defaultTools": ["read", "bash", "edit", "write"],
  "compaction": {"enabled": true, "reserveTokens": 16384, "keepRecentTokens": 20000},
  "retry": {"enabled": true, "maxRetries": 3, "baseDelayMs": 2000,
             "maxAgentDelayMs": 60000, "provider": {"maxRetries": 0, "maxRetryDelayMs": 60000}},
  "cacheWarming": "off",
  "images": {"autoResize": true, "blockImages": false},
  "enableInstallTelemetry": false,
  "enableAnalytics": false
}
```

This is an **experimental baseline**, not an exact untouched-default run: cache warming and install telemetry are disabled by design. The selected model/provider must be explicit in the runner, and unrelated resources must be excluded through the launch environment/flags. Arrays such as `skills: []` or `extensions: []` alone do not mean automatic discovery is disabled. [P40] [P71] [P61]

## Complete documented settings inventory

The table below covers every named setting row in the pinned `docs/settings.md`. Defaults are runtime/documented defaults, not values inserted by a JSON-schema validator. A numeric schema with no bounds is labelled as such; proposed experimental bounds elsewhere are deliberately stricter. The effect descriptions summarize the official reference. Object/map rows include their child domain; the thinking-budget and compaction-override children are expanded above. UI-only settings are retained for completeness, but excluded from the proposed HPO space.

| Name | Type | Default | Domain and constraints | Expected runtime effect | Evidence |
|---|---|---|---|---|---|
| `defaultProvider` | string | Automatic | string; Exact installed provider and usable credentials; fix for HPO. | Startup AI provider. | [P72] [P73] |
| `defaultModel` | string | Automatic | string; Valid model ID; use an exact ID for reproducibility. | Startup model ID. | [P74] [P75] |
| `defaultThinkingLevel` | `"off" \| "minimal" \| "low" \| "medium" \| "high" \| "xhigh" \| "max"` | `"medium"` | off, minimal, low, medium, high, xhigh, max; Clamped to supported model levels. | Startup thinking level. | [P76] [P77] |
| `modelThinkingLevels` | object | None | string-keyed map to off, minimal, low, medium, high, xhigh, max; Exact provider/modelId keys. | Per-model startup thinking levels keyed by exact `provider/modelId`. | [P78] [P79] |
| `thinkingBudgets` | object | Built-in budgets | minimal: number; no schema bounds; low: number; no schema bounds; medium: number; no schema bounds; high: number; no schema bounds; Provider-dependent; defaults minimal=1024, low=2048, medium=8192, high=16384. | Token budgets for `minimal`, `low`, `medium`, and `high` thinking levels. | [P80] [P81] |
| `enabledModels` | `string[]` | All available models | array of string | Model patterns used for startup selection and model cycling. Uses the same format as `--models`. | [P82] [P83] |
| `hideThinkingBlock` | boolean | `false` | true / false | Hide thinking blocks in the transcript. | [P84] [P85] |
| `showCacheMissNotices` | boolean | `false` | true / false | Show notices for significant cache misses, successful cache warming, compaction usage, and provider recovery. | [P86] [P87] |
| `cacheWarming` | `"off" \| "streaming" \| "idle"` | `"streaming"` | "off" / "streaming" / "idle"; Agent-directory settings only; refreshes can cost money. | Keep eligible provider prompt caches warm during active runs or, with `"idle"`, between runs. Global setting only. | [P88] [P89] |
| `steeringMode` | `"all" \| "one-at-a-time"` | `"one-at-a-time"` | "all" / "one-at-a-time" | How queued steering messages are delivered. | [P90] [P91] |
| `followUpMode` | `"all" \| "one-at-a-time"` | `"one-at-a-time"` | "all" / "one-at-a-time" | How queued follow-up messages are delivered. | [P92] [P93] |
| `externalEditor` | string | `$VISUAL`, `$EDITOR`, then platform default | string | Command opened by the external-editor keybinding. | [P94] [P95] |
| `doubleEscapeAction` | `"tree" \| "fork" \| "none"` | `"tree"` | "fork" / "tree" / "none" | Action for double Escape with an empty editor. | [P96] [P97] |
| `treeFilterMode` | `"default" \| "no-tools" \| "user-only" \| "labeled-only" \| "all"` | `"default"` | "default" / "no-tools" / "user-only" / "labeled-only" / "all" | Initial filter used by `/tree`. | [P98] [P99] |
| `defaultProjectTrust` | `"ask" \| "always" \| "never"` | `"ask"` | "ask" / "always" / "never"; Agent-directory settings only. | Fallback project-trust behavior. **Can only be set in agent-directory settings.** | [P100] [P101] |
| `defaultTools` | `string[]` | `read`, `bash`, `edit`, `write` | array of string; Registered tools; plain names replace, +/- modify inherited selection. | Tools enabled at startup. Plain names replace the defaults; `+name` adds a tool and `-name` removes one. An empty array disables all built-in tools but not extension or SDK tools. | [P102] [P103] |
| `codemode.mode` | `"on"` \| `"only"` | `"on"` | "on" / "only"; Only effective when codemode is active. | How the `codemode` tool presents tools while it is active. `on`: declared tools get a note on calling them from scripts appended to their description, and `codemode` lists only tools that are not declared. `only`: `codemode` lists every tool scripts can call, and active built-in and extension tools are hidden from the model, so it reaches them through `codemode`. | [P104] [P105] |
| `codemode.inlineBudget` | number | `3000` | number >= 0; Only effective when codemode is active; estimated tokens. | Estimated tokens (characters / 4) the `codemode` tool's description may spend on tool declarations. Tools that do not fit are left out and found with `searchTools()`. `0` lists only namespaces. | [P106] [P105] |
| `sessionDir` | string | Agent session directory | string; Relative to cwd; environment/CLI override. | Session storage directory. Relative paths resolve from the working directory. `PI_CODING_AGENT_SESSION_DIR` and `--session-dir` override this setting. | [P107] [P108] |
| `sessionShareDestination` | `"auto" \| "gist" \| "radius"` | `"auto"` | "auto" / "gist" / "radius" | Destination used by `/share`. `auto` uses Radius when authenticated and otherwise creates a GitHub gist. `gist` always uses a gist. `radius` requires Radius authentication and never falls back to a gist. | [P109] [P110] |
| `compaction.enabled` | boolean | `true` | true / false | Enable automatic compaction. | [P111] [P112] |
| `compaction.reserveTokens` | number | `16384` | integer >= 0, <= 9007199254740991 | Free context tokens below which automatic compaction starts. | [P113] [P112] |
| `compaction.keepRecentTokens` | number | `20000` | integer >= 0, <= 9007199254740991 | Recent tokens retained without summarization. | [P114] [P112] |
| `compaction.modelOverrides` | object | None | string-keyed map to reserveTokens: integer >= 0, <= 9007199254740991; keepRecentTokens: integer >= 0, <= 9007199254740991; Exact provider/modelId keys; nonnegative safe integer children. | Per-model token settings keyed by exact `provider/modelId`. | [P115] [P112] |
| `branchSummary.reserveTokens` | number | `16384` | number; no schema bounds | Tokens reserved when summarizing branch history. | [P116] [P117] |
| `branchSummary.skipPrompt` | boolean | `false` | true / false | Skip the branch-summary prompt and default to no summary. | [P118] [P117] |
| `theme` | string | `"system"` | string | Built-in or custom theme name. `system` derives colors from the terminal theme. | [P119] [P120] |
| `quietStartup` | boolean \| `"header"` | `false` | true / false / "header" | `true` hides the startup header and loaded-resource listing. `"header"` keeps the header (version and key hints) but hides the model scope line and loaded-resource listing. | [P121] [P122] |
| `tuiMode` | `"regular" \| "fullscreen"` | `"fullscreen"` | "regular" / "fullscreen" | Interactive terminal UI mode. | [P123] [P124] |
| `fullscreenExitOutput` | `"transcript" \| "resume-hint"` | `"transcript"` | "transcript" / "resume-hint" | Output printed when fullscreen mode exits. | [P125] [P126] |
| `fullscreenScrollbar` | `"auto" \| "always" \| "hidden"` | `"auto"` | "auto" / "always" / "hidden" | Fullscreen transcript scrollbar behavior. | [P127] [P128] |
| `fullscreenCopyOnSelect` | boolean | `true` | true / false | Copy selected text automatically in fullscreen mode. | [P129] [P130] |
| `fullscreenWheelScrollLines` | `"auto"` \| number | `"auto"` | number; no schema bounds / "auto"; Numeric runtime range 1–100, or auto. | Lines per mouse-wheel event in fullscreen mode, from 1 to 100. `"auto"` moves one line per event in local macOS terminals, which already accelerate wheel and trackpad input; elsewhere, and over SSH, it speeds up fast wheel spins to at most 6 lines per event. Alt+wheel moves five times as far. | [P131] [P132] |
| `editorPaddingX` | number | `0` | number; no schema bounds; Documented range 0–3 cells. | Horizontal editor padding from 0 to 3 cells. | [P133] [P134] |
| `outputPad` | `0 \| 1` | `1` | 0 / 1 | Horizontal transcript padding for messages, tool output, `!` command output, and summary blocks. | [P135] [P136] |
| `autocompleteMaxVisible` | number | `5` | number; no schema bounds; Documented range 3–20 entries. | Visible autocomplete entries, from 3 to 20. | [P137] [P138] |
| `showHardwareCursor` | boolean | `false` | true / false | Use the terminal cursor instead of Pi's drawn cursor. Pi still positions it for input methods. | [P139] [P140] |
| `terminal.showImages` | boolean | `true` | true / false | Display inline images when supported. | [P141] [P142] |
| `terminal.imageWidthCells` | number | `60` | number; no schema bounds | Preferred inline image width in terminal cells. | [P143] [P142] |
| `terminal.clearOnShrink` | boolean | `false` | true / false | Clear empty rows when rendered content shrinks. When unset, `PI_CLEAR_ON_SHRINK=1` enables it. | [P144] [P142] |
| `terminal.showTerminalProgress` | boolean | `false` | true / false | Show OSC 9;4 progress in the terminal tab. | [P145] [P142] |
| `terminal.hyperlinks` | `boolean \| "auto"` | `"auto"` | true / false / "auto" | Override OSC 8 hyperlink detection. | [P146] [P142] |
| `terminal.images` | `"kitty" \| "iterm2" \| "auto" \| false` | `"auto"` | "kitty" / "iterm2" / "auto" / false | Override inline-image protocol detection. | [P147] [P142] |
| `terminal.trueColor` | `boolean \| "auto"` | `"auto"` | true / false / "auto" | Override true-color detection. | [P148] [P142] |
| `images.autoResize` | boolean | `true` | true / false | Resize images to at most 2000 by 2000 pixels before sending them to a model. | [P149] [P150] |
| `images.blockImages` | boolean | `false` | true / false | Prevent images from being sent to models. | [P151] [P150] |
| `markdown.codeBlockIndent` | string | `"  "` | string | Prefix used to indent rendered code blocks. | [P152] [P153] |
| `markdown.mermaid` | `"off" \| "final" \| "streaming"` | `"streaming"` | "off" / "final" / "streaming" | Mermaid rendering mode. | [P154] [P153] |
| `transport` | `"auto" \| "sse" \| "websocket" \| "websocket-cached"` | `"auto"` | "auto" / "sse" / "websocket" / "websocket-cached" | Preferred transport for AI providers that support multiple transports. | [P155] [P156] |
| `httpProxy` | string | None | string; Agent-directory settings only; valid proxy URL. | Proxy URL applied as `HTTP_PROXY` and `HTTPS_PROXY` for Pi-managed HTTP clients. **Can only be set in agent-directory settings.** | [P157] [P158] |
| `httpIdleTimeoutMs` | number \| `"disabled"` | `300000` | number >= 0 / "disabled"; 0 or disabled disables idle timeout; prefer a finite experimental cap. | HTTP header and body idle timeout in milliseconds. Set to `0` or `"disabled"` to disable. | [P159] [P160] |
| `websocketConnectTimeoutMs` | number \| `"disabled"` | `15000` | number >= 0 / "disabled"; 0 or disabled disables connection timeout. | WebSocket connection timeout in milliseconds. Set to `0` or `"disabled"` to disable. | [P161] [P162] |
| `retry.enabled` | boolean | `true` | true / false | Enable automatic agent-level retry for transient failures. | [P163] [P164] |
| `retry.maxRetries` | number | `3` | number; no schema bounds | Maximum agent-level retry attempts. | [P165] [P164] |
| `retry.baseDelayMs` | number | `2000` | number; no schema bounds | Initial exponential-backoff delay in milliseconds. | [P166] [P164] |
| `retry.maxAgentDelayMs` | number | `60000` | number; no schema bounds | Maximum agent-level retry delay in milliseconds. | [P167] [P164] |
| `retry.provider.timeoutMs` | number | `httpIdleTimeoutMs` | number; no schema bounds | Provider request timeout in milliseconds. | [P168] [P164] |
| `retry.provider.maxRetries` | number | `0` | number; no schema bounds | Provider-level retry attempts. | [P169] [P164] |
| `retry.provider.maxRetryDelayMs` | number | `60000` | number; no schema bounds; 0 disables the delay limit. | Maximum server-requested delay in milliseconds. Set to `0` to disable the limit. | [P170] [P164] |
| `shellPath` | string | Platform default | string | Custom shell executable path. Supports a leading `~`. | [P171] [P172] |
| `shellCommandPrefix` | string | None | string | Prefix prepended to every shell command. | [P173] [P174] |
| `npmCommand` | `string[]` | `npm` | array of string | Command and arguments used for npm package lookup and installation. | [P175] [P176] |
| `packages` | array | `[]` | array of source strings or {source,autoload?,extensions?,skills?,prompts?,themes?}; Strings or source/filter objects; packages may add executable behavior; fix contents. | npm, git, or local Pi package sources. | [P177] [P178] |
| `extensions` | `string[]` | `[]` | array of string; Empty array does not suppress discovery; built-ins also exist. | Extension files or directories. | [P179] [P180] |
| `skills` | `string[]` | `[]` | array of path strings; legacy object accepted/migrated; Empty array does not suppress discovery; legacy object form is migrated. | Skill files or directories. | [P181] [P182] |
| `prompts` | `string[]` | `[]` | array of string | Prompt-template files or directories. | [P183] [P184] |
| `themes` | `string[]` | `[]` | array of string | Theme files or directories. | [P185] [P186] |
| `enableSkillCommands` | boolean | `true` | true / false; Command discovery only; not an enable/disable switch for all skill access. | Register skills as `/skill:name` commands. | [P187] [P188] |
| `collapseChangelog` | boolean | `false` | true / false | Show a condensed changelog after an update. | [P189] [P190] |
| `enableInstallTelemetry` | boolean | `true` | true / false | Enable anonymous install/update reporting and selected provider attribution headers. Does not control update checks. | [P191] [P192] |
| `enableAnalytics` | boolean | `false` | true / false | Opt in to analytics data sharing. Currently used only by the experimental first-run setup. | [P193] [P194] |
| `warnings.anthropicExtraUsage` | boolean | `true` | true / false | Warn when Anthropic subscription authentication may use paid extra usage. | [P195] [P196] |

### Schema-only bookkeeping and legacy keys

These are not additional performance knobs: `$schema` identifies editor schema; `lastChangelogVersion`, `trackingId`, and global `deviceId` are bookkeeping identifiers (strings, unset/generated rather than a useful numerical default). Legacy `queueMode` (all/one-at-a-time), `websockets` (boolean), `retry.maxDelayMs` (number), and legacy `skills` object values migrate to their modern equivalents. Do not include both legacy and current keys in candidate files. [P197] [P198] [P12] [P199]

### Interpretation limits

Expected runtime effects are source-based hypotheses, not measured results. No setting was shown to improve SkillsBench here. In particular, a configured thinking budget can be ignored by an adaptive provider; a compaction threshold can remain inactive on short tasks; display settings do not establish model capability changes. Before any paid search, the proposed integration checks must show that each candidate reaches the intended Pi instance and changes the effective behavior described above.

## Source index

All repository citations below are immutable links to the exact inspected commit. Line numbers refer to that checkout, not moving `main`. `P` = Pi, `S` = SkillsBench, `B` = BenchFlow, `A` = the upstream pi-acp adapter.

- **P1**: `third_party/pi-mono/packages/coding-agent/package.json:1–21`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P1]

[P1]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L1-L21

- **P2**: `third_party/pi-mono/packages/coding-agent/package.json:88–97`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P2]

[P2]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L88-L97

- **P3**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:7–88`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P3]

[P3]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L7-L88

- **P4**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:120–163`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P4]

[P4]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L120-L163

- **P5**: `third_party/pi-mono/packages/coding-agent/docs/configuration.md:1–39`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P5]

[P5]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/configuration.md#L1-L39

- **P6**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:3–5`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P6]

[P6]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L3-L5

- **P7**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:42–60`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P7]

[P7]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L42-L60

- **P8**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:148–163`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P8]

[P8]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L148-L163

- **P9**: `third_party/pi-mono/packages/coding-agent/src/core/settings-manager.ts:126–146`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P9]

[P9]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L126-L146

- **P10**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:1–9`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P10]

[P10]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L1-L9

- **P11**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:206–217`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P11]

[P11]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L206-L217

- **P12**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:443–453`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P12]

[P12]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L443-L453

- **P13**: `third_party/pi-mono/packages/coding-agent/src/core/settings-manager.ts:366–455`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P13]

[P13]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L366-L455

- **P14**: `third_party/pi-mono/packages/coding-agent/src/core/settings-manager.ts:833–879`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P14]

[P14]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L833-L879

- **P15**: `third_party/pi-mono/packages/coding-agent/src/core/sdk.ts:253–278`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P15]

[P15]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/sdk.ts#L253-L278

- **P16**: `third_party/pi-mono/packages/coding-agent/src/core/defaults.ts:1–12`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P16]

[P16]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/defaults.ts#L1-L12

- **P17**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:63–72`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P17]

[P17]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L63-L72

- **P18**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:13–18`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P18]

[P18]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L13-L18

- **P19**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:69–82`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P19]

[P19]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L69-L82

- **P20**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:27–49`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P20]

[P20]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L27-L49

- **P21**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:73–80`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P21]

[P21]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L73-L80

- **P22**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:43–49`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P22]

[P22]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L43-L49

- **P23**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:100–136`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P23]

[P23]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L100-L136

- **P24**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:38–60`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P24]

[P24]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L38-L60

- **P25**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:119–156`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P25]

[P25]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L119-L156

- **P26**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:42–46`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P26]

[P26]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L42-L46

- **P27**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:151–178`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P27]

[P27]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L151-L178

- **P28**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:43–44`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P28]

[P28]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L43-L44

- **P29**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:154–168`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P29]

[P29]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L154-L168

- **P30**: `third_party/pi-mono/packages/ai/src/api/simple-options.ts:15–21`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P30]

[P30]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/api/simple-options.ts#L15-L21

- **P31**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:121–133`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P31]

[P31]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L121-L133

- **P32**: `third_party/pi-mono/packages/ai/src/api/simple-options.ts:68–108`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P32]

[P32]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/api/simple-options.ts#L68-L108

- **P33**: `third_party/pi-mono/packages/ai/src/api/anthropic-messages.ts:976–1003`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P33]

[P33]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/api/anthropic-messages.ts#L976-L1003

- **P34**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:15–18`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P34]

[P34]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L15-L18

- **P35**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:128–136`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P35]

[P35]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L128-L136

- **P36**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:55–71`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P36]

[P36]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L55-L71

- **P37**: `third_party/pi-mono/packages/coding-agent/src/core/agent-session.ts:3819–3858`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P37]

[P37]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/agent-session.ts#L3819-L3858

- **P38**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:132–136`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P38]

[P38]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L132-L136

- **P39**: `third_party/pi-mono/packages/coding-agent/src/core/sdk.ts:340–350`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P39]

[P39]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/sdk.ts#L340-L350

- **P40**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:21–23`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P40]

[P40]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L21-L23

- **P41**: `third_party/pi-mono/packages/coding-agent/src/core/settings-manager.ts:928–931`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P41]

[P41]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L928-L931

- **P42**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:106–114`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P42]

[P42]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L106-L114

- **P43**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:29–32`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P43]

[P43]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L29-L32

- **P44**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:84–89`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P44]

[P44]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L84-L89

- **P45**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:16–23`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P45]

[P45]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L16-L23

- **P46**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:206–453`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P46]

[P46]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L206-L453

- **P47**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:53–74`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P47]

[P47]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L53-L74

- **P48**: `third_party/pi-mono/packages/coding-agent/docs/models-configuration.md:26–87`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P48]

[P48]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L26-L87

- **B1**: `third_party/benchflow/src/benchflow/rollout/_config.py:119–125`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B1]

[B1]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L119-L125

- **P49**: `third_party/pi-mono/packages/coding-agent/docs/models-configuration.md:52–61`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P49]

[P49]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L52-L61

- **P50**: `third_party/pi-mono/packages/coding-agent/docs/models-configuration.md:81–85`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P50]

[P50]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L81-L85

- **P51**: `third_party/pi-mono/packages/ai/src/api/simple-options.ts:18–46`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P51]

[P51]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/api/simple-options.ts#L18-L46

- **P52**: `third_party/pi-mono/packages/coding-agent/docs/models.md:114–140`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P52]

[P52]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models.md#L114-L140

- **P53**: `third_party/pi-mono/packages/ai/src/types.ts:136–137`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P53]

[P53]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/types.ts#L136-L137

- **P54**: `third_party/pi-mono/packages/ai/src/api/simple-options.ts:24–33`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P54]

[P54]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/api/simple-options.ts#L24-L33

- **P55**: `third_party/pi-mono/packages/coding-agent/docs/models-configuration.md:32–55`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P55]

[P55]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L32-L55

- **P56**: `third_party/pi-mono/packages/ai/src/providers/model-schema.ts:51–75`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P56]

[P56]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/providers/model-schema.ts#L51-L75

- **P57**: `third_party/pi-mono/packages/coding-agent/docs/models.md:81–102`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P57]

[P57]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models.md#L81-L102

- **P58**: `third_party/pi-mono/packages/coding-agent/docs/models-configuration.md:40–51`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P58]

[P58]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L40-L51

- **P59**: `third_party/pi-mono/packages/coding-agent/docs/models.md:104–112`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P59]

[P59]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models.md#L104-L112

- **P60**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:119–138`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P60]

[P60]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L119-L138

- **P61**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:194–217`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P61]

[P61]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L194-L217

- **P62**: `third_party/pi-mono/packages/coding-agent/docs/skills.md:41–61`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P62]

[P62]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/skills.md#L41-L61

- **P63**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:229–240`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P63]

[P63]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L229-L240

- **P64**: `third_party/pi-mono/packages/coding-agent/docs/configuration.md:18–39`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P64]

[P64]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/configuration.md#L18-L39

- **P65**: `third_party/pi-mono/packages/coding-agent/docs/configuration.md:7–24`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P65]

[P65]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/configuration.md#L7-L24

- **P66**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:78–107`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P66]

[P66]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L78-L107

- **P67**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:241–242`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P67]

[P67]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L241-L242

- **P68**: `third_party/pi-mono/packages/coding-agent/docs/models.md:15–15`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P68]

[P68]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models.md#L15

- **P69**: `third_party/pi-mono/packages/coding-agent/docs/environment-variables.md:79–88`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P69]

[P69]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/environment-variables.md#L79-L88

- **P70**: `third_party/pi-mono/packages/coding-agent/src/core/tools/truncate.ts:1–13`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P70]

[P70]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/tools/truncate.ts#L1-L13

- **B2**: `third_party/benchflow/src/benchflow/agents/registry.py:366–389`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B2]

[B2]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L389

- **B3**: `third_party/benchflow/src/benchflow/acp/runtime.py:399–413`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B3]

[B3]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/acp/runtime.py#L399-L413

- **P71**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:148–171`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P71]

[P71]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L148-L171

- **P72**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:13–13`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P72]

[P72]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L13

- **P73**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:14–16`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P73]

[P73]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L14-L16

- **P74**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:14–14`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P74]

[P74]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L14

- **P75**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:17–19`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P75]

[P75]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L17-L19

- **P76**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:15–15`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P76]

[P76]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L15

- **P77**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:20–22`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P77]

[P77]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L20-L22

- **P78**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:16–16`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P78]

[P78]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L16

- **P79**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:23–31`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P79]

[P79]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L23-L31

- **P80**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:17–17`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P80]

[P80]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L17

- **P81**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:528–545`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P81]

[P81]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L528-L545

- **P82**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:18–18`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P82]

[P82]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L18

- **P83**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:470–476`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P83]

[P83]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L470-L476

- **P84**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:19–19`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P84]

[P84]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L19

- **P85**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:202–205`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P85]

[P85]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L202-L205

- **P86**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:20–20`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P86]

[P86]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L20

- **P87**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:206–210`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P87]

[P87]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L206-L210

- **P88**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:21–21`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P88]

[P88]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L21

- **P89**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:655–672`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P89]

[P89]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L655-L672

- **P90**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:31–31`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P90]

[P90]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L31

- **P91**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:71–83`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P91]

[P91]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L71-L83

- **P92**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:32–32`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P92]

[P92]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L32

- **P93**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:84–96`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P93]

[P93]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L84-L96

- **P94**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:33–33`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P94]

[P94]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L33

- **P95**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:211–214`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P95]

[P95]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L211-L214

- **P96**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:34–34`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P96]

[P96]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L34

- **P97**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:484–501`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P97]

[P97]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L484-L501

- **P98**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:35–35`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P98]

[P98]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L35

- **P99**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:502–527`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P99]

[P99]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L502-L527

- **P100**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:36–36`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P100]

[P100]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L36

- **P101**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:232–249`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P101]

[P101]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L232-L249

- **P102**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:42–42`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P102]

[P102]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L42

- **P103**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:477–483`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P103]

[P103]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L477-L483

- **P104**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:43–43`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P104]

[P104]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L43

- **P105**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:609–633`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P105]

[P105]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L609-L633

- **P106**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:44–44`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P106]

[P106]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L44

- **P107**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:66–66`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P107]

[P107]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L66

- **P108**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:634–637`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P108]

[P108]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L634-L637

- **P109**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:67–67`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P109]

[P109]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L67

- **P110**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:53–70`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P110]

[P110]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L53-L70

- **P111**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:73–73`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P111]

[P111]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L73

- **P112**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:100–141`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P112]

[P112]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L100-L141

- **P113**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:74–74`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P113]

[P113]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L74

- **P114**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:75–75`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P114]

[P114]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L75

- **P115**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:76–76`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P115]

[P115]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L76

- **P116**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:88–88`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P116]

[P116]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L88

- **P117**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:142–156`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P117]

[P117]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L142-L156

- **P118**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:89–89`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P118]

[P118]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L89

- **P119**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:95–95`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P119]

[P119]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L95

- **P120**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:97–99`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P120]

[P120]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L97-L99

- **P121**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:96–96`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P121]

[P121]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L96

- **P122**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:219–231`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P122]

[P122]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L219-L231

- **P123**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:97–97`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P123]

[P123]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L97

- **P124**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:686–698`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P124]

[P124]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L686-L698

- **P125**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:98–98`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P125]

[P125]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L98

- **P126**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:699–712`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P126]

[P126]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L699-L712

- **P127**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:99–99`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P127]

[P127]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L99

- **P128**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:713–730`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P128]

[P128]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L713-L730

- **P129**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:100–100`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P129]

[P129]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L100

- **P130**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:731–735`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P130]

[P130]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L731-L735

- **P131**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:101–101`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P131]

[P131]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L101

- **P132**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:736–748`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P132]

[P132]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L736-L748

- **P133**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:102–102`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P133]

[P133]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L102

- **P134**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:546–550`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P134]

[P134]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L546-L550

- **P135**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:103–103`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P135]

[P135]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L103

- **P136**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:551–564`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P136]

[P136]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L551-L564

- **P137**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:104–104`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P137]

[P137]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L104

- **P138**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:565–569`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P138]

[P138]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L565-L569

- **P139**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:105–105`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P139]

[P139]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L105

- **P140**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:570–573`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P140]

[P140]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L570-L573

- **P141**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:106–106`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P141]

[P141]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L106

- **P142**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:388–454`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P142]

[P142]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L388-L454

- **P143**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:107–107`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P143]

[P143]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L107

- **P144**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:108–108`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P144]

[P144]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L108

- **P145**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:109–109`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P145]

[P145]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L109

- **P146**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:110–110`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P146]

[P146]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L110

- **P147**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:111–111`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P147]

[P147]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L111

- **P148**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:112–112`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P148]

[P148]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L112

- **P149**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:113–113`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P149]

[P149]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L113

- **P150**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:455–469`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P150]

[P150]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L455-L469

- **P151**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:114–114`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P151]

[P151]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L114

- **P152**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:115–115`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P152]

[P152]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L115

- **P153**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:574–599`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P153]

[P153]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L574-L599

- **P154**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:116–116`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P154]

[P154]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L116

- **P155**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:124–124`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P155]

[P155]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L124

- **P156**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:32–52`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P156]

[P156]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L32-L52

- **P157**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:125–125`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P157]

[P157]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L125

- **P158**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:638–641`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P158]

[P158]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L638-L641

- **P159**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:126–126`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P159]

[P159]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L126

- **P160**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:642–654`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P160]

[P160]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L642-L654

- **P161**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:127–127`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P161]

[P161]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L127

- **P162**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:673–685`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P162]

[P162]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L673-L685

- **P163**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:128–128`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P163]

[P163]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L128

- **P164**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:157–201`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P164]

[P164]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L157-L201

- **P165**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:129–129`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P165]

[P165]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L129

- **P166**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:130–130`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P166]

[P166]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L130

- **P167**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:131–131`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P167]

[P167]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L131

- **P168**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:132–132`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P168]

[P168]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L132

- **P169**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:133–133`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P169]

[P169]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L133

- **P170**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:134–134`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P170]

[P170]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L134

- **P171**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:142–142`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P171]

[P171]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L142

- **P172**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:215–218`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P172]

[P172]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L215-L218

- **P173**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:143–143`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P173]

[P173]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L143

- **P174**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:250–253`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P174]

[P174]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L250-L253

- **P175**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:144–144`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P175]

[P175]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L144

- **P176**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:254–260`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P176]

[P176]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L254-L260

- **P177**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:154–154`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P177]

[P177]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L154

- **P178**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:280–331`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P178]

[P178]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L280-L331

- **P179**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:155–155`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P179]

[P179]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L155

- **P180**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:332–338`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P180]

[P180]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L332-L338

- **P181**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:156–156`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P181]

[P181]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L156

- **P182**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:343–368`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P182]

[P182]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L343-L368

- **P183**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:157–157`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P183]

[P183]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L157

- **P184**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:369–375`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P184]

[P184]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L369-L375

- **P185**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:158–158`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P185]

[P185]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L158

- **P186**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:376–382`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P186]

[P186]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L376-L382

- **P187**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:159–159`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P187]

[P187]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L159

- **P188**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:383–387`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P188]

[P188]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L383-L387

- **P189**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:169–169`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P189]

[P189]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L169

- **P190**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:261–265`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P190]

[P190]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L261-L265

- **P191**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:170–170`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P191]

[P191]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L170

- **P192**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:266–270`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P192]

[P192]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L266-L270

- **P193**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:171–171`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P193]

[P193]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L171

- **P194**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:271–275`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P194]

[P194]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L271-L275

- **P195**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:172–172`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P195]

[P195]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L172

- **P196**: `third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json:600–608`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P196]

[P196]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/schemas/settings.schema.json#L600-L608

- **P197**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:208–217`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P197]

[P197]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L208-L217

- **P198**: `third_party/pi-mono/packages/coding-agent/src/core/settings-schema.ts:299–315`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P198]

[P198]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-schema.ts#L299-L315

- **P199**: `third_party/pi-mono/packages/coding-agent/src/core/settings-manager.ts:397–455`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P199]

[P199]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L397-L455

