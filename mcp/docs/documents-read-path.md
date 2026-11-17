# Documents knowledge base — read-path specification

Normative description of the question-answering read path of a compiled document knowledge
base (KB). The reference implementation is Python; this document is the contract a Rust
rewrite must reproduce bit-for-bit where observable (citation order, scores, tensions,
rendered text). Python quirks are kept, not fixed: see **Suspected defects**.

Path aliases used in citations:

| alias | file |
|---|---|
| `ask.py` | `core/src/documents/ask.py` |
| `text.py` | `core/src/documents/text.py` |
| `store.py` | `core/src/documents/store.py` |
| `model.py` | `core/src/documents/model.py` |
| `verify.py` | `core/src/documents/verify.py` |
| `vector.py` | `core/src/documents/vector.py` |
| `cli.py` | `core/src/cli/documents.py` |
| `sparql.py` | `core/src/sparql.py` |
| `cli_query.py` | `core/src/cli/query.py` |

Entry points:

| operation | signature | location |
|---|---|---|
| index build | `Corpus(claims, documents, verdicts, include_unverified=False)` | `ask.py:189` |
| lexical + fused search | `Corpus.search(question, limit=12, semantic_ranking=None) -> list[Citation]` | `ask.py:277` |
| answer | `ask(question, corpus, limit=12) -> Answer` | `ask.py:434` |
| tensions | `find_tensions(citations) -> list[Tension]` | `ask.py:391` |
| text rendering | `render_text(answer) -> str` | `ask.py:442` |
| CLI | `ontocore ask QUESTION [-k KB] [-n LIMIT] [--json] [--include-unverified] [--semantic/--no-semantic]` | `cli.py:597-630` |

Pipeline order, mandatory: load `claims.jsonl`, `documents.jsonl`, `verifier.jsonl`; filter
claims by verdict; build the index; tokenize the question; score every claim; keep
`score > 0`; sort; optionally fuse with a semantic ranking; take a window of
`max(limit*4, limit)`; deduplicate by normalized statement; stop at `limit`; build citations;
compute tensions from those citations only; render.

The read path never opens `spans.jsonl`, `rejected.jsonl`, `graph.ttl`, `evidence.csv`,
`view.html`, or `text/<doc_id>.txt`. Quotes come from `claims.jsonl`; a citation carries no
document body text.

---

## 1. File formats

`core/src/documents/store.py` owns every on-disk name (`store.py:36-46`) and every reader.

| file | reader | missing file | used by the `ask` path |
|---|---|---|---|
| `manifest.json` | `KnowledgeBase.manifest()` `store.py:402-404` | `{}` | only `languages` (semantic gate, `cli.py:579`) |
| `documents.jsonl` | `KnowledgeBase.documents()` `store.py:406-407` | `[]` | `doc_id`, `title`, `url` |
| `claims.jsonl` | `KnowledgeBase.claims()` `store.py:412-413` | `[]` (CLI refuses earlier, `cli.py:610-612`) | all searchable text and every citation field |
| `verifier.jsonl` | `KnowledgeBase.verifier()` `store.py:415-416` | `[]` | `claim_id`, `verdict` |
| `vectors.jsonl` | `KnowledgeBase.vectors()` `store.py:421-435` | `{}` | optional semantic ranking |
| `text/<doc_id>.txt` | `KnowledgeBase.text()` `store.py:449-451` | `""` | **no**; `text()`/`texts()` have no caller in the product code (ingest passes `extract()` output straight to `verify_all`, `cli.py:253`, `cli.py:395`) |
| `spans.jsonl` | `store.py:409-410` | `[]` | no |
| `rejected.jsonl` | `store.py:418-419` | `[]` | no |
| `graph.ttl`, `evidence.csv`, `view.html` | not read by `KnowledgeBase` | — | no |

### 1.1 JSONL and JSON readers (exact semantics)

`read_jsonl(path)` (`store.py:151-158`):

1. if the path does not exist, return `[]` — no error, no warning;
2. read the whole file as UTF-8, `errors` not overridden, so invalid bytes raise;
3. `splitlines()` — Python splits on `\n`, `\r`, `\r\n` **and** on U+000B, U+000C, U+001C–U+001E, U+0085, U+2028, U+2029;
4. drop lines where `line.strip()` is empty (Unicode whitespace strip);
5. `json.loads(line)` for each remaining line. A malformed line raises; nothing is skipped or logged;
6. a line whose JSON value is `null` becomes `None` in the list (the readers below then fail on it).

`read_json(path)` (`store.py:165-166`) has no existence guard and no error handling; only
`manifest()` wraps it with `path.exists()`.

Files are written as UTF-8 without BOM (`store.py:145-148`, `store.py:161-162`). A BOM would
make the first `json.loads` fail.

### 1.2 `manifest.json`

Object. The read path uses exactly one key:

| key | type | default | use |
|---|---|---|---|
| `languages` | object `doc_id -> "it" \| "en"` | absent → `{}` | `set((kb.manifest().get("languages") or {}).values())` decides whether the embedding model may be used (`cli.py:579`, `cli.py:585`) |

Everything else in the file is metadata for humans: `name`, `description`, `created`, `model`,
`base_url`, `prompt_hash`, `chunk_size`, `overlap`, `concurrency`, `max_tokens`, `documents`,
`pages`, `claims`, `verifier`, `truncated_calls`, `truncated_enrichment`, `retried_chunks`,
`localised_statements`, `cost_usd`, `tokens`, `replayed_cost_usd`, `replayed_tokens`,
`licences`, `elapsed_s` (`cli.py:400-444`).

Real excerpt (`kb/manifest.json` of the pilot knowledge base, values trimmed):

```json
{
 "name": "corpus",
 "created": "2026-11-16T19:20:18Z",
 "model": "deepseek-v4.1-flash",
 "documents": 279,
 "claims": 9295,
 "verifier": {"ok": 9104, "weak": 108, "no": 83},
 "languages": {"dsid_020bac2fb6ac4de28d5afb63e39a0c10": "en", "...": "en"}
}
```

### 1.3 `documents.jsonl`

One JSON object per line; the read path indexes by `doc_id` (`ask.py:210`) and reads three keys
in `_citation` (`ask.py:348`, `ask.py:353`).

| field | type | required | default when absent | use |
|---|---|---|---|---|
| `doc_id` | string | yes | — (`KeyError` at `ask.py:210`) | map key, `Citation.doc_id` |
| `title` | string | no | `None` via `.get`; then falls back to `claim.context.source`, then `claim.doc_id` (`ask.py:348`) | `Citation.title` display |
| `url` | string | no | `""` (`.get("url", "")`, `ask.py:353`) | `Citation.url` fallback |
| `path`, `kind`, `licence`, `version`, `jurisdiction`, `doc_type`, `page_range`, `sha256`, `notes`, `context`, `claims`, `pages` | any | no | ignored | not read |

Duplicate `doc_id`: the dictionary comprehension keeps the **last** row (`ask.py:210`).

Real row (truncated):

```json
{"doc_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10", "path": "dsid_020bac2fb6ac4de28d5afb63e39a0c10.txt", "title": "dsid_020bac2fb6ac4de28d5afb63e39a0c10", "kind": "text", "url": "https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench", "licence": "MIT", "version": "", "jurisdiction": "", "doc_type": "document", "page_range": null, "sha256": "89d900e4…", "notes": "onyx-dot-app/EnterpriseRAG-Bench document dsid_020…", "context": {"source": "dsid_020…", "doc_type": "document"}, "claims": 30, "pages": 1}
```

### 1.4 `claims.jsonl`

One JSON object per claim, schema v2. Only these fields are read:

