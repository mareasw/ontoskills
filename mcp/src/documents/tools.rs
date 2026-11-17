//! The three document tools, as MCP handlers.
//!
//! They are kept out of `main.rs` for one reason: the protocol layer should
//! describe tools and route requests, and the document layer should own what a
//! document answer looks like. A test can call [`ask`], [`claim`] and [`query`]
//! directly, without a JSON-RPC session.
//!
//! Every handler returns the pair `(structured, compact_text)` that
//! `main::build_response` wraps. The structured form is the contract; the text
//! is the same answer for a client that only reads text, and it is rendered from
//! the same values so the two cannot disagree.

use std::path::PathBuf;

use serde_json::{Value, json};

use super::kb::{Kb, ROOT_ENV};
use super::rank::{self, Citation, Tension};
use super::sparql::{self, GraphStore};
use super::text::norm;

/// Resolve the knowledge base: the argument, else `ONTOSKILLS_KB_ROOT`.
///
/// A KB root is a directory of customer documents, so it is never embedded in
/// the binary the way the skills catalog is: the same server serves whichever
/// knowledge base the caller names.
fn knowledge_base(arguments: &Value) -> Result<std::sync::Arc<Kb>, String> {
    let root = arguments
        .get("kb")
        .and_then(Value::as_str)
        .map(PathBuf::from)
        .or_else(|| std::env::var_os(ROOT_ENV).map(PathBuf::from))
        .ok_or_else(|| format!("no knowledge base given: pass `kb` or set {ROOT_ENV}"))?;
    Kb::cached(&root).map_err(|error| error.to_string())
}

/// `documents_ask`: the ranked citations for a question.
pub fn ask(arguments: &Value) -> Result<(Value, String), String> {
    let question = arguments
        .get("q")
        .and_then(Value::as_str)
        .ok_or_else(|| "Missing required string field 'q'".to_string())?;
    let limit = arguments.get("k").and_then(Value::as_u64).unwrap_or(10) as usize;
    let include_unverified = arguments
        .get("include_unverified")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    let kb = knowledge_base(arguments)?;
    let answer = rank::ask(&kb, question, limit, include_unverified);
    let structured = json!({
        "question": answer.question,
        "documents": answer.documents(),
        "claims_searched": answer.searched,
        "citations": answer.citations.iter().map(citation_json).collect::<Vec<_>>(),
        "tensions": answer.tensions.iter().map(tension_json).collect::<Vec<_>>(),
    });
    let text = render_answer(&answer.citations, &answer.tensions);
    Ok((structured, text))
}

