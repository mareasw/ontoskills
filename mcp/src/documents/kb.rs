//! Loading and validating a compiled knowledge base.
//!
//! A knowledge base is a directory `ontocore documents` writes; the server only
//! reads it. This module owns the reading half of that contract:
//!
//! * the file names and the fields the read path actually uses, with the same
//!   defaults the Python reader applies (`claim.get("x", "")` tolerates a missing
//!   field, so a missing field here is not an error);
//! * a cache keyed on the root and invalidated by the mtime of every file that
//!   feeds an answer, so one process asks a hundred questions without parsing
//!   `claims.jsonl` a hundred times;
//! * a path guard: a `doc_id` from the artifact becomes a file name, and a
//!   `doc_id` of `../../etc/passwd` must not.
//!
//! What this module deliberately does not load: `spans.jsonl`, `rejected.jsonl`,
//! `evidence.csv`, `view.html` and `vectors.jsonl`. The first four are not part
//! of an answer; the vectors belong to the semantic pass, which the pilot's
//! knowledge base does not carry and which v1 does not implement.

use std::collections::HashMap;
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::SystemTime;

use serde::Deserialize;
use serde_json::Value;

use super::rank::Index;

/// The artifact's file names, spelled once.
pub const MANIFEST: &str = "manifest.json";
pub const DOCUMENTS: &str = "documents.jsonl";
pub const CLAIMS: &str = "claims.jsonl";
pub const VERIFIER: &str = "verifier.jsonl";
pub const GRAPH: &str = "graph.ttl";
pub const TEXT_DIR: &str = "text";

/// The environment variable that names the default knowledge base.
pub const ROOT_ENV: &str = "ONTOSKILLS_KB_ROOT";

/// Everything that can stop a knowledge base from being read, each with the
/// fact a caller needs to fix it.
#[derive(Debug)]
pub enum KbError {
    /// No `kb` argument and no `ONTOSKILLS_KB_ROOT`.
    NoRoot,
    /// The root does not exist, or is not a directory.
    NotADirectory(PathBuf),
    /// The directory exists but holds no `claims.jsonl`.
    NoClaims(PathBuf),
    /// A relative root that climbs out with `..`.
    PathEscape(PathBuf),
    /// A `doc_id` that would name a file outside `text/`.
    UnsafeDocId(String),
    /// A file could not be read.
    Io(PathBuf, std::io::Error),
    /// A file was read but is not the JSON or JSONL the format promises.
    Format(PathBuf, String),
}

impl fmt::Display for KbError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            KbError::NoRoot => write!(
                f,
                "no knowledge base given: pass `kb` or set {ROOT_ENV} to a directory \
                 `ontocore documents ingest` wrote"
            ),
            KbError::NotADirectory(path) => {
                write!(f, "{}: not a directory", path.display())
            }
            KbError::NoClaims(path) => write!(
                f,
                "{}: no {CLAIMS}; run `ontocore documents ingest` first",
                path.display()
            ),
            KbError::PathEscape(path) => write!(
                f,
                "{}: a knowledge base root must not contain `..`",
                path.display()
            ),
            KbError::UnsafeDocId(doc_id) => write!(
                f,
                "doc_id {doc_id:?} names a path outside the knowledge base; \
                 refusing to open it"
            ),
            KbError::Io(path, error) => write!(f, "{}: {error}", path.display()),
            KbError::Format(path, error) => write!(f, "{}: {error}", path.display()),
        }
    }
}

impl std::error::Error for KbError {}

/// The provenance block a claim carries; only `source` is ranked.
///
/// `Option` rather than `String` because the Python reader distinguishes an
/// absent `source` from an empty one: `context.get("source", doc_id)` falls back
/// to the document id only when the key is missing.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Context {
    #[serde(default)]
    pub source: Option<String>,
}

/// Where a quote was found, in the normalised text the compiler indexed.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Locator {
    #[serde(default)]
    pub kind: String,
    #[serde(default, deserialize_with = "strings")]
    pub section_path: Vec<String>,
    #[serde(default)]
    pub url: String,
    #[serde(default, deserialize_with = "number")]
    pub char_start: Option<i64>,
    #[serde(default, deserialize_with = "number")]
    pub char_end: Option<i64>,
    #[serde(default, deserialize_with = "number")]
    pub page: Option<i64>,
}

/// One quotation of the source, with the role it plays in the claim.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Evidence {
    #[serde(default, deserialize_with = "string_or_empty")]
    pub quote: String,
    /// `supports`, `contradicts` or `context`; a string, not an enum, because a
    /// future role must not make an old artifact unreadable.
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub locator: Locator,
}

