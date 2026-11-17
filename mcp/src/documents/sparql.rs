//! Read-only SPARQL over the graph `ontocore documents` writes.
//!
//! The graph is the reason the layer exists: a vector store cannot answer
//! "which obligations in the annex contradict the master agreement". This module
//! makes that question reachable from the MCP without giving an agent a write
//! path into a customer's knowledge base.
//!
//! Three decisions are worth stating because they are not visible in the code's
//! shape:
//!
//! * **The guard is lexical, the syntax check is the real parser.** oxigraph
//!   0.5.6 parses a query into `PreparedSparqlQuery`, but the `spargebra::Query`
//!   it wraps is private and there is no accessor for the query form, so the
//!   form cannot be read from the parsed value. [`check_read_only`] therefore
//!   walks its own token stream — one that skips comments, strings, IRIs,
//!   variables and prefixed names — to find the first keyword and any
//!   `SERVICE`/update keyword, then hands the text to `SparqlEvaluator` so a
//!   syntactically broken query is a [`SparqlError::Parse`] and not a panic. The
//!   tokenizer is what makes `FILTER(CONTAINS(?o, "delete"))` legal: a substring
//!   guard cannot tell a literal from an update keyword, and refusing that
//!   query is the defect this replaces.
//! * **The 2 s cap is real, not a verdict taken after the fact.** oxigraph
//!   0.5.6 exposes `CancellationToken`, so a watchdog thread cancels the
//!   evaluation at the deadline and the cancellation is reported as
//!   [`SparqlError::Timeout`]. Cancellation is cooperative: it is checked
//!   between evaluation steps, so one indivisible step may overrun the deadline
//!   by a little; the elapsed time is also checked at the end, which turns an
//!   overrun into a `Timeout` instead of a late answer. The row cap is exact: the
//!   table is abandoned as soon as a 2001st solution exists.
//! * **The vocabulary is inlined, and a mismatch is an error.** The served
//!   version is `core/src/specs/documents.ttl` (documents 1.0.0), embedded at
//!   build time. Every `doc:` term the graph actually uses is compared against
//!   it; an unknown term names the version skew instead of returning a
//!   plausible-looking empty answer.
//!
//! The store is in memory (`Store::new` + `load_from_reader`) and `graph.ttl` is
//! opened for reading only: this module cannot write a knowledge base, and with
//! no `http-client` feature and `SERVICE` refused, it cannot reach the network
//! either.

use std::collections::{BTreeSet, HashSet};
use std::fmt;
use std::fs::{self, File};
use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime};

use oxigraph::io::RdfFormat;
use oxigraph::model::{NamedOrBlankNode, Term};
use oxigraph::sparql::{CancellationToken, QueryEvaluationError, QueryResults, SparqlEvaluator};
use oxigraph::store::Store;

use super::kb::Kb;

/// The namespace the layer is served at; the prefix `doc` is bound to it for
/// every query so a caller can write `doc:Claim` without a `PREFIX` line.
pub const DOC_NAMESPACE: &str = "https://ontoskills.sh/ontology/documents#";

/// The vocabulary this binary serves, inlined from the spec the compiler uses.
///
/// A relative `include_str!` is deliberate: the path is checked by the compiler,
/// so a build that moves the spec without updating this line fails to compile
/// rather than shipping a server with the wrong vocabulary.
const VOCABULARY: &str = include_str!("../../../core/src/specs/documents.ttl");

/// The most rows one answer may carry. Named in the error when it is hit,
/// because an agent that receives silence learns the graph is empty.
const MAX_ROWS: usize = 2000;

/// The wall-clock budget for one query, cancelled and named in the error.
const TIME_BUDGET: Duration = Duration::from_secs(2);

/// Prefixes every query gets for free. `doc` is the layer's own namespace; the
/// rest are the W3C vocabularies the graph's TBox already uses, so an agent can
/// ask about `owl:Class` without restating them.
const PREFIXES: &[(&str, &str)] = &[
    ("doc", DOC_NAMESPACE),
    ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("owl", "http://www.w3.org/2002/07/owl#"),
    ("xsd", "http://www.w3.org/2001/XMLSchema#"),
];

/// The only two query forms the tool answers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueryForm {
    Select,
    Ask,
}

