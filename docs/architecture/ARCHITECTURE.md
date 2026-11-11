# DATUMOR — Technical Architecture
Version: 1.0.0
Status: LOCKED

## 1. Architecture Pattern
Modular monolith with independent asynchronous workers.

## 2. Processing Flow
User Interface / API
  -> Authentication and Authorization
  -> Project and Source Management
  -> Ingestion
  -> Format Detection
  -> Extraction
  -> Understanding
  -> DUKR Canonical Representation
  -> DQIS Quality Intelligence
  -> Target Transformation
  -> Tokenization / Optional Embeddings
  -> Independent Validation
  -> Dataset Export
  -> Versioning and Lineage

## 3. Application Layers

INPUT:
Accept files, repositories and external sources.

INGESTION:
Validate, fingerprint and register original sources.

EXTRACTION:
Extract structured content using specialized adapters.

UNDERSTANDING:
Identify meaning, entities and relationships.

CANONICAL DATA:
Store extracted knowledge using DUKR.

QUALITY:
Measure accuracy, completeness, consistency,
relevance, duplication and provenance.

TRANSFORMATION:
Generate target-specific AI datasets.

OPTIMIZATION:
Handle tokenization, chunking and optional embeddings.

VALIDATION:
Independently verify schemas, evidence and lineage.

DELIVERY:
Provide reports, APIs, downloads and dataset versions.

## 4. Core Architecture Rules

1. Original source files must remain immutable.
2. Every processed record must support provenance.
3. Engine modules communicate through documented contracts.
4. Business logic must not depend on the frontend.
5. AI providers must be replaceable through adapters.
6. AI-generated output requires independent validation.
7. Embeddings are optional.
8. Dataset versions must be immutable.
9. Uploaded code must never execute during extraction.
10. All processing jobs must support failure reporting.

## 5. Technology Stack

Backend: Python 3.12+, FastAPI
Frontend: React, TypeScript, Vite, Tailwind CSS
Database: PostgreSQL
ORM: SQLAlchemy
Migrations: Alembic
Queue: Redis + Celery
Object Storage: MinIO
Documents: Docling, PyMuPDF
Code Parsing: Tree-sitter
Image: OpenCV, PaddleOCR
Audio: faster-whisper
Video: FFmpeg, OpenCV
AI: Hugging Face, Ollama
Tokenization: Hugging Face Tokenizers
Embeddings: Sentence Transformers
Vector Database: Qdrant
Data: Polars, PyArrow
Testing: Pytest, HTTPX
Deployment: Docker, Docker Compose

## 6. Data Ownership

PostgreSQL:
Projects, users, sources, jobs, metadata,
quality reports, datasets and lineage.

MinIO:
Original files, intermediate artifacts and exports.

Redis:
Temporary queue and cache data.

Qdrant:
Optional embedding indexes.

## 7. Execution Model

FastAPI handles requests.
Celery workers execute asynchronous processing.
The orchestrator coordinates engine execution.
PostgreSQL tracks persistent state.
MinIO stores binary artifacts.
Redis coordinates background jobs.

## 8. Security Boundaries

Authentication and project-level authorization.
File signature and MIME validation.
Upload and decompression limits.
Isolated processing workspaces.
No arbitrary uploaded-code execution.
Audit logging and controlled deletion.

## 9. Deployment Model

Development: Windows + Docker Desktop.
Production: Linux + Docker.
Architecture: Single deployable application
with independently scalable worker processes.

## 10. Change Control

Architecture changes require a demonstrated
technical limitation, documented impact and
explicit approval.

No speculative redesign.