/// One atomic claim, with the fields the read path uses.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Claim {
    #[serde(default)]
    pub claim_id: String,
    #[serde(default)]
    pub doc_id: String,
    #[serde(default)]
    pub statement: String,
    #[serde(default)]
    pub modality: String,
    #[serde(default)]
    pub actor: String,
    #[serde(default)]
    pub deadline: String,
    #[serde(default, deserialize_with = "strings")]
    pub conditions: Vec<String>,
    #[serde(default)]
    pub evidence: Vec<Evidence>,
    #[serde(default)]
    pub context: Context,
    #[serde(default, deserialize_with = "strings")]
    pub conflicts_with: Vec<String>,
}

impl Claim {
    /// The evidence item the citation is built from; an empty claim still yields
    /// an empty one, as `evidence or [{}]` does in Python.
    pub fn first_evidence(&self) -> &Evidence {
        self.evidence.first().unwrap_or_else(|| {
            static EMPTY: OnceLock<Evidence> = OnceLock::new();
            EMPTY.get_or_init(Evidence::default)
        })
    }
}

/// One document of the artifact.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Document {
    #[serde(default)]
    pub doc_id: String,
    #[serde(default, deserialize_with = "string_or_empty")]
    pub title: String,
    #[serde(default, deserialize_with = "string_or_empty")]
    pub url: String,
    #[serde(default)]
    pub licence: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub doc_type: String,
    #[serde(default)]
    pub sha256: String,
}

/// A loaded knowledge base, immutable once built.
#[derive(Debug)]
pub struct Kb {
    root: PathBuf,
    documents: Vec<Document>,
    by_doc: HashMap<String, usize>,
    claims: Vec<Claim>,
    by_claim: HashMap<String, usize>,
    /// The verifier's row per claim; absent means `ok`, as in the Python reader.
    verdicts: HashMap<String, ClaimVerdict>,
    /// The mtimes this snapshot was built from, compared on the next request.
    signature: Signature,
    /// The ranking index, built on the first question and kept for the life of
    /// the snapshot. Two slots because `include_unverified` changes the corpus
    /// the index is built over, not just what is shown from it.
    pub(super) index_verified: OnceLock<Index>,
    pub(super) index_all: OnceLock<Index>,
}

/// `(path, mtime, length)` for every file an answer depends on.
type Signature = Vec<(PathBuf, Option<SystemTime>, u64)>;

impl Kb {
    /// Read a knowledge base from `root`.
    ///
    /// `root` must be an existing directory holding a `claims.jsonl`. Relative
    /// paths containing `..` are refused rather than resolved: a caller that
    /// asks for a directory by climbing out of one is either confused or
    /// hostile, and both cases deserve an error instead of a guess.
    pub fn load(root: impl AsRef<Path>) -> Result<Kb, KbError> {
        let root = root.as_ref();
        if root.as_os_str().is_empty() {
            return Err(KbError::NoRoot);
        }
        if root
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        {
            return Err(KbError::PathEscape(root.to_path_buf()));
        }
        let root = fs::canonicalize(root)
            .map_err(|_| KbError::NotADirectory(root.to_path_buf()))?;
        if !root.is_dir() {
            return Err(KbError::NotADirectory(root));
        }

        let claims_path = root.join(CLAIMS);
        if !claims_path.is_file() {
            return Err(KbError::NoClaims(root));
        }

        let signature = signature(&root);
        let documents: Vec<Document> = read_jsonl(&root.join(DOCUMENTS))?;
        let claims: Vec<Claim> = read_jsonl(&claims_path)?;
        let verdict_rows: Vec<ClaimVerdict> = read_jsonl(&root.join(VERIFIER))?;

        let by_doc = documents
            .iter()
            .enumerate()
            .map(|(index, doc)| (doc.doc_id.clone(), index))
            .collect();
        let by_claim = claims
            .iter()
            .enumerate()
            .map(|(index, claim)| (claim.claim_id.clone(), index))
            .collect();
        let verdicts = verdict_rows
            .into_iter()
            .map(|row| (row.claim_id.clone(), row))
            .collect();

        Ok(Kb {
            root,
            documents,
            by_doc,
            claims,
            by_claim,
            verdicts,
            signature,
            index_verified: OnceLock::new(),
            index_all: OnceLock::new(),
        })
    }

