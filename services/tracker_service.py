"""
Study Schedule & Granular Topic Tracker Service for CareerCompass.
Handles hours planning (weekdays vs weekends), role-specific dynamic stack selectors,
syllabus generation, subtopic markers, and progress tracking.
"""

import json
import os
from typing import List, Dict, Any, Optional
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
    user_id: Optional[int],
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
    uid = user_id or 0
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
                uid,
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


def get_study_schedule(user_id: Optional[int], role_id: str) -> Dict[str, Any]:
    """Retrieves current study schedule for user & role, or sensible defaults."""
    conn = get_connection()
    uid = user_id or 0
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT weekday_hours, weekend_hours, weekly_total_hours, target_languages_json
            FROM study_schedules WHERE user_id = ? AND role_id = ?;
        """, (uid, role_id))
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

    # Always ensure DSA & Core Algorithmic Foundation is present for engineering roles
    if "product" not in role_id and "business" not in role_id:
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
    user_id: Optional[int],
    role_id: str,
    choices: List[str],
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Dynamically rebuilds or refreshes the syllabus based strictly on the selected role & stack choices.
    Preserves completion markers for topics that were already checked off!
    """
    conn = get_connection()
    uid = user_id or 0

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, topic_name, is_completed, completed_at
            FROM tracker_topics WHERE user_id = ? AND role_id = ?;
        """, (uid, role_id))
        existing_rows = cursor.fetchall()

        if existing_rows and not force_refresh:
            return get_topics_for_role(uid, role_id)

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
            """, (uid, role_id))

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
                    uid,
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

        return get_topics_for_role(uid, role_id)
    finally:
        conn.close()


def get_topics_for_role(user_id: Optional[int], role_id: str) -> List[Dict[str, Any]]:
    """Fetches all topics and their completion status for a role."""
    conn = get_connection()
    uid = user_id or 0
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, category, topic_name, subtopics_json, estimated_hours, is_completed, completed_at
            FROM tracker_topics
            WHERE user_id = ? AND role_id = ?
            ORDER BY sort_order ASC;
        """, (uid, role_id))
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


def toggle_topic_status(topic_id: int, is_completed: bool):
    """Updates completion checkbox in SQLite database."""
    conn = get_connection()
    try:
        with conn:
            if is_completed:
                conn.execute("""
                    UPDATE tracker_topics
                    SET is_completed = 1, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                """, (topic_id,))
            else:
                conn.execute("""
                    UPDATE tracker_topics
                    SET is_completed = 0, completed_at = NULL
                    WHERE id = ?;
                """, (topic_id,))
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