| field | type | required | default | read at |
|---|---|---|---|---|
| `claim_id` | string | yes | — (`KeyError`) | `ask.py:201,211,329,335,355` |
| `doc_id` | string | yes | — (`KeyError` at `ask.py:344`) | `ask.py:210,344` |
| `statement` | string | no | `""` (`ask.py:177`), `""` in search (`ask.py:330`), `""` in citation (`ask.py:349`) | indexed ×3, dedup key, display |
| `actor` | string | no | `""` (`ask.py:178`) | indexed ×1 |
| `conditions` | array of strings | no | `[]` (`ask.py:179`) | joined with `" "`, indexed ×2 |
| `evidence` | array of objects | no | `[{}]` when absent **or empty** (`ask.py:174`, `ask.py:341`) | quotes and locator |
| `evidence[i].quote` | string | no | `""` in `_claim_text` (`ask.py:175`); `None` if the key exists with `null` in `_citation` (`ask.py:350`) | indexed ×1 (all items), `Citation.quote` (first item only) |
| `evidence[i].locator` | object | no | `{}` (`ask.py:174`, `ask.py:343`) | section/page/url |
| `evidence[i].locator.section_path` | array of strings | no | `[]` | indexed ×1 (first item only), `Citation.section_path` |
| `evidence[i].locator.page` | integer | no | `None` | `Citation.page`, never defaulted |
| `evidence[i].locator.url` | string | no | `None` → fallback to document `url` | `Citation.url` |
| `context` | object | no | `{}` | fallback title |
| `context.source` | string | no | `""` | **index `title` field** (`ask.py:181`) and title fallback |
| `schema_version`, `modality`, `deadline`, `conflicts_with`, `locator.kind`, `locator.char_start`, `locator.char_end`, `evidence[i].role` | any | no | ignored | not read by `ask` |

Consequences a reimplementation must preserve:

* `deadline` is **not** indexed; "how long" questions are answered only by words that also
  appear in `statement`, `conditions`, a quote, `context.source` or a section path.
* the ranking "title" is `claim.context.source`, **not** the `documents.jsonl` title; the two
  happen to be identical in the pilot KB (verified: 0 differences over 9295 claims).
* `conditions` is assumed to be a list. A JSON string would be joined character by character
  (`" ".join("abc")` → `"a b c"`); non-string elements raise `TypeError`.
* `section_path` is assumed to be a list. A string would be iterated character by character
  in `_claim_text` (`ask.py:182`) and in `list(...)` (`ask.py:352`).
* `evidence` may be absent, `[]`, or contain objects without `quote`/`locator`; all are handled
  by the `or [{}]` / `or {}` chain.

Real row (quotes truncated at `…`):

```json
{"claim_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10-0026", "doc_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10", "schema_version": 2, "statement": "If unknown, ICs revisit within 30 minutes.", "modality": "procedure_step", "actor": "ICs", "deadline": "30 minutes", "conditions": ["unknown"], "evidence": [{"quote": "To address Mina's first-30-minutes concern: …", "locator": {"kind": "text", "section_path": ["Vanessa"], "url": "https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench", "char_start": 5554, "char_end": 6178}, "role": "supports"}, {"quote": "IC decision rule (one-liner for the bot + policy page): …", "locator": {"kind": "text", "section_path": ["Sean"], "url": "https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench", "char_start": 7577, "char_end": 7904}, "role": "supports"}], "context": {"source": "dsid_020bac2fb6ac4de28d5afb63e39a0c10", "doc_type": "document"}}
```

Field presence in the pilot KB (9 295 claims): `actor` 3713,
`conditions` 3141, `deadline` 1121, `conflicts_with` 150; every claim has exactly one
`context` with keys `source` and `doc_type`; 6376 claims have one evidence item, 2736 two,
182 three or more; no locator carries `page`; every locator carries `kind`, `section_path`
(3728 claims with at least one non-empty path) and `url`.

### 1.5 `verifier.jsonl`

One object per claim, in claim order (`verify.py:293-295`):

| field | type | required | use |
|---|---|---|---|
| `claim_id` | string | yes (`KeyError` in the comprehension, `ask.py:201`) | map key |
| `verdict` | string | yes | filter value |
| `doc_id`, `reasons`, `notes` | any | no | ignored by `ask` |

`verify()` produces exactly three verdicts (`verify.py:276-280`): `"no"` when any hard rule
fails, `"weak"` when only soft rules fail, `"ok"` otherwise. Reasons are free text
(`verify.py:218-274`). Duplicate `claim_id`: last row wins (`ask.py:201`).

Real rows:

```json
{"claim_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10-0001", "doc_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10", "verdict": "ok", "reasons": [], "notes": []}
{"claim_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10-0003", "doc_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10", "verdict": "weak", "reasons": ["1/3 content tokens unattested (33%): option"], "notes": []}
{"claim_id": "dsid_5fc2dba9f6ac4af2b49b4f546a4298d0-0038", "doc_id": "dsid_5fc2dba9f6ac4af2b49b4f546a4298d0", "verdict": "no", "reasons": ["evidence[0]: quote not in the source"], "notes": []}
```

### 1.6 `text/<doc_id>.txt`

Not read by `ask`. `store.py:449-451` reads it with `encoding="utf-8", errors="ignore"` and
returns `""` when the file is missing; `texts()` builds `{doc["doc_id"]: text(...)}` for every
row of `documents.jsonl` (`store.py:453-454`). Pages are separated by a form feed `\f`
(`store.py:14`, `verify.py:130`); `page_containing` counts occurrences before an offset
(`verify.py:133-140`; `text.py:234-236` has the offset helper). The pilot KB was built from `kind: "text"` sources: 279 files, 0 form
feeds, all `page_range: null`, so every `Citation.page` is `None`.

`errors="ignore"` silently drops undecodable bytes; character offsets in `claims.jsonl`
(`char_start`, `char_end`) are offsets into this possibly-lossy string. The `ask` path never
uses those offsets.

### 1.7 `vectors.jsonl` (optional)

Written only with `ingest --semantic` (`cli.py:460-479`, `store.py:504-526`). Line 1 is a
header `{"model": ..., "revision": ..., "dim": ...}`; every following line is
`{"claim_id": string, "vector": array<number>}`. The reader (`store.py:421-435`) parses every
line and keeps the ones that have a `claim_id`, so the header is skipped by inspection, not by
position. `vectors_header()` (`store.py:437-447`) parses line 1 only and raises if the file is
empty. **The pilot KB has no `vectors.jsonl`** — the whole semantic branch is inactive there.

---

## 2. Tokenizer

### 2.1 `norm(text)` — `text.py:63-70`

Applied in order:

1. `str(text or "")` — `None`, `False`, `0`, `""` become `""`; other non-strings are stringified.
2. `.replace("\u2019", "'")` and `.replace("\u2018", "'")` — right/left single quotation mark to ASCII apostrophe.
3. `.replace("\u201c", '"')` and `.replace("\u201d", '"')` — curly double quotes to ASCII.
4. `.replace("\u2013", "-")` and `.replace("\u2014", "-")` — en dash and em dash to hyphen-minus.
5. `re.sub(r"\s+", " ", text)` — every run of Unicode whitespace becomes one U+0020. Python's
   `\s` includes `\t`, `\n`, `\r`, `\v`, `\f`, U+00A0 (NBSP), U+1680, U+2000–U+200A, U+2028,
   U+2029, U+202F, U+205F, U+3000.
6. `.strip()` — Unicode whitespace removed from both ends.

Not performed: Unicode NFC/NFD normalization, accent folding, case folding, punctuation
removal, removal of zero-width characters (U+200B/U+200C/U+200D/U+FEFF), folding of other
dash-like characters (U+2012, U+2015, U+2212), folding of single low quotes/prime (U+201A,
U+201B, U+2032). Two texts that differ only in one of those stay different.

Examples (first one is `test_documents_text.py:16-18`):

| input | `norm` | `tokens` |
|---|---|---|
| `"The Importer’s  “right”\n\tto – delete—"` | `The Importer's "right" to - delete-` | `["the","importer","right","to","delete"]` |
| `"Può essere più facile"` | unchanged | `["può","essere","più","facile"]` |
| `"5.1(b) of the Act"` | unchanged | `["of","the","act"]` |
| `"L'orologio è fissato alle diciotto."` | unchanged | `["orologio","fissato","alle","diciotto"]` |
| `"e\u0301cole"` (e + combining acute) | unchanged | `["cole"]` |
| `"x²"` | unchanged | `["x²"]` |
| `"İstanbul"` | unchanged | `["stanbul"]` |
| `"don't stop"` | unchanged | `["don","stop"]` |
| `"foo_bar"` | unchanged | `["foo","bar"]` |
| `"2024"` | unchanged | `["2024"]` |
| `"U.S.A."` | unchanged | `[]` |
| `"\u00a0non\u00a0breaking"` | `non breaking` | `["non","breaking"]` |

### 2.2 `tokens(text)` — `text.py:80-82`

Python expression, verbatim:

```python
[t for t in re.findall(r"[^\W_]+", str(text or "").lower()) if len(t) > 1]
```