/// The bound rows of a `SELECT`, or the single boolean of an `ASK`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QueryResult {
    /// Variable names in the order the engine returns them, without `?`.
    pub variables: Vec<String>,
    /// One row per solution; `None` is a variable unbound in that row. A cell is
    /// the term in N-Triples form (`<iri>`, `"literal"@en`, `_:b0`), so an IRI
    /// and a literal with the same text cannot be confused.
    pub rows: Vec<Vec<Option<String>>>,
    /// `Some` for an `ASK`: `variables` is empty and `rows` holds one row with
    /// the single cell `"true"` or `"false"`.
    pub boolean: Option<bool>,
}

/// Everything that can stop a query, each with the fact the caller needs to act
/// on. The variants carry the failure's own vocabulary — a keyword, a term, a
/// cap — because "query failed" is not something an agent can repair.
#[derive(Debug)]
pub enum SparqlError {
    /// A write or federated keyword was found; the keyword is named.
    Guard { keyword: String, message: String },
    /// The query is not valid SPARQL, or is not SELECT/ASK.
    Parse(String),
    /// `graph.ttl` could not be opened.
    Io(PathBuf, std::io::Error),
    /// The graph or the embedded vocabulary could not be loaded.
    Load(PathBuf, String),
    /// The graph uses a `doc:` term the served vocabulary does not define.
    Vocabulary(String),
    /// The answer has more rows than the cap.
    Rows(usize),
    /// The answer took longer than the wall-clock budget.
    Timeout,
    /// Evaluation failed for a reason other than the two caps.
    Evaluation(String),
}

impl SparqlError {
    /// A stable code for the MCP layer; the message is for humans, this is for
    /// a client that branches.
    pub fn code(&self) -> &'static str {
        match self {
            SparqlError::Guard { .. } => "sparql_guard",
            SparqlError::Parse(_) => "sparql_parse",
            SparqlError::Io(..) => "sparql_io",
            SparqlError::Load(..) => "sparql_load",
            SparqlError::Vocabulary(_) => "sparql_vocabulary",
            SparqlError::Rows(_) => "sparql_rows",
            SparqlError::Timeout => "sparql_timeout",
            SparqlError::Evaluation(_) => "sparql_evaluation",
        }
    }
}

impl fmt::Display for SparqlError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SparqlError::Guard { keyword, message } => write!(f, "{keyword}: {message}"),
            SparqlError::Parse(message) => write!(
                f,
                "SPARQL syntax error: {message}; only SELECT and ASK queries are accepted"
            ),
            SparqlError::Io(path, error) => write!(f, "{}: {error}", path.display()),
            SparqlError::Load(path, message) => write!(
                f,
                "{}: {message}; the file must be the Turtle `ontocore documents ingest` writes",
                path.display()
            ),
            SparqlError::Vocabulary(message) => f.write_str(message),
            SparqlError::Rows(cap) => write!(
                f,
                "the query returns more than {cap} rows (cap: {cap} rows); add a LIMIT or narrow the pattern"
            ),
            SparqlError::Timeout => write!(
                f,
                "the query exceeded the {} s budget; add a LIMIT, narrow the pattern, or ask for less",
                TIME_BUDGET.as_secs()
            ),
            SparqlError::Evaluation(message) => {
                write!(f, "SPARQL evaluation failed: {message}")
            }
        }
    }
}

impl std::error::Error for SparqlError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            SparqlError::Io(_, error) => Some(error),
            _ => None,
        }
    }
}

/// `graph.ttl` parsed once, kept in memory, queried many times.
///
/// Parsing 16 MB of Turtle costs one to two seconds. That cost belongs to the
/// first query of a knowledge base, not to every query, which is why the caller
/// is expected to hold the `Arc` from [`GraphStore::cached`].
pub struct GraphStore {
    store: Store,
    triples: usize,
}

// `Store` has no `Debug`, and printing a whole graph is not something a log
// line should do; the triple count is the useful part.
impl fmt::Debug for GraphStore {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("GraphStore")
            .field("triples", &self.triples)
            .finish_non_exhaustive()
    }
}

impl GraphStore {
    /// Parse `kb.graph_path()` and validate the vocabulary.
    // Not called yet: `main.rs` mounts `documents_query` in a separate change.
    // The tests exercise it here, so the attribute is about the binary build,
    // not about the function being speculative.
    #[allow(dead_code)]
    pub fn open(kb: &Kb) -> Result<GraphStore, SparqlError> {
        GraphStore::open_path(&kb.graph_path())
    }

