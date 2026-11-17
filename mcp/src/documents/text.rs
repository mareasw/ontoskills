//! The text rules the ranking rests on, ported from `compiler.documents.text`.
//!
//! These three functions decide what a word is and what a sentence is, and a
//! difference of one character changes which claims a question finds. So the
//! Python definitions are reproduced literally, including the parts that look
//! like accidents:
//!
//! * a token is a run of characters in Unicode categories `L*` or `N*` —
//!   Python's `[^\W_]+` — and nothing else; an underscore splits a word, a
//!   combining accent does not join it;
//! * tokens are lower-cased *before* the split, because Python does it in that
//!   order and some lower-casings expand to two code points;
//! * a one-character token is dropped;
//! * `\s` in Python is `str.isspace()`, which is wider than Rust's
//!   `char::is_whitespace()`: the four C0 separators `U+001C..=U+001F` count as
//!   space there and not here.
//!
//! `mcp/tests/documents_parity.rs` compares the token stream of every text in
//! the committed fixture against the Python one, and `benchmark/tests` checks
//! that `stopwords.rs` is still the same list. A change to either side that is
//! not made on both fails CI.

use std::collections::HashSet;
use std::sync::OnceLock;

use unicode_general_category::{get_general_category, GeneralCategory};

use super::stopwords::STOPWORDS;

/// The index form of a word: itself when short, its first seven characters when
/// long. Seven is measured in `ask.py`, not chosen here.
pub const STEM_PREFIX: usize = 7;

/// A character Python's `\w` accepts, minus the underscore. Shared with the
/// duration scanner, which uses it for the same word boundaries.
///
/// ASCII is answered without the category table: for code points below 0x80 the
/// categories `L*` and `N*` are exactly the letters and the digits, and the
/// table lookup is the single most expensive operation in a rebuild, which
/// walks six and a half megabytes of claims.
pub(crate) fn is_word_char(c: char) -> bool {
    if c.is_ascii() {
        return c.is_ascii_alphanumeric();
    }
    matches!(
        get_general_category(c),
        GeneralCategory::UppercaseLetter
            | GeneralCategory::LowercaseLetter
            | GeneralCategory::TitlecaseLetter
            | GeneralCategory::ModifierLetter
            | GeneralCategory::OtherLetter
            | GeneralCategory::DecimalNumber
            | GeneralCategory::LetterNumber
            | GeneralCategory::OtherNumber
    )
}

/// Python's `\s`: Unicode White_Space plus the four C0 separators.
pub(crate) fn is_space(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}')
}

/// Fold curly punctuation to ASCII and collapse whitespace runs.
///
/// The offsets in the artifact index *this* text, so a consumer that slices the
/// raw file at them reads the wrong sentence; `compiler.documents.gaps` maps
/// them back. This function must stay byte-identical in behaviour to `norm`.
pub fn norm(text: &str) -> String {
    let mut folded = String::with_capacity(text.len());
    for c in text.chars() {
        folded.push(match c {
            '\u{2019}' | '\u{2018}' => '\'',
            '\u{201c}' | '\u{201d}' => '"',
            '\u{2013}' | '\u{2014}' => '-',
            other => other,
        });
    }
    let mut out = String::with_capacity(folded.len());
    let mut in_space = false;
    for c in folded.chars() {
        if is_space(c) {
            in_space = true;
            continue;
        }
        if in_space && !out.is_empty() {
            out.push(' ');
        }
        in_space = false;
        out.push(c);
    }
    out
}

/// Lower-cased alphanumeric tokens; one-character tokens are noise.
///
/// Lower-casing happens as the text is walked, one character at a time, instead
/// of on a lowered copy of the whole string: [`char::to_lowercase`] is the
/// per-character mapping Python's `str.lower` uses, so the resulting stream is
/// the same and one full copy of the text per field disappears.
pub fn tokens(text: &str) -> Vec<String> {
    let mut tokenizer = Tokenizer::default();
    for c in text.chars() {
        if c.is_ascii() {
            tokenizer.feed(c.to_ascii_lowercase());
        } else {
            for lowered in c.to_lowercase() {
                tokenizer.feed(lowered);
            }
        }
    }
    tokenizer.finish()
}

#[derive(Default)]
struct Tokenizer {
    tokens: Vec<String>,
    current: String,
    length: usize,
}

impl Tokenizer {
    fn feed(&mut self, c: char) {
        if is_word_char(c) {
            self.current.push(c);
            self.length += 1;
            return;
        }
        self.flush();
    }

    fn flush(&mut self) {
        if self.length > 1 {
            self.tokens.push(std::mem::take(&mut self.current));
        } else {
            self.current.clear();
        }
        self.length = 0;
    }

    fn finish(mut self) -> Vec<String> {
        self.flush();
        self.tokens
    }
}

fn stopword_set() -> &'static HashSet<&'static str> {
    static SET: OnceLock<HashSet<&'static str>> = OnceLock::new();
    SET.get_or_init(|| STOPWORDS.iter().copied().collect())
}

pub fn is_stopword(word: &str) -> bool {
    stopword_set().contains(word)
}

/// Content tokens: no grammatical words. The question is filtered the same way,
/// which is what keeps "quali" from ranking a document that happens to contain
/// it.
pub fn content(text: &str) -> Vec<String> {
    tokens(text)
        .into_iter()
        .filter(|token| !is_stopword(token))
        .collect()
}