/// `documents_claim`: one claim with all its evidence and the verifier's reasons.
pub fn claim(arguments: &Value) -> Result<(Value, String), String> {
    let claim_id = arguments
        .get("claim_id")
        .and_then(Value::as_str)
        .ok_or_else(|| "Missing required string field 'claim_id'".to_string())?;
    let kb = knowledge_base(arguments)?;
    let claim = kb.claim(claim_id).ok_or_else(|| {
        format!("claim not found: {claim_id}; `documents_ask` returns the ids this knowledge base carries")
    })?;
    let verdict = kb.claim_verdict(claim_id);
    let document = kb.document(&claim.doc_id);
    // The quote is checked against the document on the way out, with the rule
    // the compiler's verifier uses: the offsets index the normalised text. It
    // costs one file read and turns the locator from a claim into a fact.
    let source = kb.text(&claim.doc_id).ok().map(|text| norm(&text));

    let structured = json!({
        "claim_id": claim.claim_id,
        "doc_id": claim.doc_id,
        "statement": claim.statement,
        "modality": claim.modality,
        "actor": claim.actor,
        "deadline": claim.deadline,
        "conditions": claim.conditions,
        "conflicts_with": claim.conflicts_with,
        "evidence": claim.evidence.iter().map(|item| json!({
            "role": item.role,
            "quote": item.quote,
            "locator": locator_json(&item.locator),
            "quote_at_offsets": quote_at_offsets(
                source.as_deref(),
                &item.quote,
                item.locator.char_start,
                item.locator.char_end,
            ),
        })).collect::<Vec<_>>(),
        "verdict": {
            "verdict": kb.verdict(claim_id),
            "reasons": verdict.map(|row| row.reasons.clone()).unwrap_or_default(),
            "notes": verdict.map(|row| row.notes.clone()).unwrap_or_default(),
        },
        "document": document.map(|row| json!({
            "doc_id": row.doc_id,
            "title": row.title,
            "url": row.url,
            "doc_type": row.doc_type,
            "version": row.version,
            "licence": row.licence,
            "sha256": row.sha256,
        })),
    });

    let mut lines = vec![
        format!("{}  [{}]", claim.claim_id, kb.verdict(claim_id)),
        claim.statement.clone(),
        String::new(),
    ];
    if !claim.conditions.is_empty() {
        lines.push(format!("conditions: {}", claim.conditions.join("; ")));
    }
    if !claim.actor.is_empty() {
        lines.push(format!("actor: {}", claim.actor));
    }
    for (index, item) in claim.evidence.iter().enumerate() {
        lines.push(format!(
            "evidence[{}] ({}): \"{}\"",
            index,
            if item.role.is_empty() { "supports" } else { &item.role },
            item.quote
        ));
        lines.push(format!("    source: {}", locator_label(&item.locator, document)));
        match quote_at_offsets(
            source.as_deref(),
            &item.quote,
            item.locator.char_start,
            item.locator.char_end,
        ) {
            Some(true) => lines.push("    verified: the quote is at its offsets".to_string()),
            Some(false) => lines.push(
                "    NOT VERIFIED: the quote is not the text at those offsets".to_string(),
            ),
            None => lines.push("    verified: not checked (no text or no offsets)".to_string()),
        }
    }
    if let Some(verdict) = verdict {
        if !verdict.reasons.is_empty() {
            lines.push(format!("verifier reasons: {}", verdict.reasons.join("; ")));
        }
        if !verdict.notes.is_empty() {
            lines.push(format!("verifier notes: {}", verdict.notes.join("; ")));
        }
    }
    if !claim.conflicts_with.is_empty() {
        lines.push(format!("conflicts with: {}", claim.conflicts_with.join(", ")));
    }
    Ok((structured, lines.join("\n")))
}

/// `documents_query`: a read-only `SELECT` or `ASK` over the graph.
pub fn query(arguments: &Value) -> Result<(Value, String), String> {
    let sparql = arguments
        .get("sparql")
        .and_then(Value::as_str)
        .ok_or_else(|| "Missing required string field 'sparql'".to_string())?;
    // The guard runs before the graph is opened, not after: a refused mutation
    // must not cost the caller the parse of sixteen megabytes of Turtle, and a
    // caller that typed `DELETE` learns it in a millisecond.
    sparql::check_read_only(sparql).map_err(|error| format!("[{}] {error}", error.code()))?;
    let kb = knowledge_base(arguments)?;
    let store = GraphStore::cached(&kb).map_err(|error| error.to_string())?;
    let result = store.query(sparql).map_err(|error| {
        // The code prefix is what a client branches on; the message says what to
        // do. `sparql rows` and `sparql timeout` both name their cap.
        format!("[{}] {error}", error.code())
    })?;

    let structured = json!({
        "form": if result.boolean.is_some() { "ask" } else { "select" },
        "variables": result.variables,
        "rows": result.rows,
        "boolean": result.boolean,
        "triples": store.triples(),
    });

    let mut lines = Vec::new();
    if let Some(boolean) = result.boolean {
        lines.push(format!("ASK: {boolean}"));
    } else {
        lines.push(result.variables.join("\t"));
        for row in &result.rows {
            lines.push(
                row.iter()
                    .map(|cell| cell.clone().unwrap_or_default())
                    .collect::<Vec<_>>()
                    .join("\t"),
            );
        }
        lines.push(format!("{} row(s)", result.rows.len()));
    }
    Ok((structured, lines.join("\n")))
}

fn citation_json(citation: &Citation) -> Value {
    json!({
        "claim_id": citation.claim_id,
        "doc_id": citation.doc_id,
        "title": citation.title,
        "statement": citation.statement,
        "quote": citation.quote,
        "locator": {
            "section_path": citation.section_path,
            "char_start": citation.char_start,
            "char_end": citation.char_end,
            "page": citation.page,
            "url": citation.url,
        },
        "score": citation.score,
        "verdict": citation.verdict,
    })
}

fn tension_json(tension: &Tension) -> Value {
    json!({
        "topic": tension.topic,
        "values": tension.values,
        "reason": tension.reason,
    })
}