    /// The same, for a caller that already has the graph's path.
    pub fn open_path(graph: &Path) -> Result<GraphStore, SparqlError> {
        let file =
            File::open(graph).map_err(|error| SparqlError::Io(graph.to_path_buf(), error))?;
        let store = Store::new()
            .map_err(|error| SparqlError::Load(graph.to_path_buf(), error.to_string()))?;
        // In-memory store plus a read-only handle: no line in this module can
        // write to `graph.ttl`, so a query cannot mutate a customer artifact.
        store
            .load_from_reader(RdfFormat::Turtle, BufReader::new(file))
            .map_err(|error| SparqlError::Load(graph.to_path_buf(), error.to_string()))?;
        validate_vocabulary(&store, graph)?;
        let triples = store
            .len()
            .map_err(|error| SparqlError::Load(graph.to_path_buf(), error.to_string()))?;
        Ok(GraphStore { store, triples })
    }

    /// The process-wide cache, invalidated by the graph's mtime and size.
    ///
    /// The size is part of the key because a filesystem can preserve an mtime
    /// across a rewrite with a coarse clock; a changed length is always visible.
    /// Two concurrent misses may parse the graph twice and the last one wins;
    /// that is cheaper than holding a lock for the second the parse takes.
    pub fn cached(kb: &Kb) -> Result<Arc<GraphStore>, SparqlError> {
        let path = kb.graph_path();
        let metadata = fs::metadata(&path).map_err(|error| SparqlError::Io(path.clone(), error))?;
        let modified = metadata.modified().ok();
        let len = metadata.len();

        {
            let slot = cache_slot()
                .lock()
                .unwrap_or_else(|poison| poison.into_inner());
            if let Some(entry) = slot.as_ref() {
                if entry.path == path && entry.modified == modified && entry.len == len {
                    return Ok(Arc::clone(&entry.store));
                }
            }
        }

        let store = Arc::new(GraphStore::open_path(&path)?);
        let mut slot = cache_slot()
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
        *slot = Some(Cached {
            path,
            modified,
            len,
            store: Arc::clone(&store),
        });
        Ok(store)
    }

    /// Number of triples loaded; evidence that the file was read, not skipped.
    pub fn triples(&self) -> usize {
        self.triples
    }

    /// Execute a query already validated by the guard.
    ///
    /// Re-guarding inside is deliberate: `query` is public and a caller holding
    /// a `GraphStore` must not be able to skip the check by not calling
    /// [`check_read_only`] first.
    pub fn query(&self, sparql: &str) -> Result<QueryResult, SparqlError> {
        let form = guard(sparql)?;
        let started = Instant::now();
        let watchdog = Watchdog::start();

        let evaluator = evaluator()?;
        let prepared = evaluator
            .with_cancellation_token(watchdog.token().clone())
            .parse_query(sparql)
            .map_err(|error| SparqlError::Parse(error.to_string()))?;
        let results = prepared
            .on_store(&self.store)
            .execute()
            .map_err(evaluation_error)?;

        let result = match results {
            QueryResults::Boolean(value) => {
                if form != QueryForm::Ask {
                    return Err(SparqlError::Evaluation(
                        "a SELECT query produced a boolean result".to_string(),
                    ));
                }
                QueryResult {
                    variables: Vec::new(),
                    rows: vec![vec![Some(value.to_string())]],
                    boolean: Some(value),
                }
            }
            QueryResults::Solutions(solutions) => {
                let variables = solutions
                    .variables()
                    .iter()
                    .map(|variable| variable.as_str().to_string())
                    .collect();
                let mut rows = Vec::new();
                for solution in solutions {
                    // A 2001st row is the cap being hit, not a row to return.
                    if rows.len() >= MAX_ROWS {
                        return Err(SparqlError::Rows(MAX_ROWS));
                    }
                    if started.elapsed() > TIME_BUDGET {
                        return Err(SparqlError::Timeout);
                    }
                    let solution = solution.map_err(evaluation_error)?;
                    rows.push(
                        solution
                            .values()
                            .iter()
                            .map(|value| value.as_ref().map(|term| term.to_string()))
                            .collect(),
                    );
                }
                QueryResult {
                    variables,
                    rows,
                    boolean: None,
                }
            }
            // The guard admits only SELECT and ASK, so a graph result is a
            // server bug rather than a user error; say so instead of guessing.
            QueryResults::Graph(_) => {
                return Err(SparqlError::Evaluation(
                    "a SELECT/ASK query produced a graph result".to_string(),
                ));
            }
        };

        watchdog.stop();
        if started.elapsed() > TIME_BUDGET {
            return Err(SparqlError::Timeout);
        }
        Ok(result)
    }
}

