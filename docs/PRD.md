# DATUMOR — Product Requirements Document

## 1. Product
Universal Multimodal Data Intelligence & Preparation Engine.

## 2. Objective
Transform raw information into structured, traceable,
quality-verified datasets for different AI applications.

## 3. Target Customers
- AI developers
- AI training companies
- Coding agent developers
- Research organizations
- RAG application developers
- Video and image AI developers

## 4. Input Sources
- PDF, DOCX, TXT, Markdown, HTML
- JSON, JSONL, CSV, XML
- Python, JavaScript, TypeScript and other code
- GitHub repositories
- Images and diagrams
- Audio and video
- External APIs

## 5. Core Capabilities
- Universal ingestion
- Intelligent extraction
- Multimodal understanding
- Context and relationship detection
- Canonical representation (DUKR)
- Quality intelligence (DQIS)
- Task-specific transformation
- Tokenization and chunking
- Optional embeddings
- Independent validation
- Dataset export and versioning

## 6. Output Formats
JSONL, JSON, Parquet and vector indexes.

## 7. Product Interfaces
- REST API
- Developer integration
- Customer SaaS dashboard

## 8. Architecture
Modular monolith with independent background workers.

## 9. Fixed Technology Stack
Python 3.12+
FastAPI
React + TypeScript + Vite
Tailwind CSS
PostgreSQL
SQLAlchemy
Alembic
Redis
Celery
MinIO
Docling
PyMuPDF
Tree-sitter
OpenCV
PaddleOCR
faster-whisper
FFmpeg
Hugging Face
Ollama
Hugging Face Tokenizers
Sentence Transformers
Qdrant
Polars
PyArrow
Pytest
HTTPX
Docker

## 10. Security
- Authentication and authorization
- File validation
- Isolated processing
- Resource limits
- Audit logging
- Data deletion
- Customer data isolation

## 11. Commercial Requirements
- Customer registration
- Project management
- Processing usage metering
- Subscription billing
- Dataset downloads
- API access
- Production deployment

## 12. Quality Principles
- Preserve original sources.
- Never silently invent information.
- Maintain source traceability.
- Use measurable quality metrics.
- Independently validate AI-generated outputs.

## 13. Development Completion
M0 through M10 must pass their defined
implementation and real-world acceptance tests.

Final release requires successful production
deployment and customer acceptance.

STATUS: BASELINE REQUIREMENTS
VERSION: 1.0.0
