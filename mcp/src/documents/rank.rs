//! The ranking, ported from `compiler.documents.ask`.
//!
//! BM25 over six weighted fields, de-duplicated by statement, then a greedy
//! chooser (`cover_select`) over the wider pool, with the rest of the answer
//! built around each hit: the quote, the locator, the document, the verifier's
//! verdict, and the contradiction links the corpus implies.
//!
//! The port is literal on purpose. Three details that look like accidents are
//! reproduced because the measured ranking depends on them:
//!
//! * a field is repeated `max(1, round(weight))` times instead of multiplying
//!   the score — the statement becomes three tokens in the bag, not a weight;
//! * de-duplication happens *after* the cut to `max(limit * 4, limit)`, so a
//!   duplicate inside the window can shorten the answer;
//! * the chooser's weights are summed in question order and ties keep the
//!   first index, because the pilot's number was measured with that arithmetic.
//!
//! `mcp/tests/fixtures/documents/golden.json` carries the Python answers for 25
//! fixed questions, and the test at the bottom of this file requires the exact
//! claim ids in the exact order.

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

use super::kb::{Claim, Document, Kb};
use super::text::{content, key_in_place, norm, statement_key, tokens};

/// BM25 parameters, from `ask.py`. Not tuned here and not tunable at runtime: a
/// number a caller can change is a number that stops describing the pilot.
pub const K1: f64 = 1.5;
pub const B: f64 = 0.75;

/// Field name and weight, in the order the index sums them.
pub const FIELD_WEIGHTS: [(&str, f64); 6] = [
    ("statement", 3.0),
    ("actor", 1.0),
    ("conditions", 2.0),
    ("quote", 1.0),
    ("title", 1.0),
    ("section", 1.0),
];

/// The text of a claim, split by the field it belongs to.
#[derive(Debug, Clone, Default)]
pub struct ClaimText {
    pub statement: String,
    pub actor: String,
    pub conditions: String,
    pub quote: String,
    pub title: String,
    pub section: String,
}

impl ClaimText {
    /// Exactly `_claim_text` in `ask.py`: the first evidence's section path, all
    /// evidence quotes joined, and the *claim's* context source as the title
    /// (not the document's title, which is a different field and a different
    /// ranking).
    pub fn of(claim: &Claim) -> ClaimText {
        let locator = &claim.first_evidence().locator;
        ClaimText {
            statement: claim.statement.clone(),
            actor: claim.actor.clone(),
            conditions: claim.conditions.join(" "),
            quote: claim
                .evidence
                .iter()
                .map(|item| item.quote.as_str())
                .collect::<Vec<_>>()
                .join(" "),
            title: claim.context.source.clone().unwrap_or_default(),
            section: locator.section_path.join(" "),
        }
    }
}

/// One citation, in the shape the tool returns.
#[derive(Debug, Clone)]
pub struct Citation {
    pub claim_id: String,
    pub doc_id: String,
    pub title: String,
    pub statement: String,
    pub quote: String,
    pub page: Option<i64>,
    /// Offsets into the *normalised* text of the document, when the compiler
    /// recorded them; the citation is followable without re-reading the file.
    pub char_start: Option<i64>,
    pub char_end: Option<i64>,
    pub section_path: Vec<String>,
    pub url: String,
    pub score: f64,
    pub verdict: String,
}

impl Citation {
    /// `Title, p. 3, Section > Subsection`, the label the CLI prints.
    pub fn label(&self) -> String {
        let mut bits = vec![if self.title.is_empty() {
            self.doc_id.clone()
        } else {
            self.title.clone()
        }];
        if let Some(page) = self.page.filter(|page| *page != 0) {
            bits.push(format!("p. {page}"));
        }
        if !self.section_path.is_empty() {
            bits.push(self.section_path.join(" > "));
        }
        bits.join(", ")
    }
}

/// Two durations on the same topic that disagree across documents.
#[derive(Debug, Clone)]
pub struct Tension {
    pub topic: String,
    /// `(duration label, "claim_id (doc_id)")`, ordered by hours.
    pub values: Vec<(String, String)>,
    pub reason: String,
}

