"""
Study Schedule & Granular Topic Tracker Service for CareerCompass.
Handles hours planning (weekdays vs weekends), role-specific dynamic stack selectors,
syllabus generation, subtopic markers, and progress tracking.
"""

import json
import os
from typing import List, Dict, Any
from database.db import get_connection


# ── Role-Specific Stack Configuration Schemas ──────────────────────────────
# The catalog lives in data/stacks.json so specialization content can be updated
# without touching application code.
STACKS_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "stacks.json"
)


def _load_stack_schemas() -> Dict[str, Dict[str, Any]]:
    """Loads the per-role specialization stacks from data/stacks.json."""
    try:
        with open(STACKS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("stacks", {})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


ROLE_STACK_SCHEMAS = _load_stack_schemas()


def get_role_stack_schema(role_id: str) -> Dict[str, Any]:
    """Returns the custom 3-category stack configuration for the chosen role."""
    if role_id in ROLE_STACK_SCHEMAS:
        return ROLE_STACK_SCHEMAS[role_id]

    # Clean default fallback for unspecified roles
    return {
        "dim1": {
            "label": "1. Core Programming Stack",
            "options": ["Python", "Java", "TypeScript / JavaScript", "Go", "C++"]
        },
        "dim2": {
            "label": "2. Data & Storage System",
            "options": ["PostgreSQL (Relational SQL)", "MongoDB (Document NoSQL)", "Redis Caching", "Cloud Data Lake"]
        },
        "dim3": {
            "label": "3. Framework & Tooling",
            "options": ["REST API Architecture", "Docker Containerization", "Git & CI/CD Pipelines", "System Architecture Fundamentals"]
        }
    }


def save_study_schedule(
    user_id: int,
    role_id: str,
    weekday_hours: float,
    weekend_hours: float,
    target_languages: List[str]
) -> Dict[str, Any]:
    """Saves or updates user's study schedule and calculates weekly throughput."""
    weekday_hours = max(0.5, float(weekday_hours))
    weekend_hours = max(0.5, float(weekend_hours))
    weekly_total = (weekday_hours * 5.0) + (weekend_hours * 2.0)

    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO study_schedules (
                    user_id, role_id, weekday_hours, weekend_hours,
                    weekly_total_hours, target_languages_json, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                );
            """, (
                user_id,
                role_id,
                weekday_hours,
                weekend_hours,
                weekly_total,
                json.dumps(target_languages)
            ))
        return {
            "weekday_hours": weekday_hours,
            "weekend_hours": weekend_hours,
            "weekly_total_hours": weekly_total,
            "target_languages": target_languages
        }
    finally:
        conn.close()


def get_study_schedule(user_id: int, role_id: str) -> Dict[str, Any]:
    """Retrieves current study schedule for user & role, or sensible defaults."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT weekday_hours, weekend_hours, weekly_total_hours, target_languages_json
            FROM study_schedules WHERE user_id = ? AND role_id = ?;
        """, (user_id, role_id))
        row = cursor.fetchone()
        if row:
            return {
                "weekday_hours": row["weekday_hours"],
                "weekend_hours": row["weekend_hours"],
                "weekly_total_hours": row["weekly_total_hours"],
                "target_languages": json.loads(row["target_languages_json"] or "[]")
            }

        # Provide sensible default options from the role schema
        schema = get_role_stack_schema(role_id)
        default_choices = [
            schema["dim1"]["options"][0],
            schema["dim2"]["options"][0],
            schema["dim3"]["options"][0]
        ]
        return {
            "weekday_hours": 1.5,
            "weekend_hours": 4.0,
            "weekly_total_hours": 15.5,
            "target_languages": default_choices
        }
    finally:
        conn.close()


# ── Specialist Syllabus Blocks ────────────────────────────────────────────────
# The engine above maps a fixed vocabulary of choices onto topics. When the role
# catalogue grew past its original 15 roles, the newer specialisations (mobile,
# games, embedded, design, offensive security, ...) needed content of their own.
# Each entry below is (keywords, category, topic_name, subtopics, hours) and is
# matched against the joined choice text, exactly like the branches above.
#
# The keywords are deliberately absent from the original roles' stacks.json
# options, which is what keeps those roles' study plans identical to before —
# tests/test_tracker_syllabus.py asserts that invariant.
_SPECIALIST_SYLLABUS = (
    # ── Mobile engineering ─────────────────────────────────────────────────
    (("kotlin",), "Mobile Platform Core", "Kotlin Coroutines, Jetpack Compose & Android Architecture", [
        "Android lifecycle, configuration changes and process death",
        "Coroutines & Flow: structured concurrency, cancellation and dispatchers",
        "Jetpack Compose: recomposition, state hoisting and previews",
        "Hilt dependency injection with repository/use-case layering",
    ], 10.0),
    (("swift",), "Mobile Platform Core", "Swift Concurrency, ARC & SwiftUI State Management", [
        "Optionals, protocols, generics and value semantics",
        "ARC, retain cycles and memory graph debugging",
        "async/await, actors and MainActor isolation",
        "SwiftUI state, @Observable models and navigation",
    ], 10.0),
    (("flutter", "dart"), "Mobile Platform Core", "Flutter, Dart & Cross-Platform Widget Architecture", [
        "Widget tree, layout constraints and composition",
        "State management: setState vs Riverpod/Bloc",
        "Dart isolates, the event loop and async patterns",
        "Platform channels and platform-specific UI details",
    ], 10.0),
    (("graphql",), "Mobile Data Layer", "Mobile API Integration & Offline-First Sync", [
        "REST vs GraphQL: schema, queries, mutations and pagination",
        "Retrofit/Apollo clients, caching and auth interceptors",
        "Offline-first storage, sync queues and conflict resolution",
        "Retry, backoff and honest network-failure UX",
    ], 10.0),
    (("firebase",), "Mobile Data Layer", "Firebase Auth, Firestore & Push Notifications", [
        "Firebase Auth flows, custom claims and session handling",
        "Firestore modelling, security rules and realtime listeners",
        "FCM push, notification channels and deep links",
        "Crashlytics, Remote Config and product analytics",
    ], 8.0),
    (("coredata", "local persistence"), "Mobile Data Layer", "On-Device Persistence, Caching & Migrations", [
        "Room/CoreData schema design and migrations",
        "Cache invalidation, TTL strategy and stale-while-revalidate",
        "Threading, query performance and large result sets",
        "Encrypting data at rest and secure storage choices",
    ], 8.0),
    (("app store", "play store"), "Mobile Release Engineering", "App Store & Play Store Release Engineering", [
        "Signing, keystores and provisioning profiles",
        "Versioning, staged rollouts and feature flags",
        "Store review guidelines and privacy disclosures",
        "Automated builds and releases with Fastlane and Gradle",
    ], 8.0),
    (("mobile performance", "startup performance", "app performance"), "Mobile Release Engineering", "App Performance Profiling & Startup Time", [
        "Cold/warm startup analysis and baseline profiles",
        "Memory leaks, GC pressure and allocation profiling",
        "Frame rendering, jank and battery drain",
        "Crash clustering, ANR triage and regression gates",
    ], 8.0),

    # ── Game development ───────────────────────────────────────────────────
    (("unity",), "Game Engine & Gameplay", "Unity C# Gameplay Programming & Engine Loop", [
        "MonoBehaviour lifecycle and the update loop",
        "GameObjects, components, prefabs and scene composition",
        "Coroutines, events and ScriptableObject data",
        "Editor tooling and asset serialisation",
    ], 12.0),
    (("unreal",), "Game Engine & Gameplay", "Unreal Engine C++ & Blueprint Architecture", [
        "Actor/component model and UObject lifecycle",
        "Drawing the Blueprint ↔ C++ boundary cleanly",
        "Replication, ownership and network roles",
        "Asset pipelines, plugins and packaging",
    ], 12.0),
    (("graphics", "shader", "rendering"), "Rendering & Visuals", "Real-Time Rendering & Shader Programming", [
        "Rasterisation pipeline and coordinate spaces",
        "HLSL/GLSL shaders and material graphs",
        "Lighting models, shadows and post-processing",
        "Batching, LODs, culling and overdraw",
    ], 12.0),
    (("physics",), "Rendering & Visuals", "Game Physics, Collision & Character Controllers", [
        "Rigid bodies, colliders, layers and collision matrices",
        "Continuous collision detection and tunnelling",
        "Kinematic character controllers and movement feel",
        "Joints, ragdolls and stability tuning",
    ], 8.0),
    (("netcode", "multiplayer"), "Multiplayer & Live Systems", "Multiplayer Netcode & State Synchronisation", [
        "Client-server vs peer-to-peer topology",
        "Tick rate, interpolation and lag compensation",
        "State replication, ownership and authority",
        "Matchmaking, lobbies and anti-cheat basics",
    ], 12.0),
    (("frame budget", "frame profiling"), "Multiplayer & Live Systems", "Frame Profiling & Performance Budgets", [
        "CPU-bound vs GPU-bound analysis",
        "Draw calls, overdraw and instancing",
        "Memory budgets and asset streaming",
        "Profiler workflows and regression tracking",
    ], 8.0),
    (("live-ops", "live ops", "monetis", "monetiz"), "Multiplayer & Live Systems", "Live-Ops, Telemetry & Monetisation Systems", [
        "Remote config and content update pipelines",
        "Event telemetry and funnel instrumentation",
        "Battle passes, in-app purchases and economy tuning",
        "A/B testing and player segmentation",
    ], 8.0),

    # ── Embedded & firmware ────────────────────────────────────────────────
    (("firmware", "bare-metal", "microcontroller"), "Firmware & Real-Time Systems", "Embedded C, Memory-Mapped I/O & Firmware Architecture", [
        "Bit manipulation, volatile and register access",
        "Memory-mapped I/O, clocks and peripheral configuration",
        "Interrupts, ISRs and latency budgets",
        "Linker scripts, startup code and memory layout",
    ], 12.0),
    (("device driver", "embedded linux"), "Firmware & Real-Time Systems", "Embedded Linux & Device Driver Development", [
        "Kernel modules, device tree and platform drivers",
        "Character/block devices, ioctls and sysfs",
        "Cross-compilation, Yocto and root filesystems",
        "Debugging with ftrace, dmesg and gdb",
    ], 12.0),
    (("rtos",), "Firmware & Real-Time Systems", "RTOS Scheduling, Tasks & Real-Time Concurrency", [
        "Tasks, priorities and preemptive scheduling",
        "Semaphores, mutexes, queues and event flags",
        "Priority inversion, deadlocks and ISR-safe APIs",
        "Response-time analysis and jitter budgets",
    ], 10.0),
    (("i2c", "spi", "uart", "can bus"), "Hardware Interfaces", "Serial Protocols: I2C, SPI, UART & CAN", [
        "I2C addressing, clock stretching and arbitration",
        "SPI modes, chip selects and DMA transfers",
        "UART framing, flow control and buffering",
        "CAN frames, arbitration IDs and higher-layer protocols",
    ], 10.0),
    (("oscilloscope", "logic analyser", "logic analyzer", "jtag"), "Hardware Interfaces", "Board Bring-Up & Hardware Debugging", [
        "Reading schematics and datasheets critically",
        "Oscilloscope and logic analyser capture and decode",
        "JTAG/SWD stepping and register inspection",
        "Systematic bring-up of a new board revision",
    ], 8.0),
    (("misra", "autosar"), "Hardware Interfaces", "MISRA-C, AUTOSAR & Functional Safety Discipline", [
        "MISRA-C rules and static analysis in CI",
        "AUTOSAR layering: RTE, BSW and software components",
        "Requirements traceability and unit testing on target",
        "Safety documentation and review habits",
    ], 8.0),

    # ── Analytics engineering & product analytics ──────────────────────────
    (("dimensional", "star schema"), "Warehouse Modelling", "Dimensional Modelling & Star Schemas", [
        "Grain, fact tables and conformed dimensions",
        "Slowly changing dimensions (types 1–3)",
        "Star vs snowflake trade-offs and bridge tables",
        "Modelling snapshots, events and accumulators",
    ], 10.0),
    (("semantic layer", "semantics"), "Warehouse Modelling", "Semantic Layer & Metrics Governance", [
        "Defining each metric exactly once",
        "Semantic models over warehouse tables",
        "Consistency between dashboards and notebooks",
        "Documentation, ownership and deprecation",
    ], 10.0),
    (("analytics engineering",), "Warehouse Modelling", "Analytics Engineering: Models, Tests & Lineage", [
        "Staging → intermediate → mart layering",
        "Tests, contracts and freshness checks",
        "Incremental models and cost-aware materialisation",
        "Lineage, documentation and code review",
    ], 10.0),
    (("data quality",), "Pipeline Operations", "Data Quality, Contracts & Reconciliation", [
        "Schema and contract enforcement at ingest",
        "Anomaly detection and reconciliation checks",
        "Late, duplicate and out-of-order data",
        "Responding when a pipeline breaks",
    ], 10.0),
    (("freshness", "pipeline sla"), "Pipeline Operations", "Pipeline Freshness, Backfills & SLAs", [
        "Batch vs streaming freshness expectations",
        "Retries, backfills and idempotent runs",
        "Run metadata, alerting and on-call handover",
        "Cost-aware scheduling windows",
    ], 8.0),
    (("taxonomy", "instrumentation"), "Product Analytics", "Event Instrumentation & Tracking Plans", [
        "Designing an event and parameter taxonomy",
        "Tracking plans, naming conventions and governance",
        "Client-side vs server-side event implementation",
        "Validating data quality after releases",
    ], 8.0),
    (("experimentation",), "Experimentation", "Experimentation: A/B Test Design & Readouts", [
        "Hypotheses, primary metrics and guardrails",
        "Sample sizing and statistical power",
        "Randomisation, A/A checks and sample-ratio mismatch",
        "Interpreting results honestly and shipping the decision",
    ], 10.0),
    (("uplift", "causal analysis"), "Experimentation", "Causal Inference & Uplift Measurement", [
        "Confounders, selection bias and DAG thinking",
        "Difference-in-differences and propensity matching",
        "Uplift modelling for targeting decisions",
        "What to do when a clean experiment is impossible",
    ], 10.0),
    (("decision readouts",), "Experimentation", "Data Storytelling & Decision Readouts", [
        "Structuring a readout: question → evidence → action",
        "Choosing the right chart for the claim",
        "Handling uncertainty and disagreement",
        "Writing the one-page decision memo",
    ], 8.0),

    # ── Language & vision AI ───────────────────────────────────────────────
    (("retrieval", "vector indexing"), "Language Modelling", "Retrieval-Augmented Generation & Vector Search", [
        "Chunking strategies and embedding model choice",
        "Vector indexes and hybrid keyword + dense retrieval",
        "Re-ranking, citations and grounding",
        "Measuring retrieval quality (hit rate, nDCG)",
    ], 12.0),
    (("evaluation harness", "nlp evaluation", "human review"), "Language Modelling", "Evaluation Harnesses & Human Review", [
        "Offline metrics (F1, BLEU, ROUGE, nDCG)",
        "Golden sets and adversarial cases",
        "LLM-as-judge and its failure modes",
        "Annotation guidelines and inter-annotator agreement",
    ], 10.0),
    (("opencv", "detection", "segmentation", "computer vision"), "Vision Modelling", "Detection, Segmentation & OCR Pipelines", [
        "Image preprocessing, augmentation and normalisation",
        "Object detection families and instance segmentation",
        "OCR and text extraction pipelines",
        "Metrics: IoU, mAP and per-class error analysis",
    ], 12.0),
    (("video analytics", "multi-object tracking"), "Vision Modelling", "Video Analytics & Multi-Object Tracking", [
        "Frame sampling and temporal consistency",
        "Tracking-by-detection and re-identification",
        "Streaming ingestion and windowed inference",
        "Latency, throughput and idempotent processing",
    ], 10.0),
    (("edge inference", "onnx", "tensorrt", "quantis", "quantiz"), "Vision Deployment", "Edge Inference: Quantisation, ONNX & TensorRT", [
        "Exporting models to ONNX and operator compatibility",
        "INT8/FP16 quantisation and the accuracy it costs",
        "Batching, concurrency and accelerator streams",
        "Benchmarking latency on the real target device",
    ], 10.0),
    (("dataset curation", "annotation"), "Vision Deployment", "Dataset Curation, Labelling & Versioning", [
        "Sampling strategy and class balance",
        "Labelling guidelines, QA and agreement metrics",
        "Dataset versioning and reproducible splits",
        "Finding label noise, leakage and duplicate images",
    ], 8.0),

    # ── ML platform & production ML ────────────────────────────────────────
    (("drift", "retraining"), "Production ML", "Drift Monitoring & Retraining Triggers", [
        "Data drift vs concept drift and how to detect them",
        "Monitoring features, predictions and outcomes",
        "Alert thresholds and investigation playbooks",
        "Automated retraining, shadow deploys and rollback",
    ], 10.0),
    (("gpu",), "Production ML", "GPU Capacity & Cost Engineering", [
        "GPU types, memory limits and utilisation metrics",
        "Queueing, quotas and fair scheduling",
        "Spot/reserved mix and cost per experiment",
        "Right-sizing inference replicas",
    ], 8.0),

    # ── Platform, delivery & reliability ───────────────────────────────────
    (("observability", "slo"), "Reliability Engineering", "Observability: Metrics, Traces & SLOs", [
        "The three pillars: metrics, logs and traces",
        "SLIs, SLOs and error budgets",
        "OpenTelemetry instrumentation and sampling",
        "Dashboards that answer a real question",
    ], 10.0),
    (("incident response", "postmortem"), "Reliability Engineering", "Incident Response, On-Call & Postmortems", [
        "Severity levels, incident roles and comms",
        "Mitigation first: runbooks and rollback",
        "Blameless postmortems and tracked actions",
        "Reducing toil and alert fatigue",
    ], 8.0),
    (("progressive delivery", "canary", "blue-green"), "Delivery Engineering", "Release Automation, Canaries & Rollbacks", [
        "Automated gates between build and production",
        "Canary analysis and progressive rollouts",
        "Feature flags and backward-compatible migrations",
        "Fast, rehearsed rollback strategies",
    ], 10.0),
    (("trunk-based", "merge queues"), "Delivery Engineering", "Trunk-Based Development & Merge Queues", [
        "Short-lived branches and small pull requests",
        "Merge queues and required status checks",
        "Release trains and versioning discipline",
        "Avoiding long-lived divergence",
    ], 8.0),
    (("finops", "cloud cost"), "Delivery Engineering", "Cloud Cost Engineering (FinOps)", [
        "Tagging, allocation and showback per team",
        "Right-sizing compute and storage classes",
        "Spot/reserved mix and autoscaling policy",
        "Unit economics and budget alerts",
    ], 8.0),

    # ── Database engineering ───────────────────────────────────────────────
    (("replication", "failover"), "Database Reliability", "Replication, Failover & High Availability", [
        "Synchronous vs asynchronous replication",
        "Read replicas, lag and consistency trade-offs",
        "Automated failover and avoiding split-brain",
        "Rehearsing failover with game days",
    ], 10.0),
    (("point-in-time recovery", "backup", "restore"), "Database Reliability", "Backup, Restore & Point-in-Time Recovery", [
        "Full, incremental and logical vs physical backups",
        "Write-ahead log/binlog archiving and retention",
        "Practising restores: an untested backup is not a backup",
        "RPO/RTO targets and restore drills",
    ], 10.0),
    (("sharding", "horizontal scale", "partitioning"), "Database Reliability", "Sharding, Partitioning & Horizontal Scale", [
        "Partitioning (range, list, hash) vs sharding",
        "Choosing and evolving a shard key",
        "Cross-shard queries and transactions",
        "Online resharding and data movement",
    ], 10.0),
    (("query plan", "indexing", "isolation levels"), "Database Performance", "Query Plans, Indexing & Transaction Isolation", [
        "Reading EXPLAIN / EXPLAIN ANALYZE plans",
        "Index types, selectivity and covering indexes",
        "Locking, deadlocks and isolation levels",
        "Connection pooling and prepared statements",
    ], 10.0),
    (("zero-downtime", "zero downtime", "schema migration"), "Database Performance", "Schema Migrations & Zero-Downtime Changes", [
        "The expand/contract pattern for live schema change",
        "Safe defaults and batched backfills",
        "Locking risks and long-running DDL",
        "Coordinating application deploys with migrations",
    ], 8.0),

    # ── Networking ─────────────────────────────────────────────────────────
    (("switching", "vlan", "subnetting", "subnet design"), "Network Design", "Switching, VLANs & Subnet Design", [
        "VLAN segmentation, trunking and 802.1Q",
        "Spanning tree and loop prevention",
        "IP addressing, subnetting and route summarisation",
        "Layer 2 vs layer 3 boundaries and inter-VLAN routing",
    ], 10.0),
    (("ospf", "bgp", "dynamic routing"), "Network Design", "Dynamic Routing: OSPF, BGP & Redistribution", [
        "OSPF areas, costs and adjacency states",
        "BGP attributes, path selection and peering",
        "Route redistribution and loop prevention",
        "Convergence and failover behaviour",
    ], 10.0),
    (("dhcp", "load balancing"), "Network Design", "DNS, DHCP & Load Balancing", [
        "Record types, zones and delegation",
        "DHCP scopes, reservations and relay agents",
        "Layer 4 vs layer 7 load balancing and health checks",
        "Caching, TTLs and troubleshooting resolution",
    ], 8.0),
    (("firewall", "vpn"), "Network Security & Operations", "Firewalls, VPNs & Zero-Trust Access", [
        "Stateful rules, NAT and policy ordering",
        "Site-to-site and remote-access VPNs",
        "Segmentation and zero-trust access models",
        "Auditing and troubleshooting blocked flows",
    ], 10.0),
    (("sd-wan", "sdwan", "hybrid cloud"), "Network Security & Operations", "Hybrid Cloud Connectivity & SD-WAN", [
        "Interconnects, peering and transit options",
        "Overlay tunnels and traffic engineering",
        "Bandwidth, latency and path selection",
        "Monitoring connectivity across many sites",
    ], 8.0),

    # ── Security engineering ───────────────────────────────────────────────
    (("threat model", "threat modelling", "threat modeling", "secure code review"), "Secure Development", "Threat Modelling & Secure Code Review", [
        "STRIDE and mapping assets to trust boundaries",
        "Reviewing code for injection, authorisation and deserialisation flaws",
        "Design-review checklists for new features",
        "Turning findings into guardrails and regression tests",
    ], 12.0),
    (("access control", "authorisation", "authorization", "authz"), "Secure Development", "Authentication, Authorisation & Session Security", [
        "OAuth2/OIDC flows and their common pitfalls",
        "RBAC/ABAC and the principle of least privilege",
        "Session, token and refresh-token handling",
        "IDOR/BOLA and multi-tenant isolation testing",
    ], 10.0),
    (("cryptography", "secrets management", "key management"), "Secure Development", "Cryptography & Secrets Management", [
        "Symmetric/asymmetric primitives and when to use each",
        "Key rotation, KMS/HSM and envelope encryption",
        "Getting secrets out of code and config",
        "TLS configuration and certificate hygiene",
    ], 10.0),
    (("sast", "dast", "devsecops", "security scanning"), "Security Assurance", "DevSecOps: Scanning Gates & Triage", [
        "SAST/DAST/SCA and IaC scanning in CI",
        "Triaging findings without drowning developers",
        "Fixing vs flagging: workflows that get code fixed",
        "Security regression tests and policy as code",
    ], 10.0),
    (("supply-chain", "supply chain", "sbom"), "Security Assurance", "Dependency & Supply-Chain Security", [
        "SBOMs and dependency inventory",
        "Pinning, provenance and reproducible builds",
        "Typosquatting and malicious package detection",
        "Patch SLAs and coordinated upgrades",
    ], 8.0),

    # ── Offensive security ─────────────────────────────────────────────────
    (("web exploitation", "api exploitation"), "Offensive Tradecraft", "Web & API Exploitation", [
        "Mapping attack surface, including authenticated areas",
        "Injection, XSS, SSRF and file-upload chains",
        "API abuse: BOLA, mass assignment and rate limits",
        "Chaining low-severity findings into real impact",
    ], 12.0),
    (("privilege escalation",), "Offensive Tradecraft", "Linux & Windows Privilege Escalation", [
        "Enumerating misconfigurations and weak permissions",
        "Credential harvesting and reuse",
        "Container escapes and kernel-level vectors",
        "Maintaining access ethically within scope",
    ], 12.0),
    (("reconnaissance", "osint"), "Offensive Tradecraft", "Reconnaissance, OSINT & Attack Surface Mapping", [
        "Passive recon: DNS, certificates and leaked data",
        "Safe active enumeration and rate limits",
        "Mapping assets to business impact",
        "Evidence handling and scope discipline",
    ], 8.0),
    (("active directory",), "Enterprise Attack Paths", "Active Directory Attack Paths", [
        "AD structure, trusts and delegation",
        "Kerberos abuse: Kerberoasting and AS-REP roasting",
        "Lateral movement and credential tiering",
        "Detection opportunities and hardening",
    ], 12.0),
    (("cloud attack", "container attack", "iam abuse"), "Enterprise Attack Paths", "Cloud & Container Attack Paths", [
        "IAM misconfiguration and role chaining",
        "Metadata services, tokens and secret exposure",
        "Kubernetes RBAC, escapes and node compromise",
        "Cloud logging and the gaps attackers use",
    ], 12.0),
    (("phishing", "social engineering"), "Engagement Delivery", "Social Engineering & Phishing Simulations", [
        "Building realistic pretexts and target lists",
        "Campaign infrastructure and domain hygiene",
        "Measuring click and report rates responsibly",
        "Debriefing and awareness follow-through",
    ], 8.0),
    (("pentest report", "client reporting", "remediation guidance"), "Engagement Delivery", "Client Reporting & Remediation Guidance", [
        "Findings that read: evidence → impact → fix",
        "Risk ratings clients can act on",
        "Executive summaries vs technical detail",
        "Re-testing, evidence and closure",
    ], 8.0),

    # ── Product design ─────────────────────────────────────────────────────
    (("design tokens", "typography"), "Design Craft", "Design Tokens, Typography & Colour Systems", [
        "Type scales, rhythm and readability",
        "Colour systems, contrast and semantic tokens",
        "Spacing, grid and layout primitives",
        "Token naming and handoff to code",
    ], 10.0),
    (("interaction design", "micro-interaction", "microinteraction"), "Design Craft", "Interaction Design & Micro-Interactions", [
        "States: default, hover, focus, disabled and error",
        "Feedback, affordances and transitions",
        "Motion principles, easing and reduced-motion support",
        "Designing for touch and for keyboard",
    ], 8.0),
    (("information architecture", "user flows", "user flow"), "Design Craft", "Information Architecture & User Flows", [
        "Card sorting, tree testing and mental models",
        "Flows, entry points and edge-case paths",
        "Navigation patterns and findability",
        "Mapping content to real journeys",
    ], 8.0),
    (("usability", "user interview"), "Research & Evidence", "Usability Testing & User Interviews", [
        "Writing test tasks that do not lead the user",
        "Moderated vs unmoderated, and the five-user guide",
        "Task success, time on task and SEQ",
        "Affinity mapping and synthesising themes",
    ], 10.0),
    (("accessibility", "wcag", "inclusive design"), "Research & Evidence", "Accessibility, WCAG 2.2 & Inclusive Design", [
        "WCAG conformance levels and the POUR model",
        "Keyboard order, focus and screen-reader semantics",
        "Colour contrast, text scaling and motion",
        "Accessible components and testing with real users",
    ], 8.0),
    (("journey analytics", "design measurement"), "Research & Evidence", "Journey Analytics & Design Measurement", [
        "Funnels, drop-off and dead-click analysis",
        "Pairing analytics with qualitative sessions",
        "Defining design success metrics",
        "Instrumenting experiments and guardrails",
    ], 8.0),
    (("design handoff", "developer handoff", "prototyping"), "Delivery & Collaboration", "Prototyping & Developer Handoff", [
        "Fidelity choices: wireframe → prototype → spec",
        "Documenting states, edge cases and real content",
        "Handoff rituals and QA against the design",
        "Reviewing built UI for intent, not pixel-perfection",
    ], 8.0),
    (("design ops", "component libraries"), "Delivery & Collaboration", "Design Ops, Component Libraries & Contribution", [
        "Auditing and consolidating existing UI patterns",
        "Component API design and versioning",
        "Contribution models and governance",
        "Measuring adoption and design debt",
    ], 8.0),

    # ── Technical program management ───────────────────────────────────────
    (("dependency mapping", "critical path", "program delivery"), "Program Delivery", "Dependency Mapping & Critical Path Planning", [
        "Building the dependency graph across teams",
        "Critical path, float and honest buffers",
        "Interface contracts and hand-off criteria",
        "Re-planning when dates move",
    ], 10.0),
    (("risk register", "risk management"), "Program Delivery", "Risk Registers, Mitigation & Change Control", [
        "Identifying technical, vendor and people risk",
        "Probability/impact scoring with named owners",
        "Mitigation plans and trigger conditions",
        "Change control that does not slow the team down",
    ], 8.0),
    (("stakeholder", "escalation"), "Influence & Communication", "Stakeholder Alignment & Escalation", [
        "Mapping stakeholders and their incentives",
        "Written updates that create alignment",
        "Escalating early with options, not complaints",
        "Running decisions in reviews and steering forums",
    ], 10.0),
    (("release readiness", "launch coordination"), "Influence & Communication", "Release Readiness & Cross-Team Launch", [
        "Readiness checklists: code, ops, support and legal",
        "Dry runs, rollback and communication plans",
        "Launch-day coordination and update cadence",
        "Post-launch review and follow-through",
    ], 8.0),
)


def _specialist_topics(choices_text: str) -> List[Dict[str, Any]]:
    """Returns the syllabus blocks for whichever specialisations the choices hit."""
    return [
        {"category": category, "topic_name": name, "subtopics": list(subtopics), "estimated_hours": hours}
        for keywords, category, name, subtopics, hours in _SPECIALIST_SYLLABUS
        if any(keyword in choices_text for keyword in keywords)
    ]


# ── Granular Syllabus Topic Mapping By Choice ──────────────────────────────────
def build_topics_from_choices(role_id: str, choices: List[str]) -> List[Dict[str, Any]]:
    """Synthesizes granular syllabus topics from the user's role-specific choices."""
    choices_text = " ".join(choices).lower()
    topics = []

    # 1. First Dimension (Core Language / Specialized Entry)
    if "java" in choices_text and "javascript" not in choices_text:
        topics.append({
            "category": "Core Language & OOP",
            "topic_name": "Java Fundamentals, OOP Architecture & Memory Model",
            "subtopics": [
                "JVM architecture, ClassLoader, JIT execution & Bytecode inspection",
                "OOP Principles (Encapsulation, Polymorphism, Inheritance, Composition)",
                "Java Memory Model: Stack vs Heap, Metaspace, GC (G1/ZGC) lifecycle",
                "Records, Pattern Matching, Sealed Classes & Modern Java syntax"
            ],
            "estimated_hours": 8.0
        })
        topics.append({
            "category": "Core Language & OOP",
            "topic_name": "Collections Framework & Modern Streams API",
            "subtopics": [
                "List, Set, Map internal implementations & collision handling",
                "Generics, Wildcards, Type Erasure & custom Comparators",
                "Stream pipelines, Lambdas, Functional Interfaces & Collectors",
                "Optional<T> best practices and NPE-proof functional code"
            ],
            "estimated_hours": 8.0
        })
        topics.append({
            "category": "Concurrency & Systems",
            "topic_name": "Multithreading, Concurrency & Virtual Threads",
            "subtopics": [
                "Thread lifecycle, Runnable vs Callable, CompletableFuture",
                "volatile keyword, AtomicReference, Synchronized blocks",
                "ExecutorService, ThreadPoolExecutor tuning & ForkJoinPool",
                "Virtual Threads (Project Loom) for high-concurrency throughput"
            ],
            "estimated_hours": 10.0
        })

    elif "python" in choices_text:
        topics.append({
            "category": "Core Language & Idioms",
            "topic_name": "Pythonic Fundamentals, Memory Model & Primitives",
            "subtopics": [
                "List/Dict comprehensions, Set operations, Generators & Memory-efficient Iterators",
                "Decorators (@wraps), Closures, Scope resolution (LEGB rule)",
                "Magic dunder methods (__init__, __str__, __repr__, __call__, __enter__)",
                "Python object memory model, Reference counting & Garbage Collection"
            ],
            "estimated_hours": 8.0
        })
        topics.append({
            "category": "Concurrency & Async",
            "topic_name": "Asyncio & High-Throughput Asynchronous Python",
            "subtopics": [
                "Event Loop fundamentals, Coroutines, async and await primitives",
                "asyncio.gather, Task creation, Semaphores & cancellation handling",
                "Multiprocessing vs Threading vs Asyncio: Navigating the GIL",
                "Type hinting (typing module, TypeVar, Generics, Pydantic validation)"
            ],
            "estimated_hours": 8.0
        })

    elif "go" in choices_text or "golang" in choices_text:
        topics.append({
            "category": "Go Core & Concurrency",
            "topic_name": "Go Idiomatic Core & Concurrency Primitives",
            "subtopics": [
                "Goroutines scheduler (GMP model) vs OS threads",
                "Channels (buffered vs unbuffered), select statements & Channel deadlocks",
                "sync package (sync.Mutex, sync.RWMutex, sync.WaitGroup, sync.Once)",
                "context.Context cancellation, deadlines & distributed request propagation"
            ],
            "estimated_hours": 10.0
        })
        topics.append({
            "category": "Go Microservices",
            "topic_name": "Go Microservices, Networking & gRPC",
            "subtopics": [
                "net/http standard library client/server tuning & Gin Web Framework",
                "Protocol Buffers (protobuf) & gRPC unary/streaming RPC services",
                "Database connection pooling with database/sql and pgx driver",
                "Benchmarking (go test -bench) & Profiling with pprof"
            ],
            "estimated_hours": 10.0
        })

    elif "c++" in choices_text:
        topics.append({
            "category": "C++ Systems Engineering",
            "topic_name": "Modern C++ (C++17/20), Memory & Pointer Mechanics",
            "subtopics": [
                "Stack vs Heap allocation, Raw pointers vs References, Pointer arithmetic",
                "Smart Pointers (std::unique_ptr, std::shared_ptr, std::weak_ptr)",
                "Move semantics, R-value references (&&), std::move & Rule of 5",
                "Templates, Meta-programming, Concepts & Constexpr evaluation"
            ],
            "estimated_hours": 12.0
        })

    elif "typescript" in choices_text or "react" in choices_text or "next" in choices_text:
        topics.append({
            "category": "TypeScript & Modern JS",
            "topic_name": "Modern TypeScript & Advanced Type Systems",
            "subtopics": [
                "Type inference, Union & Intersection types, Type narrowing (guards)",
                "Generics, Keyof, Mapped types, Conditional types & Utility types",
                "ES6+ asynchronous JS: Event loop, Microtasks vs Macrotasks, Promises",
                "tsconfig.json compilation targets, strict mode & module resolution"
            ],
            "estimated_hours": 8.0
        })

    # 2. Second Dimension (Database / Storage / SIEM / BI)
    if "postgres" in choices_text or "sql" in choices_text or "mysql" in choices_text:
        topics.append({
            "category": "Database Engineering",
            "topic_name": "Relational Data Modeling & Advanced SQL Optimization",
            "subtopics": [
                "Relational schema normalization (1NF, 2NF, 3NF, BCNF) & ER diagrams",
                "Complex multi-table JOINs, Self-joins & Cross-joins",
                "Analytical Window Functions (ROW_NUMBER, RANK, DENSE_RANK, NTILE, LAG/LEAD)",
                "Common Table Expressions (CTEs), Recursive queries & Subquery optimizations",
                "B-Tree index architecture, Composite indexes, EXPLAIN ANALYZE query planning",
                "ACID transactions, Row-level locking & Read Committed vs Serializable isolation"
            ],
            "estimated_hours": 10.0
        })

    if "mongo" in choices_text or "document" in choices_text:
        topics.append({
            "category": "NoSQL Database",
            "topic_name": "MongoDB & Document Database Modeling",
            "subtopics": [
                "Document schema design (Embedding vs Referencing patterns)",
                "MongoDB Aggregation Pipeline ($match, $group, $lookup, $unwind)",
                "Compound indexes, Partial indexes & TTL indexes",
                "Replica Sets, Sharding architecture & Write Concerns (w: 'majority')"
            ],
            "estimated_hours": 8.0
        })

    if "redis" in choices_text or "cache" in choices_text:
        topics.append({
            "category": "Caching & Fast Storage",
            "topic_name": "Redis In-Memory Architecture & Distributed Caching",
            "subtopics": [
                "Data structures: Strings, Hashes, Lists, Sets, Sorted Sets (ZSET)",
                "Cache invalidation strategies (Cache-Aside, Write-Through, Write-Behind)",
                "Cache stampede, Cache penetration & TTL eviction policies",
                "Distributed locks (Redlock algorithm) & Redis Pub/Sub"
            ],
            "estimated_hours": 6.0
        })

    if "power bi" in choices_text or "tableau" in choices_text or "looker" in choices_text:
        topics.append({
            "category": "BI & Visual Analytics",
            "topic_name": "Business Intelligence & Executive KPI Modeling",
            "subtopics": [
                "Data modeling: Star schema vs Snowflake schema, Fact & Dimension tables",
                "Advanced DAX / Calculated fields (CALCULATE, FILTER, Time Intelligence)",
                "Interactive drill-downs, Cross-filtering & Custom tooltips",
                "Automated data refresh schedules & Enterprise governance"
            ],
            "estimated_hours": 8.0
        })

    if "splunk" in choices_text or "sentinel" in choices_text or "wireshark" in choices_text:
        topics.append({
            "category": "Security Telemetry & SIEM",
            "topic_name": "SIEM Analytics & Network Traffic Inspection",
            "subtopics": [
                "Splunk Search Processing Language (SPL) & Correlation Searches",
                "Wireshark packet capture analysis: TCP handshake, TLS negotiation, DNS anomalies",
                "Log aggregation, Syslog forwarding & Endpoint Detection and Response (EDR)",
                "Incident triage runbooks & Security Operations Center (SOC) workflows"
            ],
            "estimated_hours": 10.0
        })

    if "qdrant" in choices_text or "pinecone" in choices_text or "vector" in choices_text:
        topics.append({
            "category": "Vector DB & Search",
            "topic_name": "Vector Databases & Hybrid Semantic Search",
            "subtopics": [
                "Dense vs Sparse embeddings, Cosine similarity vs Dot product",
                "HNSW (Hierarchical Navigable Small World) indexing & filtering algorithms",
                "Hybrid search: combining BM25 keyword matching with vector recall",
                "Metadata payload indexing, Collection partitioning & scale"
            ],
            "estimated_hours": 8.0
        })

    if (
        "pytorch" in choices_text
        or "tensorflow" in choices_text
        or "keras" in choices_text
        or "transformer" in choices_text
        or "deep learning" in choices_text
    ):
        topics.append({
            "category": "Deep Learning",
            "topic_name": "Neural Networks & Deep Learning Engineering",
            "subtopics": [
                "Tensors, autograd, broadcasting & GPU acceleration fundamentals",
                "Training loops: loss functions, optimizers (Adam/SGD) & LR schedules",
                "Convolutional (CNN) and Recurrent (RNN/LSTM) architectures",
                "Transfer learning, fine-tuning & regularisation (dropout, weight decay)",
                "Transformer architecture: self-attention, positional encoding & fine-tuning"
            ],
            "estimated_hours": 14.0
        })

    if (
        "mlflow" in choices_text
        or "feature store" in choices_text
        or "model serving" in choices_text
        or "mlops" in choices_text
        or "dvc" in choices_text
    ):
        topics.append({
            "category": "MLOps & Production ML",
            "topic_name": "MLOps: Experiment Tracking, Serving & Monitoring",
            "subtopics": [
                "Experiment tracking, metrics logging & model registry with MLflow",
                "Packaging models into reproducible training & inference pipelines",
                "Serving models via REST (FastAPI) behind Docker & Kubernetes",
                "Monitoring for data drift, model decay & retraining triggers",
                "CI/CD for ML, data versioning (DVC) & feature stores"
            ],
            "estimated_hours": 12.0
        })

    # 3. Third Dimension (Frameworks, Microservices, Agents, Testing, Cloud)
    if "spring" in choices_text:
        topics.append({
            "category": "Enterprise Framework",
            "topic_name": "Spring Boot 3, JPA/Hibernate & Security",
            "subtopics": [
                "Inversion of Control (IoC), Beans lifecycle & ConfigurationProperties",
                "Spring MVC REST controllers, Global exception handling (@ControllerAdvice)",
                "Spring Data JPA, Hibernate entity relationships, Lazy loading & N+1 fix",
                "Spring Security with JWT authentication and stateless authorization filters"
            ],
            "estimated_hours": 12.0
        })

    elif "fastapi" in choices_text:
        topics.append({
            "category": "Web Framework",
            "topic_name": "FastAPI Async Architecture & Pydantic Validation",
            "subtopics": [
                "FastAPI async request lifecycle, Starlette & Pydantic schemas",
                "Dependency injection system (Depends), Middleware & CORS governance",
                "SQLAlchemy 2.0 async ORM, Alembic schema migrations & connection pooling",
                "Background task workers, WebSockets & Swagger/OpenAPI documentation"
            ],
            "estimated_hours": 10.0
        })

    elif "langgraph" in choices_text or "crewai" in choices_text or "mcp" in choices_text or "agent" in choices_text:
        topics.append({
            "category": "Agentic AI Architecture",
            "topic_name": "LLM Function Calling, Multi-Agent Loops & Tool Use",
            "subtopics": [
                "Structured Outputs & JSON Schema constraint enforcement",
                "Tool-calling execution loops (defining schemas, handling multi-step tool calls)",
                "Multi-agent orchestration frameworks (LangGraph, CrewAI, AutoGen)",
                "Model Context Protocol (MCP) clients and servers for agent tooling",
                "Agentic evaluation, error correction loops & guardrails"
            ],
            "estimated_hours": 14.0
        })

    elif "kubernetes" in choices_text or "docker" in choices_text or "terraform" in choices_text:
        topics.append({
            "category": "Infrastructure & Cloud",
            "topic_name": "Docker Containerization, Kubernetes & Terraform IaC",
            "subtopics": [
                "Docker containerization: Multi-stage builds, Distroless images, Layer caching",
                "Kubernetes core primitives: Pods, Deployments, Services (ClusterIP/LoadBalancer)",
                "Terraform Infrastructure as Code: Modules, State management, Remote backends",
                "Prometheus & Grafana monitoring: Metrics, PromQL, Alertmanager rules"
            ],
            "estimated_hours": 12.0
        })

    elif "playwright" in choices_text or "selenium" in choices_text:
        topics.append({
            "category": "Test Automation",
            "topic_name": "End-to-End Test Automation with Playwright / Selenium",
            "subtopics": [
                "Page Object Model (POM) design pattern & modular test architectures",
                "Asynchronous locators, Auto-waiting, Network request interception & Mocking",
                "API automation testing with RestAssured / Playwright APIRequestContext",
                "Parallel test execution, CI/CD reporting & Headless grid runners"
            ],
            "estimated_hours": 10.0
        })

    elif "figma" in choices_text or "prd" in choices_text or "jira" in choices_text:
        topics.append({
            "category": "Product Management",
            "topic_name": "PRD Specs, Prototyping & Agile Execution",
            "subtopics": [
                "Writing structured PRDs (Problem statement, User stories, Acceptance criteria)",
                "Figma wireframing, User flow mapping & Usability testing",
                "Agile backlog grooming, Sprint estimation & MoSCoW feature prioritization",
                "Product Metrics: AARRR Pirate funnels, North Star metric, A/B Testing"
            ],
            "estimated_hours": 10.0
        })

    # Specialisations introduced after the original role set (mobile, games,
    # embedded, design, offensive security, ...). Keyed on choice text exactly
    # like the branches above, but on keywords the original stacks never use.
    topics.extend(_specialist_topics(choices_text))

    # Always ensure DSA & Core Algorithmic Foundation is present for engineering roles.
    # Product, business and program-management tracks are not engineering roles, so
    # they are not asked to grind algorithmic interview problems.
    if not any(track in role_id for track in ("product", "business", "program")):
        topics.append({
            "category": "Computer Science Foundation",
            "topic_name": "Data Structures & Algorithmic Problem Solving",
            "subtopics": [
                "Arrays & Two-pointer / Sliding Window interview patterns",
                "HashMaps & HashSets: Frequency counting & Subarray sum problems",
                "Linked Lists: Fast & slow pointers, Cycle detection, in-place reversal",
                "Stacks & Queues: Monotonic stack patterns, Breadth-First Search (BFS)",
                "Binary Trees & BSTs: Recursive DFS traversals, Lowest Common Ancestor (LCA)",
                "Graphs: Adjacency list representation, Dijkstra shortest path, Topological sort",
                "Dynamic Programming: 1D memoization, 0/1 Knapsack, Longest Common Subsequence"
            ],
            "estimated_hours": 18.0
        })

    return topics


def sync_topics_for_role_stack(
    user_id: int,
    role_id: str,
    choices: List[str],
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Dynamically rebuilds or refreshes the syllabus based strictly on the selected role & stack choices.
    Preserves completion markers for topics that were already checked off!
    """
    conn = get_connection()

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, topic_name, is_completed, completed_at
            FROM tracker_topics WHERE user_id = ? AND role_id = ?;
        """, (user_id, role_id))
        existing_rows = cursor.fetchall()

        if existing_rows and not force_refresh:
            return get_topics_for_role(user_id, role_id)

        # Store completed states to preserve candidate progress
        completed_map = {}
        for r in existing_rows:
            if r["is_completed"]:
                completed_map[r["topic_name"]] = r["completed_at"]

        new_topics = build_topics_from_choices(role_id, choices)

        # Update in SQLite
        with conn:
            conn.execute("""
                DELETE FROM tracker_topics WHERE user_id = ? AND role_id = ?;
            """, (user_id, role_id))

            sort_idx = 1
            for t in new_topics:
                is_done = 1 if t["topic_name"] in completed_map else 0
                done_at = completed_map.get(t["topic_name"])

                conn.execute("""
                    INSERT INTO tracker_topics (
                        user_id, role_id, category, topic_name,
                        subtopics_json, estimated_hours, is_completed, completed_at, sort_order
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    );
                """, (
                    user_id,
                    role_id,
                    t["category"],
                    t["topic_name"],
                    json.dumps(t["subtopics"]),
                    t.get("estimated_hours", 8.0),
                    is_done,
                    done_at,
                    sort_idx
                ))
                sort_idx += 1

        return get_topics_for_role(user_id, role_id)
    finally:
        conn.close()


def get_topics_for_role(user_id: int, role_id: str) -> List[Dict[str, Any]]:
    """Fetches all topics and their completion status for a role."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, category, topic_name, subtopics_json, estimated_hours, is_completed, completed_at
            FROM tracker_topics
            WHERE user_id = ? AND role_id = ?
            ORDER BY sort_order ASC;
        """, (user_id, role_id))
        rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "category": r["category"],
                "topic_name": r["topic_name"],
                "subtopics": json.loads(r["subtopics_json"] or "[]"),
                "estimated_hours": r["estimated_hours"],
                "is_completed": bool(r["is_completed"]),
                "completed_at": r["completed_at"]
            })
        return results
    finally:
        conn.close()