/// An evaluator with the built-in prefixes already bound.
///
/// The prefix IRIs are constants in this file, so a failure here is a server
/// bug, not a user error; it is still reported rather than unwrapped.
fn evaluator() -> Result<SparqlEvaluator, SparqlError> {
    let mut evaluator = SparqlEvaluator::new();
    for (name, iri) in PREFIXES {
        evaluator = evaluator
            .with_prefix(*name, *iri)
            .map_err(|error| SparqlError::Evaluation(format!("built-in prefix {name}: {error}")))?;
    }
    Ok(evaluator)
}

/// The guard, exposed so a test can check the refusal without a graph.
///
/// It does two things in order: the tokenizer decides the form and finds
/// forbidden keywords, then the real parser checks the syntax. A string that
/// passes this function is a valid SELECT or ASK.
// Not called yet: `main.rs` validates the argument before calling `query`.
#[allow(dead_code)]
pub fn check_read_only(sparql: &str) -> Result<QueryForm, SparqlError> {
    let form = guard(sparql)?;
    evaluator()?
        .parse_query(sparql)
        .map(|_| form)
        .map_err(|error| SparqlError::Parse(error.to_string()))
}

// ---------------------------------------------------------------------------
// The guard
// ---------------------------------------------------------------------------

/// Update and federated keywords, refused wherever they appear as a word.
const FORBIDDEN: &[&str] = &[
    "INSERT", "DELETE", "LOAD", "CLEAR", "DROP", "CREATE", "SERVICE", "DESCRIBE",
];

/// One lexical token. `Qualified` is a whole prefixed name such as
/// `doc:hasStatement` or `ex:delete`, kept opaque so its local part cannot be
/// mistaken for a keyword.
#[derive(Debug, Clone, Copy)]
enum Token<'a> {
    Word(&'a str),
    Qualified,
    Iri,
    Other,
}

/// Find the query form and refuse every keyword that is not read-only.
///
/// This is intentionally not a substring search: the tokenizer is the whole
/// point. A literal `"delete"`, an IRI `<http://example.com/delete>`, a variable
/// `?delete` and a prefixed name `ex:delete` all fall through; the old Python
/// guard refused them, and that is the defect being replaced.
fn guard(sparql: &str) -> Result<QueryForm, SparqlError> {
    let tokens = tokenize(sparql);
    if tokens.is_empty() {
        return Err(SparqlError::Parse(
            "the query is empty; send a SELECT or an ASK".to_string(),
        ));
    }

    for token in &tokens {
        if let Token::Word(word) = token {
            let keyword = word.to_ascii_uppercase();
            if FORBIDDEN.contains(&keyword.as_str()) {
                return Err(guard_error(&keyword));
            }
        }
    }

    let mut index = 0;
    while let Some(token) = tokens.get(index) {
        match token {
            Token::Word(word) => {
                let keyword = word.to_ascii_uppercase();
                match keyword.as_str() {
                    // Declarations are not a query form; skip the declaration
                    // and look at the first real keyword after it.
                    "PREFIX" => {
                        index += 1;
                        if matches!(tokens.get(index), Some(Token::Qualified)) {
                            index += 1;
                        }
                        if matches!(tokens.get(index), Some(Token::Iri)) {
                            index += 1;
                        }
                    }
                    "BASE" => {
                        index += 1;
                        if matches!(tokens.get(index), Some(Token::Iri)) {
                            index += 1;
                        }
                    }
                    "SELECT" => return Ok(QueryForm::Select),
                    "ASK" => return Ok(QueryForm::Ask),
                    "CONSTRUCT" => {
                        return Err(SparqlError::Guard {
                            keyword,
                            message: "only bound rows are returned, from SELECT and ASK; \
                                      CONSTRUCT would produce a graph"
                                .to_string(),
                        });
                    }
                    _ => {
                        return Err(SparqlError::Parse(format!(
                            "expected SELECT or ASK, found `{word}`; only read-only queries \
                             are accepted"
                        )));
                    }
                }
            }
            _ => index += 1,
        }
    }

    Err(SparqlError::Parse(
        "no SELECT or ASK keyword in the query; declare prefixes after it, not instead of it"
            .to_string(),
    ))
}