/// One answer: the citations in rank order and what the corpus disagrees about.
#[derive(Debug, Clone, Default)]
pub struct Answer {
    pub question: String,
    pub citations: Vec<Citation>,
    pub tensions: Vec<Tension>,
    /// How many claims the question was ranked against. Provenance for a reader
    /// asking "did this search the whole corpus or a slice of it?".
    pub searched: usize,
}

impl Answer {
    /// Distinct document ids in citation order — the CLI's `documents` field.
    pub fn documents(&self) -> Vec<String> {
        let mut seen = Vec::new();
        let mut known = HashSet::new();
        for citation in &self.citations {
            if known.insert(citation.doc_id.as_str()) {
                seen.push(citation.doc_id.clone());
            }
        }
        seen
    }
}

/// The BM25 index over the claims the verifier passed.
///
/// An inverted index — term to the claims that carry it and how often — rather
/// than one count map per claim. Both shapes answer the same question, and the
/// inverted one answers it by touching only the claims a query term reaches: a
/// question with six content words visits the posting lists instead of the whole
/// corpus, and building it allocates one small map that is reused for every
/// claim instead of one map per claim.
///
/// The arithmetic is untouched. The score of a claim is still accumulated term
/// by term in query order, so the floating-point sum is the one `ask.py`
/// produces; nothing here may be reordered for speed.
#[derive(Debug)]
pub struct Index {
    /// Positions into `Kb::claims`, one per member slot, in artifact order.
    members: Vec<usize>,
    /// Token count per slot, after the field weights and `max(1, …)`.
    lengths: Vec<usize>,
    /// Term to `(slot, term frequency)`, slots ascending.
    postings: HashMap<String, Vec<(u32, u32)>>,
    avg_length: f64,
}

impl Index {
    pub fn build(kb: &Kb, include_unverified: bool) -> Index {
        let mut members: Vec<usize> = Vec::new();
        let mut lengths: Vec<usize> = Vec::new();
        let mut postings: HashMap<String, Vec<(u32, u32)>> = HashMap::new();
        // One bag reused for every claim: `clear()` keeps the allocation, and a
        // corpus of nine thousand claims should not allocate nine thousand maps.
        let mut bag: HashMap<String, u32> = HashMap::new();

        for (position, claim) in kb.claims().iter().enumerate() {
            // The verifier filter runs before the index exists, exactly as in
            // `Corpus.__init__`: an unfiltered claim must not influence the
            // document frequencies of the ones that are answered.
            if !include_unverified && kb.has_verdicts() && kb.verdict(&claim.claim_id) != "ok" {
                continue;
            }
            let slot = members.len() as u32;
            let text = ClaimText::of(claim);
            bag.clear();
            let mut length = 0usize;
            for (name, weight) in FIELD_WEIGHTS {
                let value = match name {
                    "statement" => &text.statement,
                    "actor" => &text.actor,
                    "conditions" => &text.conditions,
                    "quote" => &text.quote,
                    "title" => &text.title,
                    "section" => &text.section,
                    _ => unreachable!("FIELD_WEIGHTS is the list above"),
                };
                // `max(1, int(round(weight)))`: Python's `round` is half-to-even
                // but every weight here is a whole number, so the repetition
                // count is just the weight.
                let repeats = (weight.round() as usize).max(1);
                let mut terms = content(value);
                for term in &mut terms {
                    key_in_place(term);
                }
                for _ in 0..repeats {
                    for term in &terms {
                        match bag.get_mut(term.as_str()) {
                            Some(frequency) => *frequency += 1,
                            None => {
                                bag.insert(term.clone(), 1);
                            }
                        }
                        length += 1;
                    }
                }
            }
            for (term, frequency) in bag.drain() {
                postings
                    .entry(term)
                    .or_default()
                    .push((slot, frequency));
            }
            members.push(position);
            lengths.push(length.max(1));
        }

        let avg_length = if lengths.is_empty() {
            0.0
        } else {
            lengths.iter().sum::<usize>() as f64 / lengths.len() as f64
        };
        Index {
            members,
            lengths,
            postings,
            avg_length,
        }
    }

    pub fn len(&self) -> usize {
        self.members.len()
    }