    /// The process-wide cache: one `Kb` per root, rebuilt when a file changes.
    ///
    /// A server answers questions until it is stopped, and a knowledge base is
    /// recompiled while it runs. Comparing mtimes rather than watching the
    /// filesystem keeps this dependency-free and is what makes a rebuild
    /// visible on the next question instead of on the next restart.
    pub fn cached(root: impl AsRef<Path>) -> Result<Arc<Kb>, KbError> {
        static CACHE: OnceLock<Mutex<HashMap<PathBuf, Arc<Kb>>>> = OnceLock::new();
        let cache = CACHE.get_or_init(|| Mutex::new(HashMap::new()));

        let root = root.as_ref();
        let lookup = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
        // A poisoned lock means another thread panicked while holding it; the
        // map is still readable, and refusing to answer would be worse.
        let mut map = cache.lock().unwrap_or_else(|error| error.into_inner());
        if let Some(kb) = map.get(&lookup) {
            if kb.signature == signature(&lookup) {
                return Ok(Arc::clone(kb));
            }
        }
        let kb = Arc::new(Kb::load(&lookup)?);
        map.insert(lookup, Arc::clone(&kb));
        Ok(kb)
    }

    /// Drop every cached knowledge base. Tests only: a running server has no
    /// reason to forget an artifact it will read again.
    #[cfg(test)]
    pub fn clear_cache() {
        static CACHE: OnceLock<Mutex<HashMap<PathBuf, Arc<Kb>>>> = OnceLock::new();
        if let Some(cache) = CACHE.get() {
            cache.lock().unwrap_or_else(|error| error.into_inner()).clear();
        }
    }

    pub fn claims(&self) -> &[Claim] {
        &self.claims
    }

    pub fn document(&self, doc_id: &str) -> Option<&Document> {
        self.by_doc.get(doc_id).map(|index| &self.documents[*index])
    }

    pub fn claim(&self, claim_id: &str) -> Option<&Claim> {
        self.by_claim.get(claim_id).map(|index| &self.claims[*index])
    }

    /// The verifier's verdict for a claim; `ok` when the file does not mention it.
    pub fn verdict(&self, claim_id: &str) -> &str {
        self.claim_verdict(claim_id)
            .map(|row| row.verdict.as_str())
            .unwrap_or("ok")
    }

    /// The whole verifier row — verdict, reasons, notes — for `documents_claim`.
    pub fn claim_verdict(&self, claim_id: &str) -> Option<&ClaimVerdict> {
        self.verdicts.get(claim_id)
    }

    pub fn has_verdicts(&self) -> bool {
        !self.verdicts.is_empty()
    }

    pub fn graph_path(&self) -> PathBuf {
        self.root.join(GRAPH)
    }

    /// The extracted text of a document, normalised by the compiler.
    ///
    /// A missing file is an empty string, as on the Python side: the citation is
    /// still worth returning without its text.
    pub fn text(&self, doc_id: &str) -> Result<String, KbError> {
        let path = self.text_path(doc_id)?;
        match fs::read_to_string(&path) {
            Ok(text) => Ok(text),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(String::new()),
            Err(error) => Err(KbError::Io(path, error)),
        }
    }

    /// `text/<doc_id>.txt`, refusing a `doc_id` that is not a plain file name.
    pub fn text_path(&self, doc_id: &str) -> Result<PathBuf, KbError> {
        let unsafe_id = doc_id.is_empty()
            || doc_id == "."
            || doc_id == ".."
            || doc_id.contains('/')
            || doc_id.contains('\\')
            || doc_id.contains('\0')
            || Path::new(doc_id).components().count() != 1;
        if unsafe_id {
            return Err(KbError::UnsafeDocId(doc_id.to_string()));
        }
        Ok(self.root.join(TEXT_DIR).join(format!("{doc_id}.txt")))
    }

}

/// One row of `verifier.jsonl`: what the deterministic verifier decided, and
/// the reasons a reader can disagree with.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct ClaimVerdict {
    #[serde(default)]
    pub claim_id: String,
    #[serde(default)]
    pub verdict: String,
    #[serde(default, deserialize_with = "strings")]
    pub reasons: Vec<String>,
    #[serde(default, deserialize_with = "strings")]
    pub notes: Vec<String>,
}

fn signature(root: &Path) -> Signature {
    [MANIFEST, DOCUMENTS, CLAIMS, VERIFIER, GRAPH]
        .iter()
        .map(|name| {
            let path = root.join(name);
            let meta = fs::metadata(&path).ok();
            (
                path,
                meta.as_ref().and_then(|meta| meta.modified().ok()),
                meta.map(|meta| meta.len()).unwrap_or(0),
            )
        })
        .collect()
}

/// One JSON value per non-blank line, as `store.read_jsonl` reads it.
fn read_jsonl<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<Vec<T>, KbError> {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(KbError::Io(path.to_path_buf(), error)),
    };
    let mut rows = Vec::new();
    for (number, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row = serde_json::from_str(line).map_err(|error| {
            KbError::Format(path.to_path_buf(), format!("line {}: {error}", number + 1))
        })?;
        rows.push(row);
    }
    Ok(rows)
}