/// A refusal that names the keyword and says what to write instead.
fn guard_error(keyword: &str) -> SparqlError {
    let keyword = keyword.to_ascii_uppercase();
    let message = match keyword.as_str() {
        "SERVICE" => "federated queries are disabled: the graph is local and the server has no \
                      network client; query the local graph without SERVICE"
            .to_string(),
        "DESCRIBE" => "only bound rows are returned, from SELECT and ASK; DESCRIBE would produce \
                       a graph"
            .to_string(),
        _ => "SPARQL update keywords are refused: documents_query is read-only and accepts \
              SELECT and ASK only"
            .to_string(),
    };
    SparqlError::Guard { keyword, message }
}

/// Split SPARQL into the tokens the guard needs, skipping the four places a
/// keyword may hide: comments, strings, IRIs and variables.
///
/// The heuristics are deliberately narrow. `<` starts an IRI only when a `>`
/// closes before whitespace or a delimiter, so `FILTER(?x < 5)` stays an
/// operator; a prefixed name is consumed whole, so `ex:service` is one opaque
/// token. A malformed query may be tokenized unusually, but the real parser
/// rejects it afterwards, and a false negative here cannot become a write:
/// the store is in memory and `query` only ever parses a query, never an update.
fn tokenize(sparql: &str) -> Vec<Token<'_>> {
    let bytes = sparql.as_bytes();
    let mut tokens = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'#' => {
                while index < bytes.len() && bytes[index] != b'\n' {
                    index += 1;
                }
            }
            b'"' | b'\'' => index = skip_string(bytes, index),
            b'<' => match iri_end(bytes, index) {
                Some(end) => {
                    tokens.push(Token::Iri);
                    index = end + 1;
                }
                None => {
                    tokens.push(Token::Other);
                    index += 1;
                }
            },
            b'?' | b'$' => {
                index += 1;
                while index < bytes.len() && is_name_byte(bytes[index]) {
                    index += 1;
                }
            }
            byte if byte.is_ascii_alphabetic() || byte == b'_' => {
                let start = index;
                index += 1;
                while index < bytes.len() && is_name_byte(bytes[index]) {
                    index += 1;
                }
                if index < bytes.len() && bytes[index] == b':' {
                    // A prefixed name: consume the colon and the local part,
                    // including the dots and colons PN_LOCAL allows.
                    index += 1;
                    while index < bytes.len() {
                        match bytes[index] {
                            b'\\' => index += 2,
                            byte if is_local_byte(byte) => index += 1,
                            _ => break,
                        }
                    }
                    tokens.push(Token::Qualified);
                } else {
                    tokens.push(Token::Word(&sparql[start..index]));
                }
            }
            _ => {
                tokens.push(Token::Other);
                index += 1;
            }
        }
    }
    tokens
}

/// A character in a bare word; keywords never contain `-` but prefixed names do,
/// and a word is never split on one.
fn is_name_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-'
}

/// A character allowed in a prefixed name's local part.
fn is_local_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.' | b'%' | b':') || byte >= 0x80
}

/// The index of the `>` closing an IRI that starts at `start`, or `None` when
/// this `<` is a comparison operator or a malformed IRI.
fn iri_end(bytes: &[u8], start: usize) -> Option<usize> {
    let mut index = start + 1;
    while index < bytes.len() {
        match bytes[index] {
            b'>' => return Some(index),
            byte if byte.is_ascii_whitespace() => return None,
            b'<' | b'"' | b'\'' | b'{' | b'}' | b'|' | b'^' | b'`' => return None,
            _ => index += 1,
        }
    }
    None
}