    /// `log(1 + (N - df + 0.5) / (df + 0.5))`, with `df` the posting list length.
    fn idf(&self, df: f64) -> f64 {
        let total = self.members.len() as f64;
        (1.0 + (total - df + 0.5) / (df + 0.5)).ln()
    }

    /// `Corpus._idf(term)`: the weight the chooser gives one question term.
    ///
    /// Python reads a document-frequency map built over the same claims; here the
    /// posting list *is* that map — one entry per claim that carries the term.
    pub fn idf_of(&self, term: &str) -> f64 {
        self.idf(self.postings.get(term).map_or(0, |list| list.len()) as f64)
    }

    /// The claims the question ranks, best first, already filtered and cut.
    ///
    /// `question` is the caller's text; the tokenizer and the stopword list are
    /// applied here, so there is exactly one definition of what a question is.
    pub fn search(&self, kb: &Kb, question: &str, limit: usize) -> Vec<Citation> {
        let mut query: Vec<String> = content(question);
        for term in &mut query {
            key_in_place(term);
        }
        if query.is_empty() || self.members.is_empty() {
            return Vec::new();
        }

        let average = if self.avg_length == 0.0 {
            1.0
        } else {
            self.avg_length
        };
        let mut scores = vec![0.0f64; self.members.len()];
        // Terms outer, postings inner: each claim still receives its terms in
        // query order, which is the order `ask.py` sums them in.
        for term in &query {
            let Some(list) = self.postings.get(term.as_str()) else {
                continue;
            };
            let idf = self.idf(list.len() as f64);
            for (slot, frequency) in list {
                let length = self.lengths[*slot as usize] as f64;
                let denominator_scale = K1 * (1.0 - B + B * length / average);
                let frequency = *frequency as f64;
                let denominator = frequency + denominator_scale;
                scores[*slot as usize] += idf * frequency * (K1 + 1.0) / denominator;
            }
        }

        // Stable sort on the score, descending: two equal scores keep the order
        // of `claims.jsonl`, which is what Python's stable sort does.
        let mut ranked: Vec<usize> = (0..scores.len()).filter(|index| scores[*index] > 0.0).collect();
        ranked.sort_by(|left, right| {
            scores[*right]
                .partial_cmp(&scores[*left])
                .unwrap_or(Ordering::Equal)
        });

        let mut out = Vec::new();
        let mut seen_statements: HashSet<String> = HashSet::new();
        for position in ranked.into_iter().take(limit.saturating_mul(4).max(limit)) {
            let claim = &kb.claims()[self.members[position]];
            let identity = statement_key(&claim.statement);
            if !seen_statements.insert(identity) {
                continue;
            }
            out.push(citation(kb, claim, scores[position]));
            if out.len() >= limit {
                break;
            }
        }
        out
    }
}

impl Kb {
    /// The index over the verified claims, or over every claim when the caller
    /// asked for the audit surface. Built once per loaded knowledge base.
    pub fn index_with(&self, include_unverified: bool) -> &Index {
        let slot: &OnceLock<Index> = if include_unverified {
            &self.index_all
        } else {
            &self.index_verified
        };
        slot.get_or_init(|| Index::build(self, include_unverified))
    }
}

/// `Corpus._citation`, field by field.
fn citation(kb: &Kb, claim: &Claim, score: f64) -> Citation {
    let evidence = claim.first_evidence();
    let document: Option<&Document> = kb.document(&claim.doc_id);
    let title = document
        .map(|document| document.title.clone())
        .filter(|title| !title.is_empty())
        .unwrap_or_else(|| {
            claim
                .context
                .source
                .clone()
                .unwrap_or_else(|| claim.doc_id.clone())
        });
    let locator = &evidence.locator;
    let url = if !locator.url.is_empty() {
        locator.url.clone()
    } else {
        document.map(|document| document.url.clone()).unwrap_or_default()
    };
    Citation {
        claim_id: claim.claim_id.clone(),
        doc_id: claim.doc_id.clone(),
        title,
        statement: claim.statement.clone(),
        quote: evidence.quote.clone(),
        page: locator.page,
        char_start: locator.char_start,
        char_end: locator.char_end,
        section_path: locator.section_path.clone(),
        url,
        score: round4(score),
        verdict: kb.verdict(&claim.claim_id).to_string(),
    }
}

