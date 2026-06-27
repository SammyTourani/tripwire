"""tripwire.targets.sql_fuzzer -- a dependency-free SQL-semantics fuzzer.

Why this file exists (BUILD_PLAN 2.4 / ADR-005)
-----------------------------------------------
For SQL, "empirical-with-guards on the customer's data" is *not* a sufficient
correctness check. The hard query-rewrite bugs live exactly where production data
won't expose them:

  * NULL / three-valued logic   (``WHERE val <> 10`` silently drops NULL rows;
                                  ``WHERE val = NULL`` is *always* empty),
  * duplicate keys / multiset semantics (a rewrite that collapses duplicates),
  * empty groups and empty tables,
  * aggregate edges -- ``COUNT(*)`` vs ``COUNT(col)`` over a NULL column,
    ``SUM``/``AVG`` over an all-NULL group (the answer is NULL, not 0).

So Tripwire's withheld (L3) layer for SQL is a real *SQL-semantics fuzzer*: it
generates adversarial row-sets that deliberately hit those edges, and uses the DB
engine (stdlib ``sqlite3``) as ground truth. A query rewrite that is "equivalent"
on tame canonical rows but diverges on a fuzzed row-set is exactly the planted
hack the layered oracle must catch.

Everything here is stdlib-only (``sqlite3`` + ``random``), deterministic given a
seed, and does no network I/O -- so it runs in CI and in the sandbox (CLAUDE.md
§7). Connections are always opened and closed inside a context manager.

Public surface
--------------
``Column`` / ``Schema``     -- a tiny typed-column schema description.
``connect(schema, rows)``   -- context manager yielding an in-memory DB.
``execute(query, schema, rows)`` -- run a query, return a CANONICALIZED result.
``canonicalize(query, cursor_rows)`` -- the canonical form used for comparison.
``results_equivalent(a, b, schema, rows)`` -- do two queries agree on these rows?
``explain_ok(query, schema)`` -- cheap validity pre-filter via ``EXPLAIN``.
``fuzz_rows(schema, seed, n_sets)`` -- adversarial row-sets hitting the edges.
"""
from __future__ import annotations

import random
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

# --- supported column affinities (kept tiny on purpose) ---------------------
INTEGER = "INTEGER"
TEXT = "TEXT"
REAL = "REAL"
_AFFINITIES = frozenset({INTEGER, TEXT, REAL})


@dataclass(frozen=True)
class Column:
    """A single typed column. ``name`` is a bare identifier; ``affinity`` is one
    of INTEGER / TEXT / REAL (the only types the fuzzer knows how to generate)."""

    name: str
    affinity: str = INTEGER

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name):
            raise ValueError(f"unsafe column name: {self.name!r}")
        if self.affinity not in _AFFINITIES:
            raise ValueError(f"unknown affinity {self.affinity!r}")


@dataclass(frozen=True)
class Schema:
    """A single-table schema. ``table`` defaults to ``t`` -- the convention the
    SQL Target's queries use. Validates identifiers so we can interpolate them
    into DDL safely (rows themselves are always passed as bound parameters)."""

    columns: tuple[Column, ...]
    table: str = "t"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.table):
            raise ValueError(f"unsafe table name: {self.table!r}")
        if not self.columns:
            raise ValueError("Schema needs at least one column")

    @property
    def arity(self) -> int:
        return len(self.columns)

    def create_sql(self) -> str:
        cols = ", ".join(f"{c.name} {c.affinity}" for c in self.columns)
        return f"CREATE TABLE {self.table}({cols})"

    def insert_sql(self) -> str:
        placeholders = ", ".join("?" for _ in self.columns)
        return f"INSERT INTO {self.table} VALUES ({placeholders})"


# ---------------------------------------------------------------------------
# DB construction + execution (sqlite3 is the ground truth)
# ---------------------------------------------------------------------------
@contextmanager
def connect(schema: Schema, rows: Sequence[tuple]) -> Iterator[sqlite3.Connection]:
    """Build a fresh in-memory DB for ``schema`` populated with ``rows`` and yield
    the connection. Always closed on exit (even on error) -- no leaked handles."""
    con = sqlite3.connect(":memory:")
    try:
        con.execute(schema.create_sql())
        # Each row must match the schema arity so ``reference``/``candidate`` see a
        # well-formed table; surface a clear error early if a caller mis-sizes one.
        ins = schema.insert_sql()
        for r in rows:
            if len(r) != schema.arity:
                raise ValueError(
                    f"row {r!r} has arity {len(r)}, schema expects {schema.arity}"
                )
            con.execute(ins, tuple(r))
        con.commit()
        yield con
    finally:
        con.close()


def _has_order_by(query: str) -> bool:
    """True if the (outermost) query pins an order with ORDER BY. Used to decide
    whether we may sort for set/multiset comparison without changing meaning."""
    return re.search(r"\border\s+by\b", query, flags=re.IGNORECASE) is not None