/// Skip a short or triple-quoted string, honouring backslash escapes.
fn skip_string(bytes: &[u8], start: usize) -> usize {
    let quote = bytes[start];
    let triple = start + 2 < bytes.len() && bytes[start + 1] == quote && bytes[start + 2] == quote;
    let mut index = start + if triple { 3 } else { 1 };
    while index < bytes.len() {
        if bytes[index] == b'\\' {
            index += 2;
            continue;
        }
        if triple {
            if index + 2 < bytes.len()
                && bytes[index] == quote
                && bytes[index + 1] == quote
                && bytes[index + 2] == quote
            {
                return index + 3;
            }
            index += 1;
        } else {
            if bytes[index] == quote {
                return index + 1;
            }
            // A raw newline cannot be inside a short string; stop here and let
            // the parser report the unterminated literal.
            if bytes[index] == b'\n' {
                return index;
            }
            index += 1;
        }
    }
    bytes.len()
}

// ---------------------------------------------------------------------------
// The vocabulary and the caps
// ---------------------------------------------------------------------------

/// Reject a graph that uses a `doc:` term the served vocabulary does not define.
///
/// The check walks the loaded quads through oxigraph rather than the file's
/// text: a term inside a literal or a comment is not a term of the graph, and a
/// term written as `<https://ontoskills.sh/ontology/documents#X>` must be caught
/// as well as `doc:X`.
fn validate_vocabulary(store: &Store, path: &Path) -> Result<(), SparqlError> {
    let known = vocabulary()?;
    let mut unknown = BTreeSet::new();
    for quad in store.iter() {
        let quad =
            quad.map_err(|error| SparqlError::Load(path.to_path_buf(), error.to_string()))?;
        if let NamedOrBlankNode::NamedNode(node) = &quad.subject {
            collect_unknown(node.as_str(), known, &mut unknown);
        }
        collect_unknown(quad.predicate.as_str(), known, &mut unknown);
        match &quad.object {
            Term::NamedNode(node) => collect_unknown(node.as_str(), known, &mut unknown),
            Term::Literal(literal) => {
                collect_unknown(literal.datatype().as_str(), known, &mut unknown);
            }
            _ => {}
        }
    }

    if unknown.is_empty() {
        return Ok(());
    }
    let named: Vec<String> = unknown
        .iter()
        .take(8)
        .map(|local| format!("doc:{local} (<{DOC_NAMESPACE}{local}>)"))
        .collect();
    let rest = unknown.len().saturating_sub(named.len());
    let more = if rest == 0 {
        String::new()
    } else {
        format!(" and {rest} more")
    };
    Err(SparqlError::Vocabulary(format!(
        "the graph uses doc: terms this server does not know at documents 1.0.0: {}{more}; \
         the knowledge base and ontomcp disagree on the vocabulary version — rebuild the graph \
         with the matching `ontocore documents` or install the matching ontomcp",
        named.join(", ")
    )))
}

fn collect_unknown(iri: &str, known: &HashSet<String>, unknown: &mut BTreeSet<String>) {
    if let Some(local) = iri.strip_prefix(DOC_NAMESPACE) {
        if !known.contains(local) {
            unknown.insert(local.to_string());
        }
    }
}

/// The terms the embedded vocabulary defines, parsed once per process.
///
/// Subjects are the terms the spec declares (`doc:Document a owl:Class`, …) and
/// predicates are included so a property mentioned only in a definition is not
/// reported as missing.
fn vocabulary() -> Result<&'static HashSet<String>, SparqlError> {
    static VOCABULARY_SET: OnceLock<Result<HashSet<String>, String>> = OnceLock::new();
    match VOCABULARY_SET.get_or_init(load_vocabulary) {
        Ok(known) => Ok(known),
        Err(message) => Err(SparqlError::Load(
            PathBuf::from("core/src/specs/documents.ttl"),
            message.clone(),
        )),
    }
}

fn load_vocabulary() -> Result<HashSet<String>, String> {
    let store = Store::new().map_err(|error| error.to_string())?;
    store
        .load_from_slice(RdfFormat::Turtle, VOCABULARY)
        .map_err(|error| error.to_string())?;
    let mut known = HashSet::new();
    for quad in store.iter() {
        let quad = quad.map_err(|error| error.to_string())?;
        if let NamedOrBlankNode::NamedNode(node) = &quad.subject {
            if let Some(local) = node.as_str().strip_prefix(DOC_NAMESPACE) {
                known.insert(local.to_string());
            }
        }
        if let Some(local) = quad.predicate.as_str().strip_prefix(DOC_NAMESPACE) {
            known.insert(local.to_string());
        }
    }
    if known.is_empty() {
        return Err("the embedded vocabulary declares no doc: term".to_string());
    }
    Ok(known)
}