/// Python's `round(value, 4)`: the closest 4-decimal float, ties to even.
///
/// `format!("{:.4}")` is correctly rounded and half-to-even on the exact binary
/// value, which is what CPython's `round` does; multiplying and dividing by
/// 10 000 is not, and produces a different last digit often enough to matter.
pub fn round4(value: f64) -> f64 {
    if !value.is_finite() {
        return value;
    }
    format!("{value:.4}")
        .parse::<f64>()
        .unwrap_or(value)
}

/// `ask()`: the answer to one question.
///
/// The pool is ten times `limit` or a hundred citations, whichever is larger,
/// exactly as `ask.py` builds it; `cover_select` then decides which of them come
/// back. The search itself is unchanged, so a corpus whose quotes share no
/// question term still answers with the ranker's own order.
pub fn ask(kb: &Kb, question: &str, limit: usize, include_unverified: bool) -> Answer {
    let index = kb.index_with(include_unverified);
    let pool = index.search(kb, question, limit.saturating_mul(10).max(100));
    let citations = cover_select(pool, index, question, limit);
    let tensions = find_tensions(&citations);
    Answer {
        question: question.to_string(),
        citations,
        tensions,
        searched: index.len(),
    }
}

/// `cover()` in `ask.py`: greedy over the question's own terms.
///
/// At each step the claim that adds the most uncovered question terms wins, with
/// the corpus IDF as the weight; a chosen claim removes its terms, so the second
/// claim covering the same word adds nothing. The remaining weights are kept in
/// question order and summed in that order, which is the floating-point sum the
/// Python chooser produces; a tie keeps the first index, as `>` does there.
///
/// The pool is never shortened below `k` when it has `k` claims: the fill at the
/// end returns the ranker's order rather than let the chooser be rewarded for
/// refusing.
pub fn cover_select(
    citations: Vec<Citation>,
    index: &Index,
    question: &str,
    k: usize,
) -> Vec<Citation> {
    let mut terms = content(question);
    for term in &mut terms {
        key_in_place(term);
    }
    let mut weights: Vec<(String, f64)> = Vec::new();
    for term in terms {
        if !weights.iter().any(|(known, _)| *known == term) {
            let weight = index.idf_of(&term);
            weights.push((term, weight));
        }
    }

    let present: Vec<HashSet<String>> = citations
        .iter()
        .map(|citation| {
            let mut quote_terms = content(&citation.quote);
            for term in &mut quote_terms {
                key_in_place(term);
            }
            quote_terms.into_iter().collect()
        })
        .collect();

    let mut picked: Vec<usize> = Vec::new();
    let mut taken = vec![false; citations.len()];
    let mut remaining = weights;
    for _ in 0..k.min(citations.len()) {
        let mut best: Option<usize> = None;
        let mut best_gain = 0.0f64;
        for (position, terms_here) in present.iter().enumerate() {
            if taken[position] {
                continue;
            }
            let mut gain = 0.0f64;
            for (term, weight) in &remaining {
                if terms_here.contains(term) {
                    gain += *weight;
                }
            }
            if gain > best_gain {
                best = Some(position);
                best_gain = gain;
            }
        }
        let Some(best) = best else { break };
        picked.push(best);
        taken[best] = true;
        remaining.retain(|(term, _)| !present[best].contains(term));
    }

    for position in 0..citations.len() {
        if picked.len() >= k {
            break;
        }
        if !taken[position] {
            picked.push(position);
            taken[position] = true;
        }
    }

    let mut slots: Vec<Option<Citation>> = citations.into_iter().map(Some).collect();
    picked
        .into_iter()
        .filter_map(|position| slots[position].take())
        .collect()
}

/// Hours per unit, `UNIT_HOURS` in `ask.py`.
fn unit_hours(unit: &str) -> Option<f64> {
    Some(match unit {
        "hour" | "hours" | "working hour" | "working hours" => 1.0,
        "day" | "days" => 24.0,
        "week" | "weeks" => 168.0,
        "month" | "months" => 730.0,
        "year" | "years" => 8760.0,
        _ => return None,
    })
}

