# Data transformation architecture

## Purpose and boundary

Milestone 4 transforms validated, source-oriented Milestone 3 records into
deterministic canonical Northstar business representations. The transformation
layer is implemented and locally validated but not yet formally closed. This
document reflects that implementation while preserving the approved
architecture and its persistence boundary.

The logical boundary is:

```text
ValidatedBatch
→ exact source-contract dispatch
→ source-specific interpretation
→ canonical normalization
→ business-key / relationship evaluation
→ transformation business rules
→ deterministic record-level derivation
→ curated-readiness evaluation
→ explicit transformation outcome
→ TransformationBatchResult
```

Milestone 4 starts at the Milestone 3 validated ingestion boundary. It must not
reopen raw source files or duplicate Milestone 3 parsing or source-contract
validation. The centralized foundations and frozen contracts from Milestones
1–3 remain unchanged.

Local integration validation also composes a physical synthetic source through
`ingest_source_file()`, `ValidatedBatch`, `transform_batch()`, explicit ordered
outcomes, and `TransformationBatchResult`. This validates the boundary without
making transformation depend on the filesystem or PostgreSQL.

## Supported v1 contracts

The supported source contract versions are exactly:

- `northstar.product_catalog/v1`
- `northstar.ecommerce_sales/v1`
- `northstar.retail_sales/v1`

## Representation boundaries

The three representations are deliberately distinct:

```text
source representation
≠ canonical Northstar business representation
≠ PostgreSQL persistence representation
```

Canonical records express governed Northstar business meaning. They do not
contain PostgreSQL surrogate identities and are not PostgreSQL table schemas.

## Canonical concepts

The approved small shared canonical business model has two conceptual families:
`CanonicalProduct` and `CanonicalSalesLine`.

### CanonicalProduct

`CanonicalProduct` conceptually carries:

- `sku`;
- `product_name`;
- `category_code`;
- `list_price`;
- `unit_cost`;
- `product_currency_code`;
- provenance;
- transformation ruleset identity.

It has no `product_id` or `product_category_id`.

### CanonicalSalesLine

`CanonicalSalesLine` conceptually carries:

- `sales_channel_code`;
- `source_transaction_number`;
- `transaction_timestamp`;
- optional `store_code`;
- explicit customer-reference state;
- `product_sku`;
- `quantity`;
- `unit_price`;
- `currency_code`;
- `line_amount`;
- source-local context where justified;
- provenance;
- transformation ruleset identity.

These concepts describe a canonical business record, not a PostgreSQL table
schema.

## Identity distinctions

The architecture keeps these identities separate:

- source identity identifies immutable source content under a source contract;
- ingestion run identity identifies a particular processing execution;
- source business identity is an identifier or reference expressed by the
  source;
- canonical business identity or reference is a governed Northstar business key
  or relationship;
- PostgreSQL surrogate identity belongs to persistence.

PostgreSQL surrogate identity remains outside the canonical transformation
core. Source identity and ingestion run identity also remain distinct.

## Exact mapping architecture

Dispatch and mapping are explicit for each exact source contract and version.
There is no reflection-based mapping, implicit field-name matching, PostgreSQL
column inference, fuzzy matching, dynamic plugin discovery, or fallback to
another source-contract version.

## Channel mapping

The exact channel mappings are:

```text
northstar.ecommerce_sales/v1 → ECOMMERCE
northstar.retail_sales/v1    → RETAIL
```

## Customer limitation

`customer_email` is not an authoritative Northstar customer identity. Its
presence may indicate an unresolved source customer reference. Its absence is
valid where the business relationship is optional. Transformation must never
fabricate `customer_id`.

## Store limitation

For retail records, `store_code` is an authoritative business-key reference
only. The current governed source does not authorize transformation to
fabricate `store_id`, `store_name`, or `country_code`.

## Category limitation

For product-catalog records, `category_code` may be preserved as a business-key
reference. Complete product-category master data cannot be fabricated where
authoritative category attributes are unavailable.

