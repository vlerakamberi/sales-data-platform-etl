# Data ingestion architecture

## Purpose

Northstar Retail Group requires a controlled boundary between external source
files and later ETL processing. External layouts have source-specific meaning
and may evolve independently, while downstream processing needs deterministic,
validated inputs with trustworthy provenance. Milestone 3 establishes that
boundary without treating an external file layout as the canonical data model.

## Relationship to Milestone 1

Milestone 3 reuses the centralized paths, validated configuration, logging,
application bootstrap, package boundaries, and testing foundations established
in Milestone 1. It does not create parallel configuration, path, logging, or
bootstrap architectures.

## Relationship to Milestone 2

The nine-entity PostgreSQL schema remains the authoritative canonical
persistence contract. External source schemas do not automatically equal or
alias PostgreSQL schemas. Ingestion provenance is metadata at the ingestion
boundary and does not require modification of the nine approved business
tables. Canonical persistence into PostgreSQL remains downstream of Milestone
3.

## Architectural boundary

```text
External source
→ Versioned source contract
→ Discovery / parsing / source-conformance validation
→ Provenance-aware validated ingestion
→ Future canonical transformation
→ Future persistence
```

Milestone 3 ends after provenance-aware validated ingestion. Canonical
transformation, relational resolution, and persistence belong to later work.

## Source-contract model

Every supported source type has an explicit logical source-contract identifier
and immutable version. Incompatible evolution requires a new version. An
unknown contract or version fails explicitly rather than being interpreted
heuristically.

External field layouts and semantics remain source-specific. Different
contracts converge only at the common ingestion boundary; they do not need to
share an external schema or mirror the persistence schema.

## Approved initial contracts

The approved initial contracts are:

- `northstar.product_catalog / v1`, demonstrating a catalog-oriented snapshot
  with product and classification semantics;
- `northstar.ecommerce_sales / v1`, demonstrating sales events whose source
  semantics do not require a physical store;
- `northstar.retail_sales / v1`, demonstrating store-associated sales events.

These three contracts provide sufficient architectural diversity across
catalog data and two materially different sales channels. They demonstrate the
common boundary without attempting to implement every future source type.

## Replay semantics

Replay is deterministic ingestion, not exactly-once persistence. The same
supported contract and the same immutable source content produce an equivalent
validated source interpretation and stable source identity. A replay is still
a distinct execution and may have a different run or correlation identity.

## Source identity

Source identity is conceptually based on:

- source-contract identifier;
- source-contract version;
- normalized relative or otherwise approved source identifier;
- source-content SHA-256.

This basis defines identity semantics without freezing an internal
serialization or class representation.

## Provenance

Minimum provenance consists of:

- source contract ID;
- source contract version;
- normalized relative or approved source identifier;
- source-content SHA-256;
- row or source position where applicable;
- run or correlation identifier.

This is ingestion metadata. It does not automatically add columns or relations
to the nine Milestone 2 business tables.

## File-level atomicity

One contract-breaking error invalidates the complete file-level ingestion
batch. There is no partial-row success. Milestone 3 provides no quarantine or
dead-letter handling. File-level atomicity does not imply exactly-once
persistence or a PostgreSQL transaction.

## Deterministic discovery

Discovery operates within an approved configured source root, considers only
supported source files, and produces deterministic ordering. Initial-contract
discovery is controlled and non-recursive. Paths cannot escape the approved
root, unsafe symlink traversal is not permitted, and behavior must not depend
on a developer workstation or current working directory.

## Deterministic CSV contract

Initial CSV contracts use UTF-8 as the authoritative default, comma delimiters,
and standard CSV quoting. Each contract defines required headers. Duplicate
headers, missing required headers, and unexpected headers are rejected unless
a contract explicitly permits an extension.

Blank-line behavior is deterministic. A missing field and an explicitly empty
value remain distinct. Malformed row widths are rejected. Number, date, and
time interpretation is locale-independent, and source timestamps representing
instants are timezone-aware where required by the source contract.

## Validation versus transformation

Milestone 3 validation may perform:

- structural checks;
- required-field checks;
- primitive parsing;
- primitive type validation;
- source-local nullability and range or value validation.

It must not perform:

- cross-entity relational resolution;
- PostgreSQL lookups;
- surrogate-key assignment;
- canonical business enrichment;
- canonical persistence mapping;
- business metrics or aggregations.

## Failure taxonomy

Controlled ingestion failures are categorized as:

- discovery failure;
- source-contract failure;
- parse failure;
- record-validation failure.

Unexpected system and programming failures remain distinct from these
controlled source-processing outcomes.

## Observability

Ingestion uses the centralized Milestone 1 logging foundation. Observability
provides useful source, contract, run, provenance, and error context while
avoiding unnecessary disclosure. Raw full records are not logged by default,
and no parallel logging subsystem is introduced.

## Test boundary

Milestone 3 ingestion is independently testable without PostgreSQL. Local
synthetic-file integration tests exercise the ingestion boundary. Existing
Milestone 2 PostgreSQL tests remain regression evidence, but core ingestion
testing introduces no PostgreSQL dependency.

## Explicit out of scope

Milestone 3 does not implement:

- canonical transformation;
- PostgreSQL loading;
- orchestration or scheduling;
- quarantine or dead-letter architecture;
- exactly-once persistence;
- Azure Blob Storage or ADLS;
- Azure Data Factory;
- Databricks;
- Spark;
- Snowflake;
- Kafka or streaming;
- API ingestion;
- change data capture;
- warehouse modeling;
- Power BI;
- later-repository functionality.
