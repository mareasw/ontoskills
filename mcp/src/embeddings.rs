//! Embedding engine for semantic intent search.
//!
//! Uses pre-computed embeddings from Python export to perform
//! semantic search via cosine similarity.

use anyhow::Result;
use ndarray::Array1;
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Pre-computed intent embedding entry.
#[derive(Debug, Deserialize)]
struct IntentEntry {
    intent: String,
    embedding: Vec<f32>,
    skills: Vec<String>,
}

/// Intent embeddings file format.
#[derive(Debug, Deserialize)]
struct IntentsFile {
    #[allow(dead_code)]
    model: String,
    dimension: usize,
    intents: Vec<IntentEntry>,
}

/// Search result for intent matching.
#[derive(Debug, Serialize, Clone)]
pub struct IntentMatch {
    /// The intent string (e.g., "create_pdf")
    pub intent: String,
    /// Cosine similarity score
    pub score: f32,
    /// Skills that resolve this intent
    pub skills: Vec<String>,
}

/// Embedding engine for semantic intent search.
///
/// Uses pre-computed embeddings from `ontoskills export-embeddings`.
/// Currently supports exact string matching with pre-computed embeddings.
/// Future versions may add ONNX inference for true semantic search.
pub struct EmbeddingEngine {
    intents: Vec<(String, Array1<f32>, Vec<String>)>,
}

impl EmbeddingEngine {
    /// Load engine from embedding directory.
    ///
    /// # Arguments
    /// * `embeddings_dir` - Directory containing intents.json
    ///
    /// # Errors
    /// Returns error if intents.json is missing or invalid.
    pub fn load(embeddings_dir: &Path) -> Result<Self> {
        // Load pre-computed intents
        let intents_path = embeddings_dir.join("intents.json");
        if !intents_path.exists() {
            anyhow::bail!("Intents file not found at {:?}", intents_path);
        }

        let intents_file: IntentsFile =
            serde_json::from_str(&std::fs::read_to_string(&intents_path)?)?;

        let intents: Vec<(String, Array1<f32>, Vec<String>)> = intents_file
            .intents
            .into_iter()
            .map(|entry| {
                let emb = Array1::from_vec(entry.embedding);
                (entry.intent, emb, entry.skills)
            })
            .collect();

        Ok(Self { intents })
    }

    /// Search for intents matching the query.
    ///
    /// # Arguments
    /// * `query` - Natural language query
    /// * `top_k` - Maximum number of results
    ///
    /// # Returns
    /// List of matches sorted by similarity score (descending).
    ///
    /// # Note
    /// Currently performs substring matching. For true semantic search,
    /// ONNX inference needs to be implemented.
    pub fn search(&self, query: &str, top_k: usize) -> Result<Vec<IntentMatch>> {
        // Normalize query for matching
        let query_lower = query.to_lowercase();
        let query_words: Vec<&str> = query_lower.split_whitespace().collect();

        // Score each intent based on word overlap
        let mut scores: Vec<(f32, &str, &Vec<String>)> = self
            .intents
            .iter()
            .map(|(intent, _emb, skills)| {
                // Simple scoring: check if query words appear in intent
                let intent_lower = intent.to_lowercase().replace('_', " ");
                let intent_words: Vec<&str> = intent_lower.split_whitespace().collect();

                // Calculate word overlap score
                let mut score = 0.0f32;
                for q_word in &query_words {
                    for i_word in &intent_words {
                        if i_word.contains(q_word) || q_word.contains(i_word) {
                            score += 1.0;
                        }
                    }
                }

                // Normalize by query length
                if !query_words.is_empty() {
                    score /= query_words.len() as f32;
                }

                (score, intent.as_str(), skills)
            })
            .collect();

        // Sort by score descending
        scores.sort_by(|a, b| {
            b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal)
        });

        // Return top_k
        Ok(scores
            .into_iter()
            .take(top_k)
            .map(|(score, intent, skills)| IntentMatch {
                intent: intent.to_string(),
                score,
                skills: skills.clone(),
            })
            .collect())
    }

    /// Check if engine has any intents loaded.
    pub fn has_intents(&self) -> bool {
        !self.intents.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_embedding_engine_load_missing_files() {
        let result = EmbeddingEngine::load(Path::new("/nonexistent"));
        assert!(result.is_err());
    }
}