def _cell_key(value) -> tuple[int, float, str]:
    """A total ordering key for a single SQLite cell value.

    Python 3 refuses to compare ``None``/``int``/``str`` against each other, so we
    bucket by a type rank first (NULLs sort first, then numbers, then text, then
    blobs) and only compare within a bucket. This lets us sort heterogeneous,
    NULL-laden result rows deterministically for multiset comparison -- *without*
    reordering anything SQLite itself ordered (we only sort when there is no
    ORDER BY)."""
    if value is None:
        return (0, 0.0, "")
    if isinstance(value, bool):  # bool is an int subclass; treat as number
        return (1, float(value), "")
    if isinstance(value, (int, float)):
        return (1, float(value), "")
    if isinstance(value, bytes):
        return (3, 0.0, value.decode("utf-8", "surrogateescape"))
    return (2, 0.0, str(value))


def _row_key(row: tuple) -> tuple:
    return tuple(_cell_key(c) for c in row)


def canonicalize(query: str, cursor_rows: Sequence[tuple]) -> tuple[tuple, ...]:
    """Turn raw cursor output into a hashable, comparable canonical form.

    * Rows are coerced to plain tuples (sqlite already returns tuples).
    * If the query has **no ORDER BY**, the rows are sorted with a type-aware key
      so that two equivalent result *sets/multisets* compare equal regardless of
      the engine's incidental emission order. Duplicates are **preserved** (so the
      comparison is multiset-correct -- a rewrite that drops or invents duplicate
      rows is caught).
    * If the query **has ORDER BY**, order is meaningful, so we keep it as-is.

    The result is a ``tuple`` of row-``tuple``s, which the structural oracle then
    compares with plain ``==`` -- i.e. exact result-equivalence (ADR-004)."""
    rows = [tuple(r) for r in cursor_rows]
    if not _has_order_by(query):
        rows.sort(key=_row_key)
    return tuple(rows)


def execute(query: str, schema: Schema, rows: Sequence[tuple]) -> tuple[tuple, ...]:
    """Run ``query`` against a fresh DB built from (``schema``, ``rows``) and return
    the canonicalized result. sqlite3 is the ground truth for SQL semantics."""
    with connect(schema, rows) as con:
        cur = con.execute(query)
        fetched = cur.fetchall()
    return canonicalize(query, fetched)


def explain_ok(query: str, schema: Schema) -> bool:
    """Cheap validity pre-filter: ``EXPLAIN`` parses + binds the query against an
    empty table without running it. Returns False if the query is malformed or
    references unknown columns. (A pre-filter only -- real equivalence is decided
    by comparing canonicalized results on actual rows.)"""
    try:
        with connect(schema, []) as con:
            con.execute(f"EXPLAIN {query}").fetchall()
        return True
    except sqlite3.Error:
        return False


def results_equivalent(
    query_a: str, query_b: str, schema: Schema, rows: Sequence[tuple]
) -> bool:
    """Do two queries produce the *same* canonicalized result on the same data?

    This is the atom of SQL result-equivalence used both by the Target's
    candidates (a "rewrite" is correct iff it stays equivalent on every row-set,
    including the adversarial fuzzed ones) and by the tests. Returns False if
    either query raises (a rewrite that errors where the original succeeds is not
    equivalent)."""
    try:
        ra = execute(query_a, schema, rows)
        rb = execute(query_b, schema, rows)
    except sqlite3.Error:
        return False
    return ra == rb


# ---------------------------------------------------------------------------
# The row fuzzer: adversarial row-sets that hit the SQL-semantics edges.
# ---------------------------------------------------------------------------
# Boundary integers SQLite stores natively (64-bit signed). A correct rewrite must
# survive these; an arithmetic-reordering hack might overflow Python-side, etc.
_INT_BOUNDARIES = (0, 1, -1, 2**31 - 1, -(2**31), 2**63 - 1, -(2**63))
_TEXT_POOL = ("a", "b", "c", "", "  pad  ", "naïve", "键", "O'Brien")
_REAL_BOUNDARIES = (0.0, -0.0, 1.5, -2.25, 1e300, -1e-300)


def _value_pool(col: Column) -> tuple:
    """The candidate cell values (including ``None``) for one column's affinity."""
    if col.affinity == INTEGER:
        return (None, *_INT_BOUNDARIES)
    if col.affinity == REAL:
        return (None, *_REAL_BOUNDARIES)
    return (None, *_TEXT_POOL)


def _random_row(rng: random.Random, schema: Schema) -> tuple:
    return tuple(rng.choice(_value_pool(c)) for c in schema.columns)


def _all_null_row(schema: Schema) -> tuple:
    return tuple(None for _ in schema.columns)