* `str(text or "")` — same coercion as `norm`; `tokens` does **not** call `norm`.
* `.lower()` — full Unicode lowercase mapping, applied to the whole string before matching.
  Some characters expand (`İ` → `i` + U+0307), and the expansion changes token boundaries.
* `[^\W_]+` — maximal runs of characters that are Unicode word characters and not `_`.
  In CPython this is exactly `c.isalnum()` (letters of any script, decimal digits, and also
  numeric characters of categories No/Nl such as `²`, `½`, `Ⅷ`). Underscore, combining marks
  (Mn/Mc/Me), ZWJ, hyphens, apostrophes, punctuation and symbols are **not** word characters,
  so they split tokens.
* `len(t) > 1` — counts Unicode code points; single-character tokens are dropped (`a`, `i`,
  `è`, `5`, `b`, `²`, digits of a clause number). Contrast: `"²x"` is one token because the
  run has two characters.

### 2.3 `statement_tokens(text)` — `text.py:85-87`

`[t for t in tokens(text) if t not in STOPWORDS]`. Used by the verifier only, not by `ask`;
reproduced here because `_content` uses the same rule.

### 2.4 `STOPWORDS` — `text.py:21-60`

A `frozenset` of 284 distinct lower-case tokens. The literal contains 292 words; eight are
repeated and collapse in the set: `a`, `all`, `during`, `i`, `in`, `its`, `per`, `within`.
Membership is tested on already-lowercased tokens (`tokens` output), so the list itself is
lower case.

Source order, as written (`text.py:23-31` then `text.py:33-58`), duplicates preserved:

```
a an the and or but if then than that this these those it its it's is are
was were be been being do does did done have has had having shall must may
can could would should will not no nor so such as at by for from in into of
on onto over under with within without to up down out off again further
once here there when where why how all any both each few more most other
some only own same too very just also about above after before below
between during through during against among within upon per via i we you
he she they them their our your his her its who whom whose which what

a ad al alla alle allo agli ai
che chi cui ci si ne
di del della delle dello degli dei dall dalla dalle dallo dagli dai
da dal
in nel nella nelle nello negli nei
su sul sulla sulle sullo sugli sui
con coi
per
tra fra
e ed o od ma però se
non né anche ancora già sempre mai più meno molto poco troppo
il lo la i gli le un uno una
è sono essere siano sia stato stata stati
ha hanno avere avuto
deve devono debbono può possono potrebbe dovrebbe
questo questa questi queste quello quella quelli quelle
loro suo sua suoi sue nostro nostra nostri nostre
ogni qualche alcuni alcune alcuno alcuna
tutti tutte tutto tutta altro altra altri altre
stesso stessa stessi stesse proprio propria
ciascuno ciascuna nessuno nessuna nulla niente qualcosa
quale quali quanto quanta tanto tanta
senza contro verso entro oltre durante secondo tramite mediante
attraverso dopo prima sotto sopra fuori dentro accanto presso
viene vengono
dell all nell sull coll
```

Effective set (284), sorted — this is the authoritative membership list:

```
a about above accanto ad after again against agli ai al alcuna alcune alcuni alcuno all alla alle
allo also altra altre altri altro among an anche ancora and any are as at attraverso avere avuto
be been before being below between both but by can che chi ci ciascuna ciascuno coi coll con
contro could cui da dagli dai dal dall dalla dalle dallo debbono degli dei del dell della delle
dello dentro deve devono di did do does done dopo dovrebbe down durante during e each ed entro
essere few for fra from fuori further già gli ha had hanno has have having he her here his how i
if il in into is it it's its just la le lo loro ma mai may mediante meno molto more most must ne
negli nei nel nell nella nelle nello nessuna nessuno niente no non nor nostra nostre nostri nostro
not nulla né o od of off ogni oltre on once only onto or other our out over own per però più poco
possono potrebbe presso prima propria proprio può qualche qualcosa quale quali quanta quanto
quella quelle quelli quello questa queste questi questo same se secondo sempre senza shall she
should si sia siano so some sono sopra sotto stata stati stato stessa stesse stessi stesso su sua
such sue sugli sui sul sull sulla sulle sullo suo suoi tanta tanto than that the their them then
there these they this those through to too tra tramite troppo tutta tutte tutti tutto un una under
uno up upon vengono verso very via viene was we were what when where which who whom whose why will
with within without would you your è
```

### 2.5 Stems — `_key(term)`, `ask.py:62-67`

```
STEM_PREFIX = 7
_key(term) = term[:7] if len(term) > 7 else term
```

`len` and the slice count Unicode code points (not bytes). Applied to both index and query
tokens, after stopword removal. Examples (verified):

| term | `_key` |
|---|---|
| `chi` | `chi` |
| `chiuso` | `chiuso` (6 characters, not cut) |
| `fornitore` | `fornito` |
| `fornitori` | `fornito` |
| `certificato` | `certifi` |
| `certificazioni` | `certifi` |
| `consegnata` | `consegn` |
| `conseguenza` | `consegu` |
| `abcdefgh` | `abcdefg` |

### 2.6 `_content(text)` — `ask.py:70-79`

`[term for term in tokens(text) if term not in STOPWORDS]`. No stemming here; callers apply
`_key` afterwards. Duplicates are kept.

Query pipeline, exactly (`ask.py:283`):

```
query = [_key(term) for term in _content(question)]
```

So: lowercase → split on non-alphanumerics → drop 1-character tokens → drop stopwords → cut to
7 code points. A question token that is a stopword is removed **before** stemming, so a stopword never
reaches `_key` at all.

---

## 3. Ranking

### 3.1 Corpus construction and verdict filter

`Corpus.__init__` (`ask.py:189-234`), in this order:

1. `self.verdicts = {row["claim_id"]: row["verdict"] for row in (verdicts or ())}` (`ask.py:201`).
2. `self.claims` = input claims filtered by (`ask.py:203-209`):
   `include_unverified or not self.verdicts or self.verdicts.get(claim["claim_id"], "ok") == "ok"`.
3. `self.documents = {doc["doc_id"]: doc for doc in documents}` (`ask.py:210`).
4. `self._by_id = {claim["claim_id"]: claim for claim in self.claims}` (`ask.py:211`).
5. index arrays are built from `self.claims` only (`ask.py:218-233`); every array is aligned by
   position with `self.claims`.

`self.claims` keeps the input order of `claims.jsonl`. The filter never reorders.

### 3.2 Indexed text per claim — `_claim_text`, `ask.py:173-183`

For a claim `c`, with `first = (c["evidence"] or [{}])[0]` and
`locator = first.get("locator") or {}`:

| field | exact value |
|---|---|
| `statement` | `c.get("statement", "")` |
| `actor` | `c.get("actor", "")` |
| `conditions` | `" ".join(c.get("conditions") or [])` |
| `quote` | `" ".join((item.get("quote") or "") for item in c.get("evidence") or [])` — **all** evidence items, not only the first |
| `title` | `(c.get("context") or {}).get("source", "")` — **not** the document title |
| `section` | `" ".join(str(p) for p in locator.get("section_path") or [])` — first evidence item only |

Missing `evidence` or `[]`: the `or [{}]` gives an empty locator and an empty quote, so
`quote=""`, `section=""`.

### 3.3 Weights, length, document frequency, average length

`FIELD_WEIGHTS` (`ask.py:42-49`), in this insertion order:

```python
{"statement": 3.0, "actor": 1.0, "conditions": 2.0, "quote": 1.0, "title": 1.0, "section": 1.0}
```

Per claim (`ask.py:218-233`):

```
field_tokens[name] = [_key(term) for term in _content(value)]     # per field
repeats            = max(1, int(round(weight)))                   # 3,1,2,1,1,1
weighted           = concat(field_tokens[name] repeated `repeats` times, in FIELD_WEIGHTS order)
length             = max(1, len(weighted))
for term in set(weighted): df[term] += 1
```

`int(round(w))` uses Python `round`: banker's rounding (half to even). With the current
weights (`3.0`, `2.0`, `1.0`) the result is exact and the rule only matters if weights change.
A claim whose fields contain no content token still gets `length = 1`; it is counted in
`avg_length` and can never match.

```
avg_length = sum(lengths) / len(lengths) if lengths else 0.0        # ask.py:234
```

Unit of `length`: weighted token occurrences. A statement word counts 3, a conditions word or
any word in the concatenated quotes, title, or section path counts 1. `modality`, `deadline`,
`doc_id`, `char_*` are not indexed.

### 3.4 IDF and score