def toggle_topic_status(topic_id: int, user_id: int, is_completed: bool) -> bool:
    """Updates a completion checkbox, scoped to the topic's owner.

    Returns True when a topic owned by ``user_id`` was updated, or False when
    the id does not exist *or* belongs to another user — the caller then
    responds 404 without revealing anything about other users' data.
    """
    conn = get_connection()
    try:
        with conn:
            owned = conn.execute(
                "SELECT 1 FROM tracker_topics WHERE id = ? AND user_id = ?;",
                (topic_id, user_id),
            ).fetchone()
            if not owned:
                return False

            if is_completed:
                conn.execute("""
                    UPDATE tracker_topics
                    SET is_completed = 1, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?;
                """, (topic_id, user_id))
            else:
                conn.execute("""
                    UPDATE tracker_topics
                    SET is_completed = 0, completed_at = NULL
                    WHERE id = ? AND user_id = ?;
                """, (topic_id, user_id))
            return True
    finally:
        conn.close()


def calculate_tracker_metrics(
    topics: List[Dict[str, Any]],
    weekly_hours: float
) -> Dict[str, Any]:
    """Calculates overall progress %, remaining hours, and estimated weeks remaining."""
    total_count = len(topics)
    if total_count == 0:
        return {
            "total_topics": 0,
            "completed_topics": 0,
            "percentage": 0,
            "total_hours": 0.0,
            "completed_hours": 0.0,
            "remaining_hours": 0.0,
            "weeks_remaining": 0.0
        }

    completed_count = sum(1 for t in topics if t["is_completed"])
    total_hours = sum(t["estimated_hours"] for t in topics)
    completed_hours = sum(t["estimated_hours"] for t in topics if t["is_completed"])
    remaining_hours = max(0.0, total_hours - completed_hours)

    pct = int((completed_count / total_count) * 100)
    weekly_hours = max(1.0, weekly_hours)
    weeks_left = round(remaining_hours / weekly_hours, 1)

    return {
        "total_topics": total_count,
        "completed_topics": completed_count,
        "percentage": pct,
        "total_hours": total_hours,
        "completed_hours": completed_hours,
        "remaining_hours": remaining_hours,
        "weeks_remaining": weeks_left
    }
