//! The document layer's read path.
//!
//! `ontocore` compiles a folder of documents into a knowledge base; this module
//! reads that artifact and answers from it in-process. Nothing here calls a
//! model, writes a file, or reaches the network: the compiler owns creation, the
//! server owns reading.
//!
//! Layout:
//!
//! * [`text`] — the tokenizer, reproduced from the Python one character class by
//!   character class;
//! * [`stopwords`] — the list, generated rather than typed;
//! * [`kb`] — loading and validating a knowledge base, with a mtime cache;
//! * [`rank`] — BM25, de-duplication, citations, contradiction links;
//! * [`sparql`] — read-only SPARQL over `graph.ttl`.

pub mod kb;
pub mod rank;
pub mod sparql;
pub mod stopwords;
pub mod text;
pub mod tools;
