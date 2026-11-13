# DATUMOR Vector Indexing

## Purpose
Optional Qdrant-backed storage and retrieval for validated embedding records.

## Configuration
Default Qdrant endpoint: `http://127.0.0.1:6333`.

Qdrant is optional. The optimization pipeline can generate embeddings without
requiring vector indexing.

## Collection isolation
Collections are deterministically identified by provider, model and vector
dimensions. Different embedding models or dimensions use separate collections.
Vectors use cosine distance.

## Indexing
`QdrantVectorIndex.index_embeddings(records)` accepts records produced by
the M7.3 embedding engine. It validates provider identity, dimensions,
vectors, chunk IDs and source metadata before writing.

Point IDs are deterministic UUID5 values derived from collection identity
and chunk ID. Re-indexing the same chunk in the same collection updates its
existing point rather than creating a duplicate.

Upserts use `wait=True`. Embeddings are not regenerated and input records
are not modified.

## Retrieval
`search(vector, provider, model, limit, source_id)` performs similarity
search and returns ranked chunks with source identity, checksums, tokenizer
fingerprint and provider metadata.

The optional source ID filter restricts results to a source.

## Integrity and limitations
- No automatic cross-model vector conversion.
- No automatic embedding generation during indexing.
- No deletion of source records when a vector collection is deleted.
- Qdrant payload stores chunk text only when supplied in the embedding record.
- Qdrant indexing is independent of the canonical DUKR records.
- Production authentication, backup policy and network exposure must be
  configured before public deployment.