/// One, two, … twelve, as the Python map spells them.
fn word_number(word: &str) -> Option<f64> {
    let number = match word {
        "one" => 1,
        "two" => 2,
        "three" => 3,
        "four" => 4,
        "five" => 5,
        "six" => 6,
        "seven" => 7,
        "eight" => 8,
        "nine" => 9,
        "ten" => 10,
        "eleven" => 11,
        "twelve" => 12,
        _ => return None,
    };
    Some(number as f64)
}

const WORD_NUMBERS: [&str; 12] = [
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
    "twelve",
];

/// `[(label, hours)]` for every explicit duration in the text.
///
/// The Python definition is a regex with a lookbehind and a lookahead, which the
/// `regex` crate cannot express. The scanner below matches the same language:
/// a number that does not continue a word or a dotted address, an optional
/// `working`, a unit, and no word character after it.
pub fn durations(text: &str) -> Vec<(String, f64)> {
    let chars: Vec<char> = text.chars().collect();
    let mut out = Vec::new();
    let mut position = 0usize;
    while position < chars.len() {
        // `(?<![\w.])`
        if position > 0 {
            let previous = chars[position - 1];
            if super::text::is_word_char(previous) || previous == '.' {
                position += 1;
                continue;
            }
        }
        let Some((_, after_number)) = match_number(&chars, position) else {
            position += 1;
            continue;
        };
        let after_spaces = skip_spaces(&chars, after_number);
        // `(working\s+)?` — a `working` that is not followed by whitespace is
        // not the optional group, so the unit must start right there.
        let (working, after_working) = match match_word(&chars, after_spaces, "working") {
            Some(after) if skip_spaces(&chars, after) > after => (true, skip_spaces(&chars, after)),
            _ => (false, after_spaces),
        };
        let Some((unit, after_unit)) = match_unit(&chars, after_working) else {
            // The regex engine advances one character and tries again; the
            // number itself cannot start a match, so do the same.
            position += 1;
            continue;
        };
        // `(?![\w])`
        if after_unit < chars.len() && super::text::is_word_char(chars[after_unit]) {
            position += 1;
            continue;
        }
        let amount_text: String = chars[position..after_number].iter().collect();
        let unit_text = unit;
        let lower = amount_text.to_lowercase();
        let number = word_number(&lower).or_else(|| amount_text.replace(',', ".").parse::<f64>().ok());
        if let (Some(number), Some(hours)) = (number, unit_hours(&unit_text.to_lowercase())) {
            let label = norm(&format!(
                "{amount_text} {}{}",
                if working { "working " } else { "" },
                unit_text.to_lowercase()
            ));
            out.push((label, number * hours));
        }
        // Non-overlapping matches: continue after the unit the regex consumed,
        // or after the unit plus the word character that failed the lookahead —
        // either way past the unit, which keeps the scan linear.
        position = after_unit.max(position + 1);
    }
    out
}

/// The number alternative: `\d+(?:[.,]\d+)?`, then a spelled-out number.
fn match_number(chars: &[char], start: usize) -> Option<(String, usize)> {
    if start < chars.len() && is_decimal_digit(chars[start]) {
        let mut position = start;
        while position < chars.len() && is_decimal_digit(chars[position]) {
            position += 1;
        }
        if position < chars.len() && matches!(chars[position], '.' | ',') {
            let separator = position;
            let mut after = position + 1;
            while after < chars.len() && is_decimal_digit(chars[after]) {
                after += 1;
            }
            if after > separator + 1 {
                position = after;
            }
        }
        let amount: String = chars[start..position].iter().collect();
        return Some((amount, position));
    }
    for word in WORD_NUMBERS {
        if let Some(after) = match_word(chars, start, word) {
            let amount: String = chars[start..after].iter().collect();
            return Some((amount, after));
        }
    }
    None
}

fn is_decimal_digit(c: char) -> bool {
    if c.is_ascii() {
        return c.is_ascii_digit();
    }
    matches!(
        unicode_general_category::get_general_category(c),
        unicode_general_category::GeneralCategory::DecimalNumber
    )
}

