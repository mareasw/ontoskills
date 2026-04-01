use anyhow::Result;
use oxigraph::store::Store;
use std::env;
use std::fs;
use std::time::Instant;
use walkdir::WalkDir;

/// Benchmark results for a single query
#[derive(serde::Serialize)]
struct BenchResult {
    query_name: String,
    skill_count: usize,
    avg_us: u64,
    min_us: u64,
    max_us: u64,
    p50_us: u64,
    p99_us: u64,
    iterations: usize,
}

/// Overall benchmark report
#[derive(serde::Serialize)]
struct BenchReport {
    total_skills: usize,
    total_triples: usize,
    load_time_ms: u64,
    results: Vec<BenchResult>,
}

fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    let ttl_dir = args.get(1).map(|s| s.as_str()).unwrap_or("skills");
    let iterations: usize = args
        .get(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(1000);
    let output_path = args.get(3).map(|s| s.as_str()).unwrap_or("results/ontomcp-bench.json");

    println!("=== OntoMCP SPARQL Benchmark ===\n");

    // Load TTL files into oxigraph
    let store = Store::new()?;
    let start = Instant::now();

    let mut skill_count = 0usize;
    let mut loaded_files = 0usize;

    for entry in WalkDir::new(ttl_dir).into_iter().filter_map(|e| e.ok()) {
        let path = entry.path();
        if path.extension().map(|e| e == "ttl").unwrap_or(false) {
            let data = fs::read_to_string(path)?;
            match store.load_from_read(
                oxigraph::model::NamedNodeRef::new_unchecked("http://bench.ontoskills.sh/"),
                data.as_bytes(),
            ) {
                Ok(_) => {
                    loaded_files += 1;
                    skill_count += data.matches("a oc:Skill").count()
                        + data.matches("a <https://ontoskills.sh/ontology#Skill>").count();
                }
                Err(e) => eprintln!("Warning: failed to load {}: {}", path.display(), e),
            }
        }
    }

    let load_time = start.elapsed();

    // Count triples
    let total_triples: usize = {
        let count_query = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }";
        let results: Vec<_> = store.query(count_query)?.into_bindings().collect();
        results
            .first()
            .and_then(|r| r.get(0))
            .and_then(|v| v.to_string().parse().ok())
            .unwrap_or(0)
    };

    println!(
        "Loaded {} files ({} skills, {} triples) in {:.1}ms\n",
        loaded_files,
        skill_count.max(loaded_files),
        total_triples,
        load_time.as_secs_f64() * 1000.0,
    );

    // Define benchmark queries using the oc: namespace from core.ttl
    let oc = "https://ontoskills.sh/ontology#";

    let queries: Vec<(&str, String)> = vec![
        (
            "search_skills (by intent)",
            format!(
                r#"SELECT ?skill ?desc WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill <{oc}resolvesIntent> "create_pdf" .
                    OPTIONAL {{ ?skill <{oc}description> ?desc }}
                }}"#
            ),
        ),
        (
            "search_skills (by type)",
            format!(
                r#"SELECT ?skill WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill a <{oc}ExecutableSkill> .
                }}"#
            ),
        ),
        (
            "get_skill_context",
            format!(
                r#"SELECT ?p ?o WHERE {{
                    <http://ontoskills.sh/ontology/skill/pdf-generator> ?p ?o .
                }}"#
            ),
        ),
        (
            "query_epistemic_rules",
            format!(
                r#"SELECT ?node ?type ?content WHERE {{
                    ?node a <{oc}KnowledgeNode> .
                    ?node <{oc}knowledgeType> ?type .
                    ?node <{oc}directiveContent> ?content .
                }}"#
            ),
        ),
        (
            "evaluate_execution_plan",
            format!(
                r#"SELECT ?skill WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill <{oc}resolvesIntent> "create_pdf" .
                    ?skill <{oc}requiresState> ?req .
                }}"#
            ),
        ),
        (
            "search_skills (all — scan)",
            format!(
                r#"SELECT ?skill ?intent ?desc WHERE {{
                    ?skill a <{oc}Skill> .
                    OPTIONAL {{ ?skill <{oc}resolvesIntent> ?intent }}
                    OPTIONAL {{ ?skill <{oc}description> ?desc }}
                }}"#
            ),
        ),
    ];

    let mut results = Vec::new();

    for (name, query) in &queries {
        // Guard against iterations == 0 to avoid panic on empty times vec
        if iterations == 0 {
            println!("{:<35} skipped (0 iterations)", name);
            results.push(BenchResult {
                query_name: name.to_string(),
                skill_count: skill_count.max(loaded_files),
                avg_us: 0,
                min_us: 0,
                max_us: 0,
                p50_us: 0,
                p99_us: 0,
                iterations: 0,
            });
            continue;
        }

        let mut times = Vec::with_capacity(iterations);

        for _ in 0..iterations {
            let start = Instant::now();
            let _ = store.query(query.as_str());
            times.push(start.elapsed().as_micros() as u64);
        }

        times.sort_unstable();

        let avg = times.iter().sum::<u64>() / times.len() as u64;
        let min = times[0];
        let max = times[times.len() - 1];
        let p50 = times[times.len() * 50 / 100];
        let p99 = times[times.len() * 99 / 100];

        println!(
            "{:<35} avg={:>6}μs  p50={:>6}μs  p99={:>6}μs  min={:>5}μs  max={:>6}μs",
            name, avg, p50, p99, min, max
        );

        results.push(BenchResult {
            query_name: name.to_string(),
            skill_count: skill_count.max(loaded_files),
            avg_us: avg,
            min_us: min,
            max_us: max,
            p50_us: p50,
            p99_us: p99,
            iterations,
        });
    }

    let report = BenchReport {
        total_skills: skill_count.max(loaded_files),
        total_triples,
        load_time_ms: load_time.as_millis() as u64,
        results,
    };

    // Write JSON results
    if let Some(parent) = std::path::Path::new(output_path).parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(&report)?;
    fs::write(output_path, &json)?;
    println!("\nResults written to {}", output_path);

    Ok(())
}