`_idf(term) = ln(1 + (N - df + 0.5) / (df + 0.5))` (`ask.py:236-239`), where
`N = len(self.claims)` (post-filter) and `df = self.df.get(term, 0)`; `math.log` is the natural
logarithm. The value is always positive for `df <= N`.

For each claim index `i` with `counts = counts of stemmed tokens in weighted` (`ask.py:287-299`):

```
score = 0.0
for term in query:                       # query order, duplicates included
    f = counts.get(term, 0)
    if f == 0: continue
    denom = f + K1 * (1 - B + B * length[i] / (avg_length or 1))
    score += idf(term) * f * (K1 + 1) / denom
```

Constants: `K1 = 1.5`, `B = 0.75` (`ask.py:39-40`). `avg_length or 1` means a zero average
(empty corpus, unreachable because search returns early) would divide by 1.

Worked example, verified (`Corpus` with one claim, statement `"retention alpha"`, quote
`"retention alpha"`, `context.source "src"`): weighted tokens
`[retenti, alpha, retenti, alpha, retenti, alpha, retenti, alpha, src]`, length 9,
avg 9, `f(alpha) = 4`, `df(alpha) = 1`, `N = 1`,
`idf = ln(1 + 0.5/1.5) = 0.287682`, `denom = 4 + 1.5*(1 - 0.75 + 0.75*1) = 5.5`,
`score = 0.287682 * 4 * 2.5 / 5.5 = 0.5231`. With a second claim `"retention beta"`:
`N = 2`, `idf(alpha) = ln(2) = 0.693147`, score `1.2603` (`round(…, 4)`).

A repeated query word is not deduplicated: `search("alpha alpha")` adds the same term twice and
doubles the score (verified: `0.2428` → `0.4856` on the three-claim fixture below).

### 3.5 Ordering and the `score > 0` filter — `ask.py:303-307`

```
ranked = sorted((i for i in range(len(scores)) if scores[i] > 0),
                key=lambda i: scores[i], reverse=True)
```

* Only strictly positive scores are candidates. A claim matching only a query term with
  `df == 0` (impossible) or with no query term at all scores `0.0` and is dropped,
  even if the candidate window has room.
* `sorted` is stable and `reverse=True` preserves stability: among equal scores the claim with
  the **smaller index in `self.claims`** comes first, i.e. the earlier line of `claims.jsonl`.
  Verified: three claims with identical fields return `D1-0001, D1-0002, D2-0001`.
* Ties are decided on the exact IEEE-754 double produced by the accumulation above; no
  epsilon, no rounding before ordering. Scores are rounded only when copied into `Citation`.

### 3.6 Semantic fusion (only when a semantic ranking is supplied) — `ask.py:313-324`

```
lexical = {claim_id: score for claim index in ranked}          # insertion order = ranking order
if semantic_ranking:
    fused = fuse([list(lexical), semantic_ranking])           # vector.py:46-52
    weight = dict(fused)
    order  = {claim_id: position for position, (claim_id, _) in enumerate(fused)}
    ranked = [i for i in range(len(self.claims)) if self.claims[i]["claim_id"] in order]
    ranked.sort(key=lambda i: order[self.claims[i]["claim_id"]])
```

`fuse` sums `1 / (60 + rank)` over rankings, ranks starting at 1 (`vector.py:16`, `:50-51`), and
returns `sorted(scores.items(), key=lambda item: (-item[1], item[0]))`: descending RRF score,
ties broken by **ascending `claim_id` string comparison** (Python code-point order).

Properties a port must keep:

* the lexical ranking contributes **all** claims with `score > 0`, with no depth cap; the
  semantic ranking arrives already capped at 200 (`ask.py:257-275`);
* the fused order is the union: a semantic-only claim is placed by its RRF score although its
  BM25 score is `0.0` (`ask.py:309-312` explains why this is not done by re-sorting);
* when fusion is active, `Citation.score` is the RRF weight, not BM25 (`ask.py:334`);
* if a claim id in `semantic_ranking` is not in the corpus, it stays in `fused`/`order` and is
  silently ignored by the `range(len(self.claims))` filter;
* ties in the fused order are broken by `claim_id`, unlike the lexical order which breaks them
  by claim position.

### 3.7 Window, deduplication, stop condition — `ask.py:326-338`

```
out = []
seen_statements = set()
for index in ranked[: max(limit * 4, limit)]:
    claim = self.claims[index]
    claim_id = claim["claim_id"]
    key = norm(claim.get("statement", "")).lower()
    if key in seen_statements:
        continue
    seen_statements.add(key)
    out.append(self._citation(claim, weight.get(claim_id, scores[index])))
    if len(out) >= limit:
        break
```

* Window: `max(limit * 4, limit)` candidates are inspected. For `limit >= 0` it is `limit*4`.
* Dedup key: `norm(statement).lower()` — curly quotes and dashes folded, whitespace collapsed
  and stripped, then Unicode-lowercased. Punctuation is **not** removed and accents are
  **not** folded, so `"Records retained."` and `"Records retained"` are distinct keys
  (verified), while `"Records retained."` and `"records RETAINED."` collide (verified).
  A claim without `statement` has key `""`; all such claims collapse to one.
* The window is applied **before** deduplication: skipped duplicates do not extend the scan.
* Stop condition: after appending, `len(out) >= limit` breaks. `limit = 0` yields `[]`
  (window empty). A negative `limit` yields one citation: `max(limit*4, limit) == limit < 0`,
  the slice `ranked[:negative]` is non-empty, and `1 >= limit` is true after the first append
  (verified: `limit=-1` returns 1).
* Default `limit` is 12 in `Corpus.search` (`ask.py:280`), in `ask` (`ask.py:434`) and in the
  CLI option `-n/--limit` (`cli.py:601`).

### 3.8 Score-bearing order versus display order

`search` returns citations in ranking order. `Answer.documents` (`ask.py:158-164`) lists distinct
`doc_id` in first-citation order; `Answer.by_document()` (`ask.py:166-170`) groups citations by
document, with groups in first-citation order and citations inside a group in ranking order.

---

## 4. Citation

`Corpus._citation` (`ask.py:340-356`) with `evidence = claim.get("evidence") or [{}]`,
`first = evidence[0]`, `locator = first.get("locator") or {}`,
`document = self.documents.get(claim["doc_id"], {})`:

| field | type | exact source | fallback chain |
|---|---|---|---|
| `claim_id` | string | `claim["claim_id"]` | none |
| `doc_id` | string | `claim["doc_id"]` | none |
| `title` | string | `document.get("title") or (claim.get("context") or {}).get("source", claim["doc_id"])` | empty/absent document title → `context.source`; absent `source` → `doc_id`; `context: null` → `{}` → `doc_id` |
| `statement` | string | `claim.get("statement", "")` | `""` |
| `quote` | string \| null | `first.get("quote", "")` | `""` only when the key is **absent**; an explicit `null` stays `None` |
| `page` | int \| null | `locator.get("page")` | `None`; not coerced to int; `0` is kept |
| `section_path` | list | `list(locator.get("section_path") or [])` | `[]`; elements are not stringified or validated |
| `url` | string \| null | `locator.get("url") or document.get("url", "")` | missing/empty/falsy locator URL → document `url`; missing document `url` → `""`; a present `null` document URL stays `None` |
| `score` | float | `round(score, 4)` | BM25 score, or RRF weight when fusion is active |
| `verdict` | string | `self.verdicts.get(claim_id, "ok")` | `"ok"` when there is no row |

`round(x, 4)` is Python's `round`: correct rounding of the binary double, ties to even. It is
not truncation and not `format`. Verified: an unrounded score of `0.523058…` is stored as
`0.5231`, and `1.26026…` as `1.2603`.

Only the **first** evidence item supplies `quote`, `page`, `section_path`, `url`; the other
items exist only in the ranking text and in `verifier.jsonl` reasons. The pilot example
`…-0026` is cited with `quote` = the `Vanessa` quote and `section_path` = `["Vanessa"]`, even
though the `Sean` quote was also indexed.

`Citation.label()` (`ask.py:136-142`): join with `", "` of `title or doc_id`, then
`f"p. {page}"` only when `page` is truthy, then `" > ".join(section_path)` only when
`section_path` is non-empty. `page == 0` is omitted (falsy).

### 4.1 `render_text(answer)` — `ask.py:442-464`

Line by line, with `\n` joins:

```
Question: {answer.question}
<empty line>
== {citations[0].title}  [{doc_id}]  ({len(group)} claim(s))
  {claim_id}  {"" if verdict=="ok" else "["+verdict+"] "}{statement}
      source: {label()}
      quote: "{quote[:400]}"
<empty line after each document group>
Tensions in the corpus:                      # only if answer.tensions
  {topic}: {reason}
    - {value}: {claim}
<empty line>
Documents answering: {len(groups)} ({", ".join(groups)})
```

The quote line is emitted only when `citation.quote` is truthy, truncated to 400 **characters**
(code points) with no ellipsis. The document header uses the title of the first citation of the
group, not the document row. The blank line before `Documents answering:` is the one appended
after the last document group; with zero citations there is no group and therefore no blank
line. The tensions block appends its own blank line after the last tension.

### 4.2 `--json` — `cli.py:617-624`

`json.dumps({"question": ..., "documents": [doc_id, …], "citations": [citation.__dict__, …],
"tensions": [tension.__dict__, …]}, ensure_ascii=False, indent=1)`. Citation keys, in dataclass
order: `claim_id, doc_id, title, statement, quote, page, section_path, url, score, verdict`.
Tension keys: `topic, values` (array of two-element arrays), `reason`.

---

## 5. Verifier filter

Source of truth is the filter at `ask.py:203-209`, evaluated once at construction:

| `verdicts` | `include_unverified` | claim's verdict | kept? |
|---|---|---|---|
| `{}` (missing or empty file) | either | any | **yes** |
| non-empty | `True` | any | **yes** |
| non-empty | `False` | row absent for `claim_id` | **yes** (default `"ok"`, `ask.py:208`) |
| non-empty | `False` | `"ok"` | yes |
| non-empty | `False` | `"weak"` | no |
| non-empty | `False` | `"no"` | no |
| non-empty | `False` | any other string | no |

So `include_unverified=True` is not "also weak": it disables filtering entirely. `weak` and
`no` claims are both excluded by default; there is no way to include only `weak`.

`Citation.verdict` is always the raw map value (`"ok"`, `"weak"`, `"no"` or an arbitrary
string), defaulting to `"ok"`, and is what `render_text` prints as a `[verdict]` badge for
non-`ok` citations (`ask.py:449`).

CLI notes (`cli.py:553-562`): when `kb.verifier()` is empty the command prints
`warning: no verifier.jsonl: unverified claims are shown unfiltered` before answering. The
message is printed for an empty existing file too, and the wording describes the effect
correctly but the filename may not be the cause.

The verifier itself (`verify.py:194-280`) is not part of the query path; the read path only
consumes its output. Verdict semantics for a port that regenerates it: hard failure → `"no"`,
only soft failures → `"weak"`, none → `"ok"` (`verify.py:276-280`); soft tolerance is
`PARAPHRASE_TOLERANCE = 0.25` with `share > 0.25` failing (`verify.py:88`, `:247-248`).

---

## 6. Semantic fusion

### 6.1 Activation

Two independent gates.

CLI (`cli.py:614-615`): semantic is attempted when the option value is not `False`, i.e. by
default and with `--semantic`; `--no-semantic` skips it entirely. `_enable_semantic`
(`cli.py:565-594`) then requires all of:

1. `kb.vectors()` is non-empty. If empty: silent when the flag was not typed; with `--semantic`
   it prints `semantic ranking unavailable (no vectors.jsonl): BM25 only`.
2. `supports(languages)` where
   `languages = set((kb.manifest().get("languages") or {}).values())` (`cli.py:579`).
   `supports` (`vector.py:28-31`) returns `True` when the set is empty (nothing declared) and
   otherwise only when at least one language is in `LANGUAGES = {"en"}` (`vector.py:25`).
   If it fails: `semantic ranking skipped: {MODEL} is trained on en, the corpus is it: BM25 only`.
3. `embedder_for(kb)` succeeds (`vector.py:83-87`): the header `model` must be absent or equal
   to `sentence-transformers/all-MiniLM-L6-v2`; then `SentenceTransformer` is loaded from the
   local cache with `local_files_only=True`. Any exception (including `ImportError`, `OSError`,
   `ValueError`) is caught by `except Exception` and printed as
   `semantic ranking unavailable ({exc}): BM25 only`.

`Corpus.enable_semantic(vectors, embedder, languages)` (`ask.py:241-255`) repeats the language
check and returns `False` without storing anything when unsupported; the CLI ignores the return
value but has already applied the same check.

### 6.2 Ranking

`Corpus.semantic_ranking(question, depth=200)` (`ask.py:257-275`):

```
if self._semantic is None: return []
asked = embedder.encode_one(question)                 # exactly one model call per question
scored = [(claim_id, cosine(asked, vector))
          for claim_id, vector in vectors.items()
          if claim_id in self._by_id]                 # verified claims only
scored.sort(key=lambda item: (-item[1], item[0]))     # descending cosine, ties by claim_id
return [claim_id for claim_id, _ in scored[:depth]]
```

`cosine` (`vector.py:35-43`): raises `ValueError("vectors of different length")` on a dimension
mismatch; returns `0.0` if either norm is zero; otherwise dot product divided by the product of
Euclidean norms. The embedder writes unnormalized vectors at build time (`vector.py:73-77`) and
rounds to 6 decimals.

`ask` calls this once per question, before `search` (`ask.py:437`), and only when
`tokens(question)` is non-empty. The vector text at build time is
`" ".join(value for value in _claim_text(claim).values() if value)` (`store.py:515`), i.e. the
same six fields used for the lexical index, concatenated in the dict order
statement, actor, conditions, quote, title, section.

### 6.3 Fusion

Reciprocal Rank Fusion, `k = RRF_K = 60` (`vector.py:16`, `:46-52`):

```
score[claim_id] = sum over rankings of 1 / (60 + rank)   # rank starts at 1
fused = sorted(score.items(), key=lambda it: (-it[1], it[0]))
```

Then `ask.py:313-324` places every corpus claim found in `fused` in fused order, and the
window/dedup step runs on that order. `Citation.score` becomes the fused weight
(`ask.py:334`): `1/61 ≈ 0.01639` for a first place in one ranking, `2/61 ≈ 0.03279` for a first
place in both, and smaller for a deep lexical rank (the lexical list is unbounded, so a rank of
9000 contributes `1/9060 ≈ 0.00011`). It is not comparable with BM25 scores. No weights are
tuned and no normalisation is applied.

### 6.4 When something is missing

| missing piece | behaviour |
|---|---|
| `vectors.jsonl` absent (pilot KB) | `kb.vectors() == {}` → `_enable_semantic` returns early; `_semantic` stays `None`; `semantic_ranking` returns `[]`; pure BM25; no error, no output unless `--semantic` was typed |
| `manifest.languages` absent | empty set → `supports` returns `True`; fusion would be attempted if vectors exist |
| corpus declared Italian only | fusion refused, BM25 only (`vector.py:18-25` rationale) |
| `sentence-transformers` / `torch` not installed | exception caught at `cli.py:593`; dim one-line message; BM25 |
| `vectors.jsonl` header names another model | `ValueError` in `embedder_for`, caught at `cli.py:593`; BM25 |
| a vector has the wrong dimension | `cosine` raises inside `semantic_ranking`, which `ask` does not catch: the command fails (see Suspected defects) |
| `vectors.jsonl` exists but is empty | `vectors()` returns `{}`; `vectors_header()` raises `JSONDecodeError` if called (it is called only by `embedder_for`, which is reached only when `vectors()` is non-empty) |

**Pilot KB fact:** the pilot knowledge base contains no `vectors.jsonl` (directory listing,
2026-11-17), and every `manifest.languages` value is `"en"`. If vectors were added, fusion
would activate by default.

---

## 7. Tensions / contradictions

Tensions are computed from the **returned citations only** (`ask.py:439`), so `limit` and the
verdict filter change them. `conflicts_with` in `claims.jsonl` is ignored by this path; the
compiler's conflict links and the tension report are unrelated mechanisms.

### 7.1 `durations(text)` — `ask.py:359-373`

Complete unit table (`ask.py:81-94`), hours per unit:

```python
{"hour": 1, "hours": 1, "working hour": 1, "working hours": 1,
 "day": 24, "days": 24, "week": 168, "weeks": 168,
 "month": 730, "months": 730, "year": 8760, "years": 8760}
```