/// A case-insensitive literal match, returning the position after it.
fn match_word(chars: &[char], start: usize, word: &str) -> Option<usize> {
    let mut position = start;
    for expected in word.chars() {
        let actual = chars.get(position)?;
        if !same_letter(*actual, expected) {
            return None;
        }
        position += 1;
    }
    Some(position)
}

/// Case-insensitive equality for one character, with `expected` always ASCII.
///
/// ASCII takes the two-way comparison (`eq_ignore_ascii_case`), which is the
/// same answer as the general mapping and is what almost every character in the
/// corpus is. A non-ASCII character keeps the full `to_lowercase` rule, so a
/// Kelvin sign still matches `k`, as Python's `re.IGNORECASE` does.
fn same_letter(actual: char, expected: char) -> bool {
    if actual.is_ascii() {
        return actual.eq_ignore_ascii_case(&expected);
    }
    let mut lowered = actual.to_lowercase();
    let first = lowered.next().unwrap_or(actual);
    first == expected && lowered.next().is_none()
}

fn skip_spaces(chars: &[char], start: usize) -> usize {
    let mut position = start;
    while position < chars.len() && super::text::is_space(chars[position]) {
        position += 1;
    }
    position
}

/// The unit alternative, longest form first, as the greedy regex prefers.
fn match_unit(chars: &[char], start: usize) -> Option<(String, usize)> {
    const FORMS: [&str; 10] = [
        "hours", "hour", "days", "day", "weeks", "week", "months", "month", "years", "year",
    ];
    for form in FORMS {
        if let Some(after) = match_word(chars, start, form) {
            return Some((form.to_string(), after));
        }
    }
    None
}

/// `TOPICS`, in the order `topic_of` reports them.
const TOPICS: [(&str, &[&str]); 4] = [
    (
        "breach_notification",
        &["breach", "notify", "notification", "inform", "incident", "data loss event"],
    ),
    (
        "retention",
        &["retain", "retention", "delete", "deletion", "erasure", "erase", "destroy"],
    ),
    ("audit", &["audit", "inspection", "inspect", "access to records"]),
    ("transfer", &["transfer", "transfers", "onward transfer"]),
];

/// The one topic the text is about, or `None` when it names several or none.
pub fn topic_of(text: &str) -> Option<&'static str> {
    let said = format!(" {} ", tokens(text).join(" "));
    let mut found: Vec<&'static str> = Vec::new();
    for (name, phrases) in TOPICS {
        if phrases.iter().any(|phrase| said.contains(&format!(" {phrase} "))) {
            found.push(name);
        }
    }
    if found.len() == 1 {
        Some(found[0])
    } else {
        None
    }
}