/// The index form of one token, on a string the caller already owns.
///
/// A token is lower-cased already, so the only work is the truncation — and the
/// truncation must count characters, not bytes. There is no by-value variant
/// because the ranking owns its tokens and copying them would allocate once per
/// token per field on every rebuild.
pub fn key_in_place(term: &mut String) {
    if term.chars().count() <= STEM_PREFIX {
        return;
    }
    let end = term
        .char_indices()
        .nth(STEM_PREFIX)
        .map(|(index, _)| index)
        .unwrap_or(term.len());
    term.truncate(end);
}

/// The identity of a statement for de-duplication: normalised, then lower-cased.
pub fn statement_key(text: &str) -> String {
    norm(text).to_lowercase()
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use super::*;

    fn key(term: &str) -> String {
        let mut owned = term.to_string();
        key_in_place(&mut owned);
        owned
    }

    #[test]
    fn norm_folds_the_typographic_characters_the_corpus_is_full_of() {
        assert_eq!(norm("the party\u{2019}s duty \u{201c}here\u{201d}"), "the party's duty \"here\"");
        assert_eq!(norm("10\u{2013}20 days\u{2014}no more"), "10-20 days-no more");
        assert_eq!(norm("  two\n\t spaces  "), "two spaces");
        assert_eq!(norm(""), "");
    }

    #[test]
    fn tokens_keep_accents_and_drop_one_character_words() {
        assert_eq!(tokens("La qualità dell'aria è buona"), vec!["la", "qualità", "dell", "aria", "buona"]);
        assert_eq!(tokens("a I x 42"), vec!["42"]);
    }

    #[test]
    fn an_underscore_splits_and_a_combining_accent_does_not_join() {
        assert_eq!(tokens("foo_bar"), vec!["foo", "bar"]);
        // U+0301 is a mark: Python's `\w` does not include it, so "é" written as
        // e + combining acute yields two one-character runs and no token.
        assert_eq!(tokens("e\u{301}"), Vec::<String>::new());
    }

    #[test]
    fn numbers_in_other_scripts_are_tokens_because_python_says_so() {
        // U+00B2 is category No: Python's `\w` accepts it, so it joins the run.
        assert_eq!(tokens("cost 10\u{00b2}"), vec!["cost", "10\u{00b2}"]);
        assert_eq!(tokens("٣٤٥"), vec!["٣٤٥"]);
    }

    #[test]
    fn the_c0_separators_are_whitespace_as_in_python() {
        assert_eq!(norm("one\u{1c}two\u{1f}three"), "one two three");
        assert_eq!(tokens("one\u{1c}two"), vec!["one", "two"]);
    }

    #[test]
    fn content_removes_both_languages_function_words() {
        assert_eq!(content("What are the default limits?"), vec!["default", "limits"]);
        assert_eq!(content("Quali certificazioni possiede l'azienda?"), vec!["certificazioni", "possiede", "azienda"]);
    }

    #[test]
    fn the_stem_is_seven_characters_and_never_shortens_a_short_word() {
        assert_eq!(key("certificazioni"), "certifi");
        assert_eq!(key("fornitore"), "fornito");
        assert_eq!(key("chi"), "chi");
        assert_eq!(key("1234567"), "1234567");
        assert_eq!(key("12345678"), "1234567");
    }

    #[test]
    fn the_in_place_key_is_the_key() {
        for term in ["certificazioni", "chi", "12345678", "qualità", "é"] {
            let mut owned = term.to_string();
            key_in_place(&mut owned);
            assert_eq!(owned, key(term), "{term}");
        }
    }

    /// G7 on a whole knowledge base, not on the three committed documents.
    ///
    /// `benchmark/layer/mcp_parity.py --tokenizer` writes the Python token stream
    /// of every text file in the corpus as JSONL and points
    /// `ONTOSKILLS_TOKEN_SNAPSHOT` at it; this compares the Rust stream to it,
    /// document by document. It is `#[ignore]`d because it needs a corpus that
    /// is not in the repository, and it reads the text files directly rather
    /// than through `Kb`: this is the tokenizer's gate, and nothing else.
    #[test]
    #[ignore]
    fn g7_token_stream_matches_python() {
        let corpus = std::env::var("ONTOSKILLS_ROOT").expect("ONTOSKILLS_ROOT");
        let snapshot = std::env::var("ONTOSKILLS_TOKEN_SNAPSHOT").expect("ONTOSKILLS_TOKEN_SNAPSHOT");
        let rows = std::fs::read_to_string(&snapshot).expect("snapshot is readable");
        let mut checked = 0usize;
        let mut failures = Vec::new();
        for line in rows.lines().filter(|line| !line.trim().is_empty()) {
            let row: serde_json::Value = serde_json::from_str(line).expect("snapshot line is json");
            let doc_id = row["doc_id"].as_str().expect("doc_id");
            let expected = row["tokens"].as_str().expect("tokens");
            let path = Path::new(&corpus).join("text").join(format!("{doc_id}.txt"));
            let text = std::fs::read_to_string(&path).expect("text file");
            let got = tokens(&text).join(" ");
            if got != expected {
                failures.push(doc_id.to_string());
            }
            checked += 1;
        }
        assert!(checked > 0, "the snapshot is empty");
        assert!(
            failures.is_empty(),
            "{} of {checked} documents tokenise differently: {failures:?}",
            failures.len()
        );
    }

    #[test]
    fn a_statement_key_survives_case_and_typography() {
        assert_eq!(statement_key("The Party\u{2019}s Duty"), "the party's duty");
    }
}