Number words (`ask.py:96-99`): `one` 1, `two` 2, `three` 3, `four` 4, `five` 5, `six` 6,
`seven` 7, `eight` 8, `nine` 9, `ten` 10, `eleven` 11, `twelve` 12.

Regex (`ask.py:100-104`), compiled with `re.IGNORECASE`:

```
_NUMBER = r"\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
DURATION = rf"(?<![\w.])({_NUMBER})\s*(working\s+)?(hours?|days?|weeks?|months?|years?)(?![\w])"
```

Algorithm:

1. `DURATION.findall(text or "")` returns triples `(amount, working, unit)` in left-to-right,
   non-overlapping order. Alternation order matters: digits are tried before number words.
2. `amount.lower() in WORD_NUMBERS` → `float(WORD_NUMBERS[amount.lower()])`; otherwise
   `float(amount.replace(",", "."))` (so `1,5` → `1.5`, `1.5` → `1.5`).
3. `key = unit.lower()`; look up `UNIT_HOURS`; if absent, skip (unreachable with the current
   regex, whose alternatives are all keys).
4. `label = norm(f"{amount} {'working ' if working else ''}{key}")` — amount keeps its original
   case and separators (`Six years`), unit is lowercased, whitespace collapsed. `working` keeps
   the plural/singular unit as printed (`working days`).
5. append `(label, number * hours)`; the product is a float.

Behaviour verified on the reference:

| input | result |
|---|---|
| `"within 48 hours"` | `[("48 hours", 48.0)]` |
| `"within 3 working days"` | `[("3 working days", 72.0)]` |
| `"six years after the end of the contract"` | `[("six years", 52560.0)]` |
| `"retain for two years"` | `[("two years", 17520.0)]` |
| `"1,5 anni"` | `[]` (Italian units are not recognised) |
| `"12 MONTHS"` | `[("12 months", 8760.0)]` |
| `"2-3 days"` | `[("3 days", 72.0)]` — only the last number |
| `"1.48 hours"` | `[("1.48 hours", 1.48)]` — the look-behind cannot reject a number at the match start |
| `"48hours"` | `[("48 hours", 48.0)]` — `\s*` allows zero spaces |
| `"for 2 weeks and 3 days"` | `[("2 weeks", 336.0), ("3 days", 72.0)]` |

Fixed conversions to note: a month is 730 hours (30.4167 days), a year is 8760 hours (365
days), a "working day/hour" has the same length as a calendar one; the `working` flag affects
only the label.

### 7.2 `topic_of(text)` — `ask.py:376-388`

```python
TOPICS = {
  "breach_notification": ("breach", "notify", "notification", "inform", "incident", "data loss event"),
  "retention": ("retain", "retention", "delete", "deletion", "erasure", "erase", "destroy"),
  "audit": ("audit", "inspection", "inspect", "access to records"),
  "transfer": ("transfer", "transfers", "onward transfer"),
}
```

`said = " " + " ".join(tokens(text)) + " "` (note: `tokens`, not `statement_tokens`; no
stemming). A topic matches when any of its phrases occurs as the substring
`f" {phrase} "` in `said`. `found` is built in `TOPICS` insertion order; the function returns
`found[0]` if exactly one topic matched, else `None` (zero or two or more topics).

Consequences:

* matching is whole-token and exact: `inform` does not match `informed`, `transfer` does not
  match `transfers` (both spellings are listed separately), `erase` does not match `erased`;
* a phrase with two or three words requires those tokens adjacent after tokenisation
  (`data loss event`, `access to records`, `onward transfer`);
* `tokens` drops one-letter tokens and lowercases, so case and punctuation do not matter;
* a text that names a breach and a retention period is ambiguous and is excluded.

### 7.3 `find_tensions(citations)` — `ask.py:391-431`

Exact steps:

1. For each citation in list order:
   `subject = " ".join([citation.statement, citation.quote])` — `quote` is the **first
   evidence quote only**; a `None` quote would raise `TypeError`.
2. `topic = topic_of(subject)`; `None` → skip.
3. `found = durations(subject)`; empty → skip; only `found[0]` is used (the leftmost duration in
   the statement+first-quote string).
4. Append `(label, hours, claim_id, doc_id)` to `buckets[topic]`.
5. Iterate `sorted(buckets.items())` — topic names in ascending string order:
   `audit`, `breach_notification`, `retention`, `transfer`.
6. `distinct` = dict `hours -> [(label, f"{claim_id} ({doc_id})"), …]` in bucket order, grouped
   by the **float** hours value (`730.0` and `730.0` group; `1.5` and `1.50` group).
7. Skip if `len(distinct) < 2`.
8. `docs = {doc_id ...}` over the bucket; skip if `len(docs) < 2` (a document contradicting
   itself is not a tension).
9. `values` = for `hours` in `sorted(distinct)` (numeric ascending), extend with that group's
   labels in insertion order.
10. `reason = f"{len(distinct)} different {topic.replace('_', ' ')} periods across {len(docs)} documents"`.
11. Append `Tension(topic, values, reason)`; the result is in topic-sorted order.

Data classes: `Tension.values` is `list[tuple[label, "claim_id (doc_id)"]]`
(`ask.py:145-149`), `Citation` as in §4.

Verified real output on the pilot KB, question
`"How many days do we have to notify a data breach?"`, default `limit=12`, no semantic
(2026-11-17):

```
tensions = 1
topic  = "breach_notification"
reason = "3 different breach notification periods across 4 documents"
values = [
  ("4 hours",  "dsid_9c8cb10d65324c03a8ededbd98c1b058-0022 (dsid_9c8cb10d65324c03a8ededbd98c1b058)"),
  ("72 hours", "dsid_98d7acbda29a4260a413c8d6da7207a3-0040 (dsid_98d7acbda29a4260a413c8d6da7207a3)"),
  ("72 hours", "dsid_36d7605113204cdca94405cb30fc2c10-0076 (dsid_36d7605113204cdca94405cb30fc2c10)"),
  ("30 days",  "dsid_6df52fdb96ae4edcb76464738bca3340-0016 (dsid_6df52fdb96ae4edcb76464738bca3340)")
]
```

The question `"vendor audit frequency years"` (same settings) produced one `retention`
tension with reason `"3 different retention periods across 2 documents"` and values
`90 days` (twice, both in `dsid_7c73cb76b80a41edb4959db4b1e7308b`), `2 years`
(`dsid_7c73…-0012`), `7 years` (three claims in `dsid_ba7d1565b0694e359983bccaa4bf5977`). Note
that `len(docs)` counts documents in the bucket, not documents per distinct value.

---

## 8. Refusal

There is **no refusal**. `Answer` has exactly three fields — `question`, `citations`,
`tensions` (`ask.py:152-156`) — and no `refused` attribute, no confidence, no "I don't know".
Any Rust port that adds `Answer.refused` would have no counterpart to match.

`citations == []` occurs when any of these holds:

1. `_content(question)` is empty after stopword removal (`ask.py:284`) — e.g. `""`,
   `"the of and"`, `"a"`, `"???"`;
2. the corpus kept no claims after the verdict filter (`ask.py:284`);
3. no kept claim has a positive score (`ask.py:303-307`);
4. every candidate inside the `max(limit*4, limit)` window is a duplicate statement
   (`ask.py:328-333`); with `limit <= 0` the window is empty or perverse (§3.7).

Note the asymmetry in `ask` (`ask.py:437-438`): the semantic ranking is attempted whenever
`tokens(question)` is non-empty, which includes questions made only of stopwords; `search`
then returns `[]` before fusion, so one embedding is computed and discarded. Semantic ranking
alone can never answer a question whose lexical query is empty.

When `len(answer.documents) < 2`, the CLI prints, after the text output
(`cli.py:626-630`):
`note: this answer cites one document; the demo's exit criterion is at least two per question.`
The `--json` path returns before this note and contains no equivalent field.

The only hard failure in the command is a missing/empty `claims.jsonl` (`cli.py:610-612`);
the message is:

```
{kb_dir}: no claims.jsonl; run `ontocore ingest` first
```

and it is raised as a `ClickException` (exit code 1).

---

## 9. SPARQL

There is no documents-specific SPARQL module. `core/src/documents/` has none; the only query
engine is `core/src/sparql.py`, generic over any Turtle file, exposed as `ontocore query`
(`cli_query.py:17-53`). It is used against `graph.ttl` (`store.py:213-343`, written by
`build_graph`) by passing `-o kb/graph.ttl`; the read path (`ask`) never calls it and never
opens `graph.ttl`.