## Unsupported entities

The current governed v1 sources provide no approved payment or return events.
No canonical payment or return records are generated.

## Normalization and business rules

Transformation uses explicit deterministic behavior:

- Business identifiers may undergo only approved normalization.
- Surrounding whitespace may be normalized where required.
- Case semantics remain preserved.
- Timestamps normalize to UTC while preserving the same instant.
- Monetary calculations use exact `Decimal` semantics.
- Fractional sales quantity must not be silently rounded where the canonical
  Repository 1 item quantity requires integral representation.
- Transaction currency is preserved; no foreign-exchange conversion occurs.
- No generalized rules framework is introduced.

## Derived value

Exactly one record-level derivation is approved:

```text
line_amount = quantity × unit_price
```

The calculation uses exact decimal semantics. It does not derive or imply order
totals, discounts, taxes, margin, profit, KPIs, aggregates, or BI metrics.
Order-level aggregation is not approved because transaction completeness across
source artifacts has not been governed.

## Transformation outcomes

Every attempted validated record receives exactly one explicit outcome from:

- `SUCCESS`
- `UNTRANSFORMABLE`
- `AMBIGUOUS`
- `BUSINESS_RULE_REJECTED`

There is no silent record loss. This outcome model does not design quarantine,
retry, dead-letter, or generalized Data Quality Framework infrastructure.
Batch results derive record, success, and failure counts from ordered outcomes;
successful canonical records remain available in source order. Fractional
quantity is locally validated as a governed `BUSINESS_RULE_REJECTED` outcome.

## Provenance

The existing Milestone 3 `RecordProvenance` remains associated with
transformation results. Transformation adds an explicit transformation
ruleset/version identity. Source identity remains distinct from processing and
run identity, and this architecture makes no exactly-once processing claim.

## Transformation rule versioning

Transformation semantics have an explicit version independent of the
source-contract version. Material changes to business or canonical semantics
require a new transformation version.

A new version is not required merely for semantics-preserving refactoring,
performance improvement, logging-only changes, or test-only changes. This
versioning decision introduces neither a remote rules registry nor a
generalized version platform.

## Curated-ready boundary

Within this logical lifecycle, `curated-ready` means
`transformation-complete`. It does not mean persisted, Data Quality
Framework-certified, orchestrated, or production-ready. The term describes a
logical readiness state and does not imply a new physical storage technology.

## PostgreSQL persistence exclusion

The transformation boundary:

- does not perform PostgreSQL loading;
- does not look up database surrogate IDs;
- does not assign surrogate IDs;
- does not map directly into database tables;
- does not redesign the Milestone 2 schema;
- does not introduce ORM schema ownership.

Persistence ownership remains separately governed.

## Local validation status

Local unit and integration coverage validates all three governed `v1`
contracts, exact source dispatch, canonical products and sales lines, UTC
normalization, exact `Decimal` line amounts, provenance and transformation
ruleset continuity, deterministic replay, and run-identity separation. It also
validates that customer email is not promoted to canonical identity or exposed
by transformation lifecycle logs, that retail `store_code` remains a business
key, and that `terminal_id` remains source-local context.

The validated boundary ends at `TransformationBatchResult`. It performs no
aggregation, surrogate-identity resolution, database access, SQL execution, or
persistence. This local validation is not a claim of formal Milestone 4 closure,
Repository 1 completion, Data Quality Framework implementation, or orchestration.

## Explicit non-goals

The Milestone 4 architecture does not introduce:

- duplication of Milestone 3 parsing or source validation;
- a generalized Data Quality Framework;
- a profiling platform;
- quality scoring;
- a generic rules engine;
- scheduling;
- orchestration;
- retry coordination;
- production monitoring;
- Azure;
- Azure Data Factory (ADF);
- Spark;
- Databricks;
- Snowflake;
- dimensional warehouse modeling;
- a BI semantic layer;
- machine-learning matching;
- streaming;
- PostgreSQL loading.