/// A JSON array of strings, tolerating the numbers a locator may carry.
fn strings<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = Option::<Value>::deserialize(deserializer)?;
    Ok(match value {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items
            .into_iter()
            .filter_map(|item| match item {
                Value::String(text) => Some(text),
                Value::Number(number) => Some(number.to_string()),
                Value::Bool(flag) => Some(flag.to_string()),
                _ => None,
            })
            .collect(),
        Some(other) => vec![other.to_string()],
    })
}

/// A string that tolerates an explicit `null`, which Python keeps as `None` and
/// every consumer of these fields treats as absent.
fn string_or_empty<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = Option::<Value>::deserialize(deserializer)?;
    Ok(match value {
        None | Some(Value::Null) => String::new(),
        Some(Value::String(text)) => text,
        Some(other) => other.to_string(),
    })
}

/// An integer that tolerates `3`, `3.0`, `"3"` and `null`.
fn number<'de, D>(deserializer: D) -> Result<Option<i64>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let value = Option::<Value>::deserialize(deserializer)?;
    Ok(match value {
        None | Some(Value::Null) => None,
        Some(Value::Number(number)) => number
            .as_i64()
            .or_else(|| number.as_f64().map(|float| float as i64)),
        Some(Value::String(text)) => text.trim().parse().ok(),
        _ => None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/documents/kb")
    }

    #[test]
    fn the_fixture_loads_with_the_counts_the_generator_wrote() {
        let kb = Kb::load(fixture()).expect("fixture loads");
        assert_eq!(kb.claims().len(), 77);
        assert_eq!(kb.documents.len(), 3);
        assert!(kb.has_verdicts());
        assert_eq!(kb.verdict("dsid_020bac2fb6ac4de28d5afb63e39a0c10-0001"), "ok");
        // A claim the verifier does not mention is `ok`, not unknown.
        assert_eq!(kb.verdict("not-a-claim"), "ok");
        // The manifest is part of the cache signature; the reader itself does
        // not need its contents, so it is not kept in memory.
        assert!(kb.root.join(MANIFEST).is_file());
    }

    #[test]
    fn a_claim_keeps_its_evidence_and_its_locator() {
        let kb = Kb::load(fixture()).expect("fixture loads");
        let claim = kb
            .claim("dsid_020bac2fb6ac4de28d5afb63e39a0c10-0001")
            .expect("claim is in the fixture");
        assert!(!claim.statement.is_empty());
        assert!(!claim.evidence.is_empty());
        let locator = &claim.first_evidence().locator;
        assert!(locator.char_start.is_some());
        assert!(locator.char_end.unwrap() > locator.char_start.unwrap());
        assert!(!claim.evidence.is_empty());
    }

    #[test]
    fn a_doc_id_cannot_name_a_file_outside_the_text_directory() {
        let kb = Kb::load(fixture()).expect("fixture loads");
        for bad in ["../manifest", "a/b", "..", ".", "", "a\\b"] {
            assert!(
                matches!(kb.text_path(bad), Err(KbError::UnsafeDocId(_))),
                "{bad:?} was accepted as a doc_id"
            );
        }
        let good = kb.text_path("dsid_020bac2fb6ac4de28d5afb63e39a0c10").expect("plain id");
        assert_eq!(
            good.file_name().unwrap(),
            "dsid_020bac2fb6ac4de28d5afb63e39a0c10.txt"
        );
    }

    #[test]
    fn a_document_text_is_read_and_a_missing_one_is_empty() {
        let kb = Kb::load(fixture()).expect("fixture loads");
        let text = kb.text("dsid_020bac2fb6ac4de28d5afb63e39a0c10").expect("text");
        assert!(!text.is_empty());
        assert_eq!(kb.text("dsid_ffffffffffffffffffffffffffffffff").expect("missing"), "");
    }

    #[test]
    fn a_root_without_claims_is_refused_with_the_reason() {
        let empty = std::env::temp_dir().join("ontomcp-kb-empty-test");
        fs::create_dir_all(&empty).expect("temp dir");
        let error = Kb::load(&empty).expect_err("no claims.jsonl");
        assert!(matches!(error, KbError::NoClaims(_)));
        assert!(error.to_string().contains("ontocore documents ingest"));
        let _ = fs::remove_dir(&empty);
    }

    #[test]
    fn a_parent_directory_in_the_root_is_refused() {
        let error = Kb::load("kb/../../etc").expect_err("must refuse");
        assert!(matches!(error, KbError::PathEscape(_)));
    }

    #[test]
    fn the_cache_returns_the_same_snapshot_until_the_files_change() {
        let kb = fixture();
        Kb::clear_cache();
        let first = Kb::cached(&kb).expect("cached load");
        let second = Kb::cached(&kb).expect("cached load");
        assert!(Arc::ptr_eq(&first, &second));
    }
}