fn evaluation_error(error: QueryEvaluationError) -> SparqlError {
    // The only token this module injects is the deadline's, so a cancellation
    // here is the 2 s cap firing and not an unrelated abort.
    match error {
        QueryEvaluationError::Cancelled => SparqlError::Timeout,
        other => SparqlError::Evaluation(other.to_string()),
    }
}

type CacheSlot = Mutex<Option<Cached>>;

struct Cached {
    path: PathBuf,
    modified: Option<SystemTime>,
    len: u64,
    store: Arc<GraphStore>,
}

fn cache_slot() -> &'static CacheSlot {
    static CACHE: OnceLock<CacheSlot> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(None))
}

/// A thread that cancels the query when the budget runs out.
///
/// The thread waits on a channel rather than sleeping the full budget, so a
/// fast query tells it to exit immediately and `stop` joins in microseconds;
/// nothing is left behind between requests.
struct Watchdog {
    token: CancellationToken,
    done: Option<std::sync::mpsc::Sender<()>>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl Watchdog {
    fn start() -> Watchdog {
        let token = CancellationToken::new();
        let (done, wait) = std::sync::mpsc::channel::<()>();
        let worker = token.clone();
        let thread = std::thread::spawn(move || {
            // A timeout here means the query is still running at the deadline.
            if wait.recv_timeout(TIME_BUDGET).is_err() {
                worker.cancel();
            }
        });
        Watchdog {
            token,
            done: Some(done),
            thread: Some(thread),
        }
    }

    fn token(&self) -> &CancellationToken {
        &self.token
    }

    fn stop(mut self) {
        self.finish();
    }

    fn finish(&mut self) {
        if let Some(done) = self.done.take() {
            let _ = done.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for Watchdog {
    fn drop(&mut self) {
        self.finish();
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::*;

    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/documents/kb")
    }

    fn fixture_store() -> GraphStore {
        let kb = Kb::load(fixture()).expect("fixture loads");
        GraphStore::open(&kb).expect("fixture graph loads")
    }

    /// A temporary directory removed on drop, named uniquely per test process.
    struct TempDir(PathBuf);

    impl TempDir {
        fn new(tag: &str) -> TempDir {
            static COUNTER: AtomicU64 = AtomicU64::new(0);
            let count = COUNTER.fetch_add(1, Ordering::Relaxed);
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|duration| duration.as_nanos())
                .unwrap_or(0);
            let path = std::env::temp_dir().join(format!(
                "ontomcp-sparql-{tag}-{}-{count}-{nanos}",
                std::process::id()
            ));
            fs::create_dir_all(&path).expect("temp dir");
            TempDir(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn a_select_returns_the_rows_and_variables_the_query_asked_for() {
        let store = fixture_store();
        let result = store
            .query("SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5")
            .expect("query runs");
        assert_eq!(result.rows.len(), 5);
        assert_eq!(result.variables, vec!["s", "p", "o"]);
        assert!(result.boolean.is_none());
        assert!(result.rows.iter().all(|row| row.len() == 3));
        assert!(result.rows.iter().flatten().all(Option::is_some));
    }

    #[test]
    fn an_ask_returns_its_boolean_and_no_variables() {
        let store = fixture_store();
        let result = store
            .query("ASK { ?s a doc:Document }")
            .expect("query runs");
        assert_eq!(result.boolean, Some(true));
        assert!(result.variables.is_empty());
        assert_eq!(result.rows, vec![vec![Some("true".to_string())]]);
    }

    #[test]
    fn every_write_and_federated_keyword_is_refused_by_name() {
        let cases = [
            ("INSERT DATA { <a:a> <a:b> <a:c> }", "INSERT"),
            ("DELETE WHERE { ?s ?p ?o }", "DELETE"),
            ("LOAD <file:///tmp/x.ttl>", "LOAD"),
            ("CLEAR ALL", "CLEAR"),
            ("DROP GRAPH <a:g>", "DROP"),
            ("CREATE GRAPH <a:g>", "CREATE"),
            ("DESCRIBE <a:a>", "DESCRIBE"),
            (
                "SELECT * WHERE { SERVICE <http://x/sparql> { ?s ?p ?o } }",
                "SERVICE",
            ),
        ];
        for (query, keyword) in cases {
            let error = check_read_only(query).expect_err(keyword);
            assert!(
                error.to_string().contains(keyword),
                "{keyword} missing from {error}"
            );
            match error {
                SparqlError::Guard { keyword: named, .. } => assert_eq!(named, keyword),
                other => panic!("{keyword} was not a guard error: {other:?}"),
            }
        }
    }

    #[test]
    fn a_keyword_inside_a_literal_is_not_a_keyword() {
        let query = r#"SELECT ?s WHERE { ?s doc:hasStatement ?o . FILTER(CONTAINS(?o, "delete")) } LIMIT 1"#;
        assert_eq!(
            check_read_only(query).expect("a literal is not a keyword"),
            QueryForm::Select
        );
        // The same query also runs: the guard is not the only consumer.
        let store = fixture_store();
        let result = store.query(query).expect("query runs");
        assert!(result.rows.len() <= 1);
    }

    #[test]
    fn keyword_shaped_names_comments_and_strings_are_not_keywords() {
        // Every forbidden word appears here in a place that is not the word:
        // a comment, a prefixed name's local part, a variable and a string.
        let query = "PREFIX ex: <https://example.com/>\n\
                     # DELETE, DROP and SERVICE live here, not in the query\n\
                     SELECT ?delete WHERE {\n\
                         ?delete ex:delete ?o .\n\
                         ?delete ex:service ?o .\n\
                         FILTER(CONTAINS(?o, \"\"\"delete\"\"\"))\n\
                     } LIMIT 1";
        assert_eq!(
            check_read_only(query).expect("names are not keywords"),
            QueryForm::Select
        );
    }

    #[test]
    fn a_broken_query_is_a_parse_error_not_a_panic() {
        let store = fixture_store();
        let error = store
            .query("SELECT ?s WHERE { ?s ?p ?o")
            .expect_err("missing brace");
        assert!(matches!(error, SparqlError::Parse(_)), "{error:?}");
    }

    #[test]
    fn a_graph_with_an_unknown_doc_term_is_refused_and_the_term_named() {
        let dir = TempDir::new("vocabulary");
        fs::write(
            dir.path().join("claims.jsonl"),
            "{\"claim_id\":\"c1\",\"statement\":\"x\"}\n",
        )
        .expect("claims");
        fs::write(dir.path().join("documents.jsonl"), "").expect("documents");
        fs::write(dir.path().join("verifier.jsonl"), "").expect("verifier");
        fs::write(
            dir.path().join("graph.ttl"),
            "@prefix doc: <https://ontoskills.sh/ontology/documents#> .\n\
             <https://ontoskills.sh/kb/d> a doc:Document ;\n\
                 doc:hasNonexistentThing \"x\" .\n",
        )
        .expect("graph");

        let kb = Kb::load(dir.path()).expect("temp kb loads");
        let error = GraphStore::open(&kb).expect_err("unknown term");
        assert!(matches!(error, SparqlError::Vocabulary(_)), "{error:?}");
        assert!(
            error.to_string().contains("hasNonexistentThing"),
            "term not named: {error}"
        );
    }

    #[test]
    fn more_than_the_row_cap_is_refused_and_the_cap_named() {
        let dir = TempDir::new("rows");
        let mut turtle = String::from("@prefix ex: <https://example.com/> .\n");
        for index in 0..2500 {
            turtle.push_str(&format!("ex:s{index} ex:p ex:o .\n"));
        }
        let graph = dir.path().join("graph.ttl");
        fs::write(&graph, turtle).expect("graph");
        let store = GraphStore::open_path(&graph).expect("graph loads");
        let error = store
            .query("SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
            .expect_err("over the row cap");
        assert!(matches!(error, SparqlError::Rows(MAX_ROWS)), "{error:?}");
        assert!(error.to_string().contains("2000"), "{error}");
    }

    #[test]
    fn the_cache_returns_the_same_snapshot_until_the_graph_changes() {
        let kb = Kb::load(fixture()).expect("fixture loads");
        let first = GraphStore::cached(&kb).expect("cached open");
        let second = GraphStore::cached(&kb).expect("cached open");
        assert!(Arc::ptr_eq(&first, &second));
    }
}