/// Whether `quote` is the text between `start` and `end` of the normalised
/// source. `None` when it cannot be checked: no text file, no offsets, or an
/// offset past the end — a reader must not read "cannot check" as "wrong".
fn quote_at_offsets(
    source: Option<&str>,
    quote: &str,
    start: Option<i64>,
    end: Option<i64>,
) -> Option<bool> {
    let source = source?;
    let (start, end) = (start?, end?);
    if start < 0 || end < start {
        return None;
    }
    let length = usize::try_from(end - start).ok()?;
    let slice: String = source.chars().skip(start as usize).take(length).collect();
    if slice.chars().count() != length {
        return None;
    }
    Some(slice == norm(quote))
}

fn locator_json(locator: &super::kb::Locator) -> Value {
    json!({
        "kind": locator.kind,
        "section_path": locator.section_path,
        "char_start": locator.char_start,
        "char_end": locator.char_end,
        "page": locator.page,
        "url": locator.url,
    })
}

fn locator_label(locator: &super::kb::Locator, document: Option<&super::kb::Document>) -> String {
    let mut bits = Vec::new();
    if let Some(document) = document {
        if !document.title.is_empty() {
            bits.push(document.title.clone());
        }
    }
    if let Some(page) = locator.page.filter(|page| *page != 0) {
        bits.push(format!("p. {page}"));
    }
    if !locator.section_path.is_empty() {
        bits.push(locator.section_path.join(" > "));
    }
    let url = if !locator.url.is_empty() {
        Some(locator.url.as_str())
    } else {
        document.map(|row| row.url.as_str()).filter(|url| !url.is_empty())
    };
    if let Some(url) = url {
        bits.push(url.to_string());
    }
    bits.join(", ")
}