`execute_sparql(ontology_path, query)` (`sparql.py:23-73`):

1. `ontology_path.exists()` false → `SPARQLError(f"Ontology file not found: {ontology_path}")`
   (`sparql.py:37-38`).
2. `Graph().parse(path, format="turtle")`; any exception →
   `SPARQLError(f"Failed to load ontology: {e}")` (`sparql.py:40-45`).
3. Read-only guard (`sparql.py:47-52`): `query_upper = query.upper()`; for each keyword in
   `["INSERT", "DELETE", "DROP", "CREATE", "CLEAR", "LOAD"]` in that order, if
   `keyword in query_upper` → `SPARQLError(f"Mutation operations ({keyword}) are not supported")`.
   This is a plain substring test on the uppercased query, not a grammar check.
4. `graph.query(query)`; any exception → `SPARQLError(f"Invalid query: {e}")` (`sparql.py:54-73`).

Limits and validation: none. No `LIMIT` is added or enforced, no maximum result count, no
timeout, no allowed-verb whitelist, no comment stripping. A query with no `LIMIT` returns every
solution; memory and time are bounded only by rdflib. `graph.query` itself does not implement
SPARQL Update, so the guard is the only barrier, and it is defeated by the substrings being
absent.

False positives the substring guard produces (it must be reproduced, not "fixed"):

* `CREATE` matches `created` — any literal or IRI containing `created`, `Deleted`,
  `loader`, `dropbox`, `clearance` is rejected;
* `LOAD` matches `loaded`, `payload`, `download`;
* `DELETE` matches `deleted`;
* the message names the **first** keyword in the list order that occurs anywhere in the string,
  e.g. a query containing both `DELETE` and `INSERT` reports `DELETE`.

Return shape: despite the annotation `-> list[dict[str, Any]]`, the function returns a tuple
`(rows, vars)` (`sparql.py:70`), where `rows` is a list of dicts mapping `str(variable)` to
`str(value)` (or `None` for unbound) and `vars` is the list of rdflib `Variable` objects.
`format_results(results, format, vars)` (`sparql.py:76-120`) supports:

* `json` → `json.dumps(results, indent=2, default=str)`;
* `turtle` → not Turtle: `"{var}: {val}"` lines, one blank line between rows;
* `table` (default) → rich table titled `Query Results`, columns from `vars`, missing values
  rendered as `""`.

CLI messages (`cli_query.py:36-53`):

* ontology missing → prints `Ontology not found: {path}` then raises `SPARQLError` with the same text;
* empty result → prints `No results` and returns (exit code 0);
* `SPARQLError` → prints `Query error: {e}` and re-raises (non-zero exit).

Pilot KB consequence: `graph.ttl` exists (16.7 MB, 2026-11-16), so `ontocore query "..."`
works against it, but no part of `ontocore ask` reads it. Claim text, quotes and sections in
the graph come from the same `claims.jsonl` rows, so answers are consistent by construction,
not by lookup.

---

## 10. Ambiguities and traps

Each item states what the Python actually does; none of these may be "improved" in a faithful
port.

1. **Tie order in the lexical ranking.** `sorted(..., reverse=True)` is stable, so equal scores
   keep ascending claim index — i.e. `claims.jsonl` line order after the verdict filter.
   Sorting descending by tuple or by `(score, claim_id)` diverges (`ask.py:303-307`).
2. **Tie order after fusion.** Different rule: RRF ties break by ascending `claim_id`
   (code-point/UTF-8 byte order), and the final order is the `fused` list order
   (`ask.py:315-324`, `vector.py:52`). Lexical ties and fused ties are decided on different keys.
3. **Duplicate query terms.** `_content` does not deduplicate; the scoring loop iterates the
   query list, so `"breach breach"` adds the term twice and doubles the score (`ask.py:283`,
   `:293-299`). Verified: `0.2428` → `0.4856`.
4. **Float accumulation order.** Scores are summed in query order and divided per term; the
   result is an IEEE-754 double with no compensation. `math.log` is the platform `log`
   (`ask.py:239`). A Rust port using `ln` and a different summation order can differ in the
   last ULP and flip an exact tie. Ordering must use the unrounded double.
5. **`round(score, 4)`.** Python `round` on a float is round-half-to-even, not Rust
   `f64::round` (half away from zero), and it rounds the binary value, not a decimal string
   (`ask.py:354`). `13.68085` may round down.
6. **Dedup window.** `ranked[: max(limit*4, limit)]` is sliced **before** deduplication, and a
   skipped duplicate does not extend the window. Verified: 9 claims with the same statement
   plus one distinct claim, `limit=2`, window 8 → exactly 1 citation (`ask.py:328-333`).
7. **Unicode `\w`.** `[^\W_]+` in CPython equals `str.isalnum()`: it includes No/Nl characters
   (`²`, `½`, `Ⅷ`) and excludes combining marks (Mn/Mc/Me), ZWJ and underscore. Rust `regex`
   `\w` is Alphabetic + M + Nd + Pc + Join_Control: it includes marks and ZWJ and excludes
   No/Nl. Both directions differ; `"e\u0301cole"` → `["cole"]` in Python, `"x²"` → `["x²"]`
   (`text.py:77`).
8. **`lower()` before tokenising.** Python lowercases the whole string first; expansions such
   as `İ` → `i` + U+0307 change token boundaries (`"İstanbul"` → `["stanbul"]`). Rust's
   `to_lowercase` also expands, but any ASCII-only lowering diverges (`text.py:82`).
9. **`_key` counts code points.** `len(term) > 7` and `term[:7]` operate on characters, not
   bytes; byte slicing on UTF-8 would cut differently and produce different keys for accented
   words (e.g. `"qualitàx"`) (`ask.py:65-67`).
10. **`norm` is not normalisation.** No NFC/NFD, no accent folding, no case folding, no
    punctuation removal. Only U+2018/U+2019/U+201C/U+201D/U+2013/U+2014 are folded; U+201A,
    U+201B, U+2032, U+2012, U+2212 survive. Two visually identical quotes with different code
    points (after `norm`) tokenise differently and dedupe differently (`text.py:63-70`).
11. **Whitespace.** `\s+` → one space is Unicode-aware and includes NBSP (U+00A0), U+2028,
    U+2029, U+3000; `strip()` uses Unicode whitespace. A port using ASCII whitespace keeps
    NBSP inside tokens and changes both tokens and the dedupe key (`text.py:69-70`).
12. **Dedup key construction.** `norm(statement).lower()`: case-folded but punctuation kept, so
    `"Retention is six years."` and `"Retention is six years"` are two citations (verified),
    while `"Records retained."` and `"records RETAINED."` collapse (verified). Using `tokens`
    or the stemmed bag here would merge more (`ask.py:330`).
13. **`conditions` join.** `" ".join(claim.get("conditions") or [])` assumes a list of strings.
    A JSON string is iterated character by character; a number raises `TypeError`
    (`ask.py:179`).
14. **Title mismatch.** Ranking uses `claim.context.source`; display uses the `documents.jsonl`
    title with `context.source` as fallback. In the pilot KB they are equal for all 9295
    claims; do not assume it for another KB (`ask.py:181` vs `ask.py:348`).
15. **Quote scope.** Ranking concatenates all evidence quotes; citation and tensions see only
    `evidence[0].quote`. A duration stated in the second quote is indexed but invisible to
    `find_tensions` (`ask.py:175` vs `ask.py:350`, `:395-398`).
16. **`page` truthiness.** `label()` prints `p. {page}` only when `page` is truthy, so page `0`
    is silently omitted; `None` and `0` behave differently from a formatting standpoint
    (`ask.py:138-139`).
17. **Missing verifier row = ok.** A claim absent from a non-empty `verifier.jsonl` passes the
    filter and is cited with `verdict="ok"` (`ask.py:208`, `:355`). This is the normal state
    after a partial rebuild; treat it as trusted.
18. **Empty verifier file = no filtering.** `not self.verdicts` is true for `{}`, so every
    claim is kept even without `--include-unverified` (`ask.py:207`).
19. **`include_unverified` disables the filter.** It does not mean "ok + weak"; `no` claims are
    cited too, with their badge (`ask.py:203-209`).
20. **Duration parsing corner cases.** `"1.48 hours"` parses as 1.48 hours; `"2-3 days"` loses
    the `2`; `months` is 730 hours and `years` 8760, so 12 months equals 1 year exactly; the
    `working` flag never changes the hours; labels keep the printed case (`"Six years"`) but
    lower-case the unit (`ask.py:81-104`, `:359-373`).
