# Content catalog

Generated from `SKILL.md` and subagent frontmatter with:

```bash
python scripts/list_content.py --format markdown
```


| Kind | Name | Description |
| --- | --- | --- |
| skill | `accessibility-audit` | Audit user interfaces for WCAG 2.1/2.2 AA/AAA conformance, ARIA semantics, keyboard operability, screen reader compatibility, and color contrast. |
| skill | `api-design` | Design an API contract — resources, operations, schemas, errors, versioning, and pagination — from requirements before implementation, producing a completed api-contract handoff. |
| skill | `ast-manipulation-codemods` | Write Abstract Syntax Tree (AST) transformers to automate large-scale, syntax-aware codebase migrations. |
| skill | `author-agentkit-content` | Create or revise indium-agentkit skills, subagents, templates, and their validation and catalog files to the repository authoring standard. Use when adding, rewriting, or reviewing content in this agentkit repository. Internal to this repository; not for consumer projects. |
| skill | `backend-api` | Build robust typed API endpoints with safe contracts. |
| skill | `ci-pipeline` | Design reliable CI pipelines with useful required checks. |
| skill | `compliance-audit` | Audit code, configuration, and data flows against GDPR, SOC 2, HIPAA, and PCI-DSS compliance controls including PII redaction and audit logging. |
| skill | `contract-testing` | Design and implement consumer-driven contract tests (Pact, MSW, Playwright) to verify interface compatibility between microservices and frontend/backend boundaries. |
| skill | `cryptographic-protocol-implementation` | Implement modern authenticated encryption, secure key exchange, mTLS, and post-quantum cryptographic primitives. |
| skill | `data-pipeline-design` | Design safe ETL/ELT pipelines, data warehouse schemas, partition strategies, idempotency controls, and data quality assertions before implementation. |
| skill | `database-design` | Design safe PostgreSQL schemas and staged migrations. |
| skill | `delegate-work` | Plan bounded subagent delegation with structured handoffs, delegation packets, and verification. |
| skill | `dependency-audit` | Audit project dependencies for vulnerabilities, staleness, license risk, unused packages, and version-policy compliance using manifests, lockfiles, and available scanning tools. |
| skill | `deployment-safety` | Plan and verify staged deployments with safe rollback. |
| skill | `estimate-work` | Decompose technical tasks into scope, story points, PERT effort estimations, risk multipliers, and delivery sequences. |
| skill | `event-sourcing-architecture` | Design immutable event logs, CQRS command/query models, and materialized view projections. |
| skill | `frontend-ship` | Build accessible, typed, expressive, glassmorphic, and 3D frontend features end to end. |
| skill | `hardware-in-loop-testing` | Interface hardware-in-the-loop (HIL) simulation testbeds with embedded firmware endpoints under noise and faults. |
| skill | `incident-triage` | Triage incidents with evidence, mitigation, and follow-up. |
| skill | `infrastructure-review` | Review infrastructure for security, reliability, and cost risks. |
| skill | `llm-eval-harness` | Design and execute evaluation benchmarks for prompts, RAG retrieval pipelines, and agent tools to measure cost, latency, accuracy, and guardrails. |
| skill | `load-testing-suite` | Design, configure, and execute performance load and stress testing suites (k6, Locust) with latency SLAs and throughput targets. |
| skill | `local-llm-integration` | Deploy, optimize, and serve quantized open-weight local LLMs (vLLM/Ollama/llama.cpp) with GQA-aware VRAM pre-flight validation, process-scoped cleanup, and healthcheck polling. |
| skill | `mobile-release-safety` | Plan and audit mobile application releases (iOS/Android/React Native/Flutter) covering app store compliance, code signing, feature flags, OTA updates, and crash symbolication. |
| skill | `multi-agent-workflow-design` | Design typed state machines, JSON-RPC handoff protocols, and delegation topologies for multi-agent execution. |
| skill | `observability-setup` | Instrument code with structured logging, metrics, distributed tracing, or alerting following existing observability patterns and avoiding credential exposure. |
| skill | `onboard-to-codebase` | Generate comprehensive developer onboarding guides, architecture orientations, dependency graphs, and environment setup specs. |
| skill | `performance-optimization` | Measure, analyze, and optimize a specific performance bottleneck through profiling, targeted change, and comparative re-measurement with evidence. |
| skill | `plan-change` | Turn feature requests, bug reports, refactors, or technical proposals into implementation-ready plans with scope, acceptance criteria, affected areas, test seams, risks, and ordered steps. |
| skill | `prototype-spike` | Investigate technical approaches through time-boxed, throwaway spikes that produce empirical evidence and go/no-go recommendations. |
| skill | `refactor-code` | Restructure, extract, inline, or simplify code to improve cohesion and maintainability while strictly preserving observable behavior verified by tests. |
| skill | `release-notes` | Create accurate user-facing release notes or changelog entries from a commit range, tags, issues, and repository history. |
| skill | `resolve-merge-conflicts` | Resolve Git merge or rebase conflicts by recovering each side's intent, preserving compatible behavior, validating the result, and documenting trade-offs. |
| skill | `review-change` | Review local diffs, branches, commit ranges, or pull requests for correctness, regressions, security, performance, conventions, and test coverage. |
| skill | `rtos-firmware-development` | Write deterministic, low-latency task schedulers and peripheral drivers for embedded FreeRTOS/Zephyr devices. |
| skill | `safe-migration` | Plan and implement safe schema, API, configuration, storage, or file-format migrations with compatibility analysis, staged rollout, rollback, and evidence-based verification. |
| skill | `security-review` | Review a scoped code change, endpoint, integration, configuration, or infrastructure definition for security risks by tracing assets, trust boundaries, authorization, input handling, and exploit paths. |
| skill | `synthetic-data-generation` | Implement deterministic scripts to populate databases with referentially solid, PII-free data. |
| skill | `systematic-debugging` | Investigate a bug, failing test, regression, unexpected output, or production issue through reproduction, evidence, hypotheses, root-cause analysis, and a regression test before fixing it. |
| skill | `test-first-change` | Plan and implement behavior changes, bug fixes, or refactors using Test-Driven Development (TDD) red-green-refactor cycles and behavior-level test seams. |
| skill | `threat-modeling` | Perform structured threat modeling (STRIDE/PASTA) on architecture diagrams, system interfaces, and data flow graphs before implementation. |
| skill | `verify-and-ship` | Verify completed repository changes, run test and lint commands, audit diffs for secrets, and commit/publish cleanly according to repository rules. |
| skill | `write-documentation` | Author, update, or audit project documentation — READMEs, architecture decisions, API references, onboarding guides, and inline doc — from code evidence. |
| skill | `write-runbook` | Create or update an operational runbook for a service, feature, or failure mode with detection, diagnosis, mitigation, recovery, and escalation procedures. |
| subagent | `accessibility-checker` | Audit user interface markup, ARIA roles, contrast, and focus order read-only. |
| subagent | `agent-orchestrator` | Read-only specialist that inspects multi-agent system states, JSON-RPC routing boundaries, context window growth, and delegation chains to prevent execution loops and payload bloat. |
| subagent | `api-designer` | Design typed API contracts from requirements without editing code. |
| subagent | `backend-builder` | Implements one bounded server-side slice (endpoint, handler, service, validation boundary, or backend test) against an agreed API contract, then returns verifiable evidence. Use when the contract and file scope are already decided. Edits only assigned paths. |
| subagent | `ci-verifier` | Diagnose CI workflows and report exact verification evidence. |
| subagent | `compliance-auditor` | Read-only compliance specialist that audits code, data flows, PII redaction, encryption, and audit logs against compliance control standards. |
| subagent | `data-engineer` | Audit data pipelines, models, quality, and governance read-only. |
| subagent | `database-architect` | Analyze schemas and propose safe, verified migration plans. |
| subagent | `debugger` | Investigates a bug, failing test, or regression by reproducing it, tracing the divergence, and testing competing hypotheses, then returns the root cause with evidence and no fix. Use when the cause of wrong behavior is unknown and evidence gathering can run in parallel with other work. Read-only. |
| subagent | `dependency-auditor` | Audit dependency vulnerabilities, staleness, and license risk read-only. |
| subagent | `doc-writer` | Audit and draft project documentation, API specs, and onboarding guides read-only. |
| subagent | `ebpf-specialist` | Audit eBPF bytecode, XDP packet processing programs, eBPF maps, and kernel-level tracing probes for safety, side effects, and verifier bounds read-only. |
| subagent | `estimator` | Assess complexity, technical risk, dependencies, and effort read-only. |
| subagent | `explorer` | Map repository structure, entry points, dependencies, and data flows read-only. |
| subagent | `formal-verifier` | Evaluate formal specifications (TLA+, Alloy, Dafny), state space invariants, temporal logic properties, and mathematical proofs read-only. |
| subagent | `frontend-builder` | Implements one bounded user-interface slice (component, page, form, or client data flow) in the project's existing framework and design system, with tests. Use when the UI behavior, API contract, and file scope are agreed. Edits only assigned paths. |
| subagent | `frontend-reviewer` | Reviews frontend components, state management, rendering boundaries, styling tokens, and bundle impact for correctness and performance risks. Use proactively after UI changes or before merging frontend work. Not for accessibility audits (use the accessibility-checker subagent). Read-only. |
| subagent | `incident-commander` | Coordinate evidence-based incident response without production edits. |
| subagent | `infrastructure-reviewer` | Reviews Dockerfiles, Terraform and other infrastructure-as-code, Kubernetes and Helm manifests, and cloud configuration for security, reliability, and cost risks. Use proactively before merging infrastructure changes or when an environment's posture is in question. Read-only. |
| subagent | `iot-embedded-auditor` | Audit RTOS task scheduling, firmware update routines, memory layout, and peripheral hardware interfaces read-only. |
| subagent | `llm-evaluator` | Evaluate LLM prompts, RAG retrieval accuracy, and tool-calling benchmarks read-only. |
| subagent | `local-model-specialist` | Evaluate on-device LLM integration, GGUF quantization levels, and KV cache memory constraints read-only. |
| subagent | `migration-planner` | Audit database schemas, data migrations, and breaking API changes read-only. |
| subagent | `mobile-specialist` | Audit iOS, Android, React Native, and Flutter app builds read-only. |
| subagent | `performance-profiler` | Measure performance bottlenecks against a reproducible baseline. |
| subagent | `release-engineer` | Audit release readiness, git changelogs, build artifacts, and deployment safety read-only. |
| subagent | `resilience-reviewer` | Review failure handling, retries, limits, and recovery paths read-only. |
| subagent | `reviewer` | Review local diffs and PRs for correctness, security, performance, and style read-only. |
| subagent | `runbook-writer` | Draft evidence-backed operational runbooks from system behavior. |
| subagent | `security-reviewer` | Review scoped changes for trust-boundary and exploit-path risks. |
| subagent | `synthetic-data-architect` | Audit relational database topologies, foreign key constraints, and statistical distributions to design referentially intact, PII-free synthetic data schemas read-only. |
| subagent | `test-writer` | Adds or repairs automated tests at public behavior seams for assigned behavior, including characterization tests before a refactor and regression tests for a fixed bug, and proves they fail and pass for the right reasons. Use when test coverage is missing or a change needs red-green evidence. Edits only assigned paths. |
| subagent | `verifier` | Verify completed work against specifications, tests, and acceptance criteria read-only. |