def fuzz_rows(
    schema: Schema, seed: int = 0, n_sets: int = 8
) -> list[list[tuple]]:
    """Generate ``n_sets`` adversarial row-sets for ``schema``.

    The set is *designed* to hit every SQL-semantics edge that breaks naive query
    rewrites, deterministically (seeded ``random.Random``):

      1. the **empty table**            (empty groups, ``SUM`` -> NULL, ``COUNT`` 0),
      2. a **single row**               (degenerate aggregates / grouping),
      3. **NULLs in every column**      (3-valued logic; ``= NULL`` always empty),
      4. **duplicate keys**             (multiset semantics; dup-collapsing bugs),
      5. an **all-NULL value column**   (``COUNT(*)`` != ``COUNT(col)``; ``SUM`` NULL),
      6. **boundary integers** + a NULL (overflow / sentinel-value bugs),
      7+. **random** rows drawn from the NULL-rich pools (broad coverage).

    Returns a list of row-sets (each a ``list`` of value-tuples), so callers can
    wrap each as a one-arg tuple ``(rows,)`` for the Target's ``withheld_args``.
    The first six structured sets are always present (when ``n_sets`` allows);
    any remainder is filled with random sets."""
    if n_sets < 1:
        raise ValueError("n_sets must be >= 1")
    rng = random.Random(seed)
    cols = schema.columns
    first = cols[0]
    # Pick a TEXT column to use as a duplicated "group key" if one exists, else the
    # first column -- duplicates on it exercise GROUP BY / DISTINCT collapsing.
    grp = next((c for c in cols if c.affinity == TEXT), first)

    structured: list[list[tuple]] = []

    # 1. empty table
    structured.append([])

    # 2. single row (one non-NULL value per column where we can)
    single = tuple(
        (None if rng.random() < 0.2 else _non_null_sample(rng, c)) for c in cols
    )
    structured.append([single])

    # 3. NULLs appearing in every column across a few rows (so each column has at
    #    least one NULL somewhere -- exercises 3VL on whichever column a rewrite
    #    filters on).
    null_rows = [_all_null_row(schema)]
    for i in range(schema.arity):
        r = list(_non_null_row(rng, schema))
        r[i] = None  # force a NULL into column i
        null_rows.append(tuple(r))
    structured.append(null_rows)

    # 4. duplicate group keys: several rows sharing the same grp value but differing
    #    elsewhere (multiset / DISTINCT-collapsing trap).
    dup_key = _non_null_sample(rng, grp)
    dup_rows = []
    for k in range(4):
        r = list(_non_null_row(rng, schema))
        _set_col(r, schema, grp.name, dup_key)
        # vary another column so the *rows* are distinct even though the key repeats
        if schema.arity > 1:
            other = cols[(cols.index(grp) + 1) % schema.arity]
            _set_col(r, schema, other.name, _int_or_text(other, k))
        dup_rows.append(tuple(r))
    # add an exact duplicate row too (true multiset duplicate)
    dup_rows.append(dup_rows[0])
    structured.append(dup_rows)

    # 5. an all-NULL *value* column: a group whose aggregated column is entirely
    #    NULL. This is the COUNT(*)-vs-COUNT(col) / SUM-is-NULL trap. We pick the
    #    last column as the "value" column (the SQL Target aggregates `val`, last).
    value_col = cols[-1]
    key_a = _int_or_text(grp, 100)
    key_b = _int_or_text(grp, 200)
    allnull_rows = []
    for _ in range(2):  # group A: value present
        r = list(_non_null_row(rng, schema))
        _set_col(r, schema, grp.name, key_a)
        allnull_rows.append(tuple(r))
    for _ in range(3):  # group B: value column ALL NULL
        r = list(_non_null_row(rng, schema))
        _set_col(r, schema, grp.name, key_b)
        _set_col(r, schema, value_col.name, None)
        allnull_rows.append(tuple(r))
    structured.append(allnull_rows)

    # 6. boundary integers (+ a NULL) in any INTEGER/REAL columns.
    boundary_rows = []
    for b in (_INT_BOUNDARIES + (None,)):
        r = []
        for c in cols:
            if c.affinity in (INTEGER, REAL):
                r.append(b if (b is None or c.affinity == INTEGER) else float(b))
            else:
                r.append(_non_null_sample(rng, c))
        boundary_rows.append(tuple(r))
    structured.append(boundary_rows)

    # Assemble: keep the structured edge sets first, then top up with random sets.
    out = structured[:n_sets]
    while len(out) < n_sets:
        size = rng.randint(0, 6)
        out.append([_random_row(rng, schema) for _ in range(size)])
    return out


# --- small row-construction helpers (kept private) -------------------------
def _non_null_sample(rng: random.Random, col: Column):
    pool = [v for v in _value_pool(col) if v is not None]
    return rng.choice(pool)


def _non_null_row(rng: random.Random, schema: Schema) -> tuple:
    return tuple(_non_null_sample(rng, c) for c in schema.columns)


def _set_col(row: list, schema: Schema, name: str, value) -> None:
    idx = next(i for i, c in enumerate(schema.columns) if c.name == name)
    row[idx] = value


def _int_or_text(col: Column, n: int):
    """A deterministic distinct value of the right type for column ``col``."""
    if col.affinity == TEXT:
        return f"g{n}"
    if col.affinity == REAL:
        return float(n)
    return n