/// The plain-text form of an answer, rendered from the same citations the JSON
/// carries. Grouped by document, in first-citation order, as `ontocore ask`
/// prints it, so a reader switching between the two sees the same shape.
fn render_answer(citations: &[Citation], tensions: &[Tension]) -> String {
    let mut lines = Vec::new();
    let mut groups: Vec<(&str, Vec<&Citation>)> = Vec::new();
    for citation in citations {
        match groups.iter_mut().find(|(doc_id, _)| *doc_id == citation.doc_id) {
            Some((_, group)) => group.push(citation),
            None => groups.push((citation.doc_id.as_str(), vec![citation])),
        }
    }
    for (doc_id, group) in &groups {
        lines.push(format!(
            "== {}  [{doc_id}]  ({} claim(s))",
            group[0].title,
            group.len()
        ));
        for citation in group {
            let mark = if citation.verdict == "ok" {
                String::new()
            } else {
                format!("[{}] ", citation.verdict)
            };
            lines.push(format!("  {}  {mark}{}", citation.claim_id, citation.statement));
            lines.push(format!("      source: {}", citation.label()));
            if !citation.quote.is_empty() {
                let quote: String = citation.quote.chars().take(400).collect();
                lines.push(format!("      quote: \"{quote}\""));
            }
        }
        lines.push(String::new());
    }
    if !tensions.is_empty() {
        lines.push("Tensions in the corpus:".to_string());
        for tension in tensions {
            lines.push(format!("  {}: {}", tension.topic, tension.reason));
            for (value, claim) in &tension.values {
                lines.push(format!("    - {value}: {claim}"));
            }
        }
        lines.push(String::new());
    }
    match groups.len() {
        0 => lines.push("No claim in this knowledge base answers the question.".to_string()),
        count => lines.push(format!(
            "Documents answering: {count} ({})",
            groups
                .iter()
                .map(|(doc_id, _)| *doc_id)
                .collect::<Vec<_>>()
                .join(", ")
        )),
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    fn fixture() -> PathBuf {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/documents/kb")
    }

    fn arguments(extra: Value) -> Value {
        let mut value = json!({ "kb": fixture().to_string_lossy() });
        for (key, item) in extra.as_object().expect("object") {
            value[key] = item.clone();
        }
        value
    }

    #[test]
    fn ask_returns_citations_documents_and_text() {
        let (structured, text) = ask(&arguments(json!({
            "q": "What are the default size limits for file uploads?"
        })))
        .expect("ask works");
        let citations = structured["citations"].as_array().expect("citations");
        assert!(!citations.is_empty());
        let first = &citations[0];
        assert!(first["claim_id"].as_str().unwrap().len() > 10);
        assert!(first["locator"]["char_start"].as_i64().unwrap() >= 0);
        assert!(
            first["locator"]["char_end"].as_i64().unwrap()
                > first["locator"]["char_start"].as_i64().unwrap()
        );
        assert!(!structured["documents"].as_array().unwrap().is_empty());
        assert!(text.contains("Documents answering:"));
    }

    #[test]
    fn ask_honours_k_and_the_unverified_switch() {
        let question = "What are the default size limits for file uploads?";
        let (structured, _) = ask(&arguments(json!({ "q": question, "k": 2 })))
            .expect("ask works");
        assert_eq!(structured["citations"].as_array().unwrap().len(), 2);
        let (all, _) = ask(&arguments(json!({
            "q": question,
            "k": 200,
            "include_unverified": true
        })))
        .expect("ask works");
        let verdicts: Vec<&str> = all["citations"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|citation| citation["verdict"].as_str())
            .collect();
        assert!(verdicts.len() >= 1);
    }

    #[test]
    fn ask_without_a_question_is_an_error_the_client_can_read() {
        let error = ask(&arguments(json!({}))).expect_err("q is required");
        assert!(error.contains("'q'"));
    }

    #[test]
    fn claim_returns_every_evidence_item_and_the_reasons() {
        let (structured, text) = claim(&arguments(json!({
            "claim_id": "dsid_020bac2fb6ac4de28d5afb63e39a0c10-0001"
        })))
        .expect("claim works");
        assert_eq!(structured["claim_id"], "dsid_020bac2fb6ac4de28d5afb63e39a0c10-0001");
        assert!(!structured["evidence"].as_array().unwrap().is_empty());
        assert_eq!(structured["verdict"]["verdict"], "ok");
        assert!(structured["verdict"]["reasons"].is_array());
        assert_eq!(structured["evidence"][0]["quote_at_offsets"], true);
        assert!(text.contains("evidence[0]"));
        assert!(text.contains("the quote is at its offsets"));
    }

    #[test]
    fn an_unknown_claim_is_named_in_the_error() {
        let error = claim(&arguments(json!({ "claim_id": "nope-0000" }))).expect_err("unknown");
        assert!(error.contains("nope-0000"));
    }

    #[test]
    fn query_answers_a_select_and_an_ask() {
        let (structured, text) = query(&arguments(json!({
            "sparql": "SELECT ?s WHERE { ?s a doc:Document }"
        })))
        .expect("select works");
        assert_eq!(structured["form"], "select");
        assert_eq!(structured["rows"].as_array().unwrap().len(), 3);
        assert!(structured["triples"].as_u64().unwrap() > 100);
        assert!(text.contains("row(s)"));

        let (structured, _) = query(&arguments(json!({
            "sparql": "ASK { ?s a doc:Document }"
        })))
        .expect("ask works");
        assert_eq!(structured["boolean"], true);
    }

    #[test]
    fn a_mutation_is_refused_before_the_graph_is_opened() {
        // A knowledge base whose graph is missing: the guard must answer first,
        // otherwise a caller who typed `DELETE` waits for a parse that then
        // fails for an unrelated reason and never learns what went wrong.
        let root = std::env::temp_dir().join(format!("ontomcp-no-graph-{}", std::process::id()));
        std::fs::create_dir_all(&root).expect("temp dir");
        std::fs::write(root.join("claims.jsonl"), "{}\n").expect("claims");
        let arguments = json!({
            "kb": root.to_string_lossy(),
            "sparql": "DELETE WHERE { ?s ?p ?o }"
        });
        let error = query(&arguments).expect_err("mutation");
        assert!(error.contains("DELETE"), "{error}");
        assert!(error.contains("sparql_guard"), "{error}");
        let select = json!({
            "kb": root.to_string_lossy(),
            "sparql": "SELECT ?s WHERE { ?s ?p ?o }"
        });
        let error = query(&select).expect_err("no graph");
        assert!(!error.contains("sparql_guard"), "{error}");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_mutation_is_refused_with_the_keyword_named() {
        let error = query(&arguments(json!({
            "sparql": "DELETE WHERE { ?s ?p ?o }"
        })))
        .expect_err("mutation");
        assert!(error.contains("DELETE"), "{error}");
        assert!(error.contains("sparql_guard"), "{error}");
    }
}