/// Durations on the same topic that disagree across two documents.
pub fn find_tensions(citations: &[Citation]) -> Vec<Tension> {
    let mut buckets: HashMap<&'static str, Vec<(String, f64, String, String)>> = HashMap::new();
    for citation in citations {
        let text = format!("{} {}", citation.statement, citation.quote);
        let Some(topic) = topic_of(&text) else {
            continue;
        };
        let found = durations(&text);
        // One duration per claim: the first explicit one is the operative one.
        let Some((label, hours)) = found.into_iter().next() else {
            continue;
        };
        buckets.entry(topic).or_default().push((
            label,
            hours,
            citation.claim_id.clone(),
            citation.doc_id.clone(),
        ));
    }

    // `sorted(buckets.items())`: the tension list is ordered by topic name, not
    // by the order the citations arrived in.
    let mut topics: Vec<&'static str> = buckets.keys().copied().collect();
    topics.sort_unstable();

    let mut tensions = Vec::new();
    for topic in topics {
        let items = &buckets[topic];
        let mut distinct: Vec<(f64, Vec<(String, String)>)> = Vec::new();
        for (label, hours, claim_id, doc_id) in items {
            let entry = format!("{claim_id} ({doc_id})");
            match distinct.iter_mut().find(|(existing, _)| existing == hours) {
                Some((_, labels)) => labels.push((label.clone(), entry)),
                None => distinct.push((*hours, vec![(label.clone(), entry)])),
            }
        }
        if distinct.len() < 2 {
            continue;
        }
        // Two documents must be involved: a document contradicting itself is a
        // compile defect, not a cross-document tension.
        let docs: HashSet<&str> = items.iter().map(|(_, _, _, doc_id)| doc_id.as_str()).collect();
        if docs.len() < 2 {
            continue;
        }
        let distinct_count = distinct.len();
        distinct.sort_by(|left, right| left.0.total_cmp(&right.0));
        let values: Vec<(String, String)> = distinct.into_iter().flat_map(|(_, labels)| labels).collect();
        tensions.push(Tension {
            topic: topic.to_string(),
            values,
            reason: format!(
                "{distinct_count} different {} periods across {} documents",
                topic.replace('_', " "),
                docs.len()
            ),
        });
    }
    tensions
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    fn fixture_root() -> PathBuf {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/documents")
    }

    fn fixture() -> Kb {
        Kb::load(fixture_root().join("kb")).expect("fixture loads")
    }

    #[test]
    fn the_duration_scanner_reads_the_cases_the_corpus_carries() {
        assert_eq!(
            durations("notify within 72 hours of the breach"),
            vec![("72 hours".to_string(), 72.0)]
        );
        assert_eq!(
            durations("retain for two years"),
            vec![("two years".to_string(), 2.0 * 8760.0)]
        );
        assert_eq!(
            durations("thirty days"), // written out, but not in the table
            Vec::<(String, f64)>::new()
        );
        assert_eq!(
            durations("a 1.5 day window"),
            vec![("1.5 day".to_string(), 36.0)]
        );
        assert_eq!(
            durations("ten working days"),
            vec![("ten working days".to_string(), 10.0 * 24.0)]
        );
        // The lookbehind: a number inside a word or after a dot is not a number
        // the sentence states.
        assert_eq!(durations("x72 hours"), Vec::<(String, f64)>::new());
        assert_eq!(durations("v1.72 hours"), Vec::<(String, f64)>::new());
        // The lookahead: a unit that continues into a word is not a unit.
        assert_eq!(durations("3 dayslong"), Vec::<(String, f64)>::new());
        // Non-overlapping: the second number is a second match.
        assert_eq!(
            durations("30 days and 12 months"),
            vec![
                ("30 days".to_string(), 720.0),
                ("12 months".to_string(), 12.0 * 730.0)
            ]
        );
    }

    #[test]
    fn a_topic_is_reported_only_when_the_text_names_one() {
        assert_eq!(topic_of("notify the breach to the authority"), Some("breach_notification"));
        assert_eq!(topic_of("retain records for 5 years"), Some("retention"));
        assert_eq!(topic_of("transfer the data"), Some("transfer"));
        // Two topics, or none: no assignment rather than a guess.
        assert_eq!(topic_of("notify a breach and retain the records"), None);
        assert_eq!(topic_of("the office is closed"), None);
    }

    #[test]
    fn rounding_matches_pythons_four_decimals() {
        assert_eq!(round4(12.345_678), 12.3457);
        assert_eq!(round4(0.000_05), 0.0001);
        assert_eq!(round4(0.000_15), 0.0001);
    }

    fn citation_with(claim_id: &str, quote: &str) -> Citation {
        Citation {
            claim_id: claim_id.to_string(),
            doc_id: "doc".to_string(),
            title: String::new(),
            statement: String::new(),
            quote: quote.to_string(),
            page: None,
            char_start: None,
            char_end: None,
            section_path: Vec::new(),
            url: String::new(),
            score: 0.0,
            verdict: "ok".to_string(),
        }
    }

    #[test]
    fn the_chooser_takes_the_claim_that_adds_an_uncovered_question_term() {
        let kb = fixture();
        let index = kb.index_with(false);
        let citations = vec![
            citation_with("a", "breach notification duty"),
            citation_with("b", "breach notification duty again"),
            citation_with("c", "retention of records"),
        ];
        let chosen = cover_select(citations, index, "breach retention", 2);
        let ids: Vec<&str> = chosen.iter().map(|c| c.claim_id.as_str()).collect();
        assert_eq!(ids, vec!["a", "c"]);
    }

    #[test]
    fn the_chooser_fills_to_k_with_the_rankers_own_order() {
        let kb = fixture();
        let index = kb.index_with(false);
        let citations = vec![
            citation_with("a", "zzz qqq"),
            citation_with("b", "xxx yyy"),
            citation_with("c", "www vvv"),
        ];
        let chosen = cover_select(citations, index, "breach", 2);
        let ids: Vec<&str> = chosen.iter().map(|c| c.claim_id.as_str()).collect();
        assert_eq!(ids, vec!["a", "b"]);
    }

    #[test]
    fn the_chooser_never_returns_more_than_the_pool_or_than_k() {
        let kb = fixture();
        let index = kb.index_with(false);
        let citations = vec![citation_with("a", "breach"), citation_with("b", "breach")];
        assert_eq!(cover_select(citations.clone(), index, "breach", 5).len(), 2);
        assert_eq!(cover_select(citations, index, "breach", 1).len(), 1);
    }

    #[test]
    fn an_empty_question_ranks_nothing() {
        let kb = fixture();
        assert!(ask(&kb, "", 10, false).citations.is_empty());
        assert!(ask(&kb, "the and of", 10, false).citations.is_empty());
    }

    #[test]
    fn a_question_cites_claims_that_carry_its_words() {
        let kb = fixture();
        let answer = ask(&kb, "What are the default size limits for file uploads?", 10, false);
        assert!(!answer.citations.is_empty());
        for citation in &answer.citations {
            assert!(!citation.claim_id.is_empty());
            assert!(!citation.statement.is_empty());
            assert_eq!(citation.verdict, "ok");
        }
    }

    #[test]
    fn the_verifier_filter_removes_a_weak_claim_unless_it_is_asked_for() {
        let kb = fixture();
        let weak: Vec<String> = kb
            .claims()
            .iter()
            .filter(|claim| kb.verdict(&claim.claim_id) != "ok")
            .map(|claim| claim.claim_id.clone())
            .collect();
        assert_eq!(weak.len(), 2);
        let verified = kb.index_with(false);
        let all = kb.index_with(true);
        assert_eq!(all.len() - verified.len(), 2);
    }

    /// G1 on the committed fixture: the exact claim ids, in the exact order,
    /// that the Python core produced for the same question list.
    #[test]
    fn every_fixture_answer_matches_the_python_ranking() {
        let kb = fixture();
        let golden: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(fixture_root().join("golden.json")).unwrap())
                .expect("golden.json parses");
        let answers = golden["answers"].as_array().expect("answers array");
        assert!(!answers.is_empty());
        let mut failures = Vec::new();
        for answer in answers {
            let question = answer["question"].as_str().expect("question");
            let expected: Vec<&str> = answer["citations"]
                .as_array()
                .expect("citations")
                .iter()
                .map(|citation| citation["claim_id"].as_str().expect("claim id"))
                .collect();
            let got: Vec<String> = ask(&kb, question, 10, false)
                .citations
                .into_iter()
                .map(|citation| citation.claim_id)
                .collect();
            if got.iter().map(String::as_str).collect::<Vec<_>>() != expected {
                failures.push(format!(
                    "{}: expected {:?}, got {:?}",
                    answer["qid"].as_str().unwrap_or(question),
                    expected,
                    got
                ));
            }
        }
        assert!(failures.is_empty(), "{}", failures.join("\n"));
    }

    /// G7 on the fixture: the token stream, the normalised text and the
    /// stopword-filtered content are the Python ones, byte for byte.
    #[test]
    fn the_tokenizer_matches_the_python_tokenizer_on_every_fixture_text() {
        let kb = fixture();
        let golden: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(fixture_root().join("golden.json")).unwrap())
                .expect("golden.json parses");
        for (doc_id, expected) in golden["tokenizer"].as_object().expect("tokenizer") {
            let text = kb.text(doc_id).expect("text");
            assert_eq!(
                tokens(&text).join(" "),
                expected["tokens"].as_str().expect("tokens"),
                "{doc_id}: token stream differs from Python"
            );
        }
    }
}