21. **Topic matching is lexical, not morphological.** `retain` matches, `retained` does not;
    `transfer` and `transfers` are listed separately; a two-word phrase needs adjacent tokens;
    two matched topics return `None` and drop the claim from the report (`ask.py:108-120`,
    `:376-388`).
22. **Tensions depend on `limit`.** They are derived from the returned citations, so a smaller
    `-n` can remove the document that created the disagreement, and `--include-unverified` can
    add one (`ask.py:439`).
23. **Tension values ordering.** Buckets iterate in topic string order; inside a topic, hour
    values ascending; inside one hour value, citation order. The `reason` counts distinct hour
    values and distinct documents over the whole topic bucket, not per value
    (`ask.py:406-430`).
24. **Float grouping.** Two durations group only if their `hours` doubles are exactly equal
    (`48` vs `48.0` equal; `72` vs `72.0000001` not). Grouping on the label string would
    differ (`ask.py:407-409`).
25. **`limit <= 0`.** `limit=0` returns nothing; a negative limit returns one citation because
    the slice and the `>=` comparison both invert. The CLI accepts any integer
    (`ask.py:328-336`, `cli.py:601`).
26. **Half-even weight rounding.** `max(1, int(round(weight)))` would give `2` for a weight of
    `2.5`; irrelevant with the shipped weights, relevant if they are edited (`ask.py:226`).
27. **JSONL line splitting.** `str.splitlines()` also splits on U+2028, U+2029, U+0085, U+000B,
    U+000C, U+001C–U+001E. A JSON string containing a raw U+2028 becomes two lines and fails to
    parse; a Rust `lines()` (splits on `\n`, strips one `\r`) would accept it. Blank-line
    skipping uses Unicode `strip()` (`store.py:154-158`).
28. **`text()` decoding.** `errors="ignore"` drops invalid bytes; char offsets recorded at
    ingest then no longer point where they did. The `ask` path never reads text, so this only
    matters to a port that validates quotes itself (`store.py:451`).
29. **`vectors_header` on an empty file.** `json.loads(handle.readline())` with `""` raises
    `JSONDecodeError`; not caught (`store.py:443-447`).
30. **Wrong vector dimension is fatal.** `cosine` raises, `semantic_ranking` does not catch,
    `ask` does not catch: the command aborts, contradicting the module's promise that a missing
    or mismatched model never turns a deterministic answer into an error (`vector.py:35-37`,
    `ask.py:269-273`, `cli.py:565-573`).
31. **`documents.jsonl` is optional.** Without it, a citation still exists with `title` from
    `context.source` (verified: `"src-D3"`) and `url` `""`; a row lacking `title` triggers the
    same fallback. A row lacking `doc_id` raises `KeyError` at corpus construction
    (`ask.py:210`).
32. **`Answer.documents` is a list of ids, not documents.** It is built from citations, so it
    reflects ranking order and the `limit` (`ask.py:158-164`).
33. **`render_text` quote truncation is 400 code points**, no ellipsis, and only when the quote
    is truthy; a `None` quote is skipped rather than printed (`ask.py:453-454`).
34. **`title` field of the index can be empty** when `context.source` is missing, even if
    `documents.jsonl` has a title — the index never consults `documents.jsonl`
    (`ask.py:173-183`).

---

## Suspected defects

Described, not corrected. Each is observable in the reference.

1. **Deduplication can starve the result list.** The window `ranked[:max(limit*4, limit)]` is
   cut before duplicates are removed, and `continue` does not fetch more candidates
   (`ask.py:326-338`). Verified: 9 claims with statement `"Retention period is six years."`
   plus one distinct claim, `limit=2` → window 8 → one citation returned, although the ninth
   candidate (index 8) is a different statement. A KB with many near-duplicate claims returns
   fewer than `limit` citations while valid matches exist.
2. **A claim missing from `verifier.jsonl` is treated as verified.** `self.verdicts.get(claim_id, "ok")`
   (`ask.py:208`) and `_citation`'s `"ok"` default (`ask.py:355`) mean a partial or stale
   verifier file silently promotes unverified claims into answers, with a green `ok` badge.
   Only an entirely empty map disables filtering, which produces the same result with a CLI
   warning.
3. **The indexed "title" is not the document title.** `_claim_text` uses
   `claim.context.source` (`ask.py:181`), while `_citation` prefers `documents.jsonl.title`
   (`ask.py:348`). A KB whose document titles differ from the compiler's `context.source`
   ranks by a string the citation never displays. In the pilot KB the two coincide.
4. **Only the first evidence quote is cited and inspected for tensions.** `_citation` reads
   `evidence[0]` (`ask.py:341-353`) and `find_tensions` joins `citation.statement` with
   `citation.quote` (`ask.py:395-398`), so a deadline present only in the second quote is
   indexed for BM25 but can never create a tension and is never shown. Claim `…-0026` in the
   pilot KB has its "30 minutes" in both quotes; a one-quote-only claim would be invisible.
5. **A semantic embedding is computed and then discarded for stopword-only questions.** `ask`
   guards on `tokens(question)` (`ask.py:437`), `search` guards on `_content(question)`
   (`ask.py:283-285`). With vectors present, `"the of and"` calls the model once and returns
   `[]`.
6. **Wrong-dimensional vectors crash the command.** `cosine` raises `ValueError`
   (`vector.py:35-37`); `semantic_ranking` (`ask.py:269-273`) and `ask` do not catch it; the
   CLI's `try` only wraps enabling (`cli.py:580-594`), not querying. The module docstring
   promises the opposite (`cli.py:571-573`).
7. **"working days" are calendar days.** `UNIT_HOURS` maps `working hour(s)` to 1 but the
   `working` group never scales a day/week (`ask.py:81-94`, `:371`). `"3 working days"` →
   72 hours, identical to `"3 days"`; a report cannot distinguish the two except by label.
8. **A month is 730 hours, a year 8760.** `ask.py:90-93`. This is 30.4167 days and 365 days;
   `12 months` and `1 year` are equal, but `6 months` (4380) and `0.5 years` cannot be
   expressed, and `1 month` vs `30 days` (730 vs 720) differ by 10 hours. Any port must copy
   these constants even though they are not calendar-exact.
9. **`durations` amount parsing is locale-blind.** `float(amount.replace(",", "."))`
   (`ask.py:366`) turns the English `"1,5"` into 1.5 and leaves `"1.5"` alone, but a
   continental thousands separator such as `"1.000 hours"` becomes 1.0 hour, and `"1.48 hours"`
   (a sentence number followed by a unit, or a version) becomes 1.48 (`ask.py:101-104`).
   Also `"2-3 days"` silently keeps only `3`.
10. **SPARQL guard is a substring test.** `sparql.py:47-52`: `"created"`, `"loaded"`,
    `"payload"`, `"clearance"`, an IRI containing `DROP`, or a string literal containing
    `DELETE` are rejected as mutations; conversely the guard does not parse the query, so any
    future rdflib support for an update verb not in the list would pass. Message names the
    first matching keyword in list order.
11. **`execute_sparql` returns a tuple but is annotated `list[dict]`.** `sparql.py:23` vs
    `sparql.py:70`; every caller unpacks two values, so the annotation is wrong rather than the
    code. A Rust port should define an explicit `(rows, vars)` result type.
12. **`vectors_header()` raises on an empty `vectors.jsonl`.** `json.loads("")` in
    `store.py:447`; the caller (`embedder_for`, `vector.py:85`) is reached only when
    `vectors()` is non-empty, so the crash is latent, but an empty file with `--semantic`
    reports the exception text as "semantic ranking unavailable" only because the CLI catches
    everything.
13. **`KnowledgeBase.manifest()` silently substitutes `{}` for a missing manifest.** The CLI
    then treats `languages` as undeclared and allows fusion (`supports({}) == True`,
    `vector.py:31`), i.e. an English-only model may be applied to a KB whose language is
    unknown. This is a deliberate choice documented at `vector.py:23-24`, but it is a silent
    one.
14. **`_corpus` warning text is emitted for an empty verifier file too.** `cli.py:556-559`
    says `no verifier.jsonl`; the condition is `not kb.verifier()`, which is also true when the
    file exists and is empty (`store.py:151-158`). The diagnosis is wrong in that case.
