# Spiegazione Completa Del Progetto OntoClaw

## 1. Cos'e questo progetto

OntoClaw e un compilatore semantico per skill di agenti AI. L'idea centrale e questa:

- input: una o piu cartelle che contengono uno `SKILL.md`
- elaborazione: un LLM legge il contenuto della skill e lo trasforma in una struttura dati rigorosa
- output: quella struttura viene serializzata come ontologia OWL 2 in RDF/Turtle
- garanzia: prima della scrittura, il grafo viene validato con SHACL

In pratica il progetto prova a trasformare descrizioni testuali di skill in un knowledge graph interrogabile via SPARQL, cosi un agente o un sistema esterno non deve rileggere ogni file Markdown per capire:

- cosa fa una skill
- quali intent risolve
- da quali altre skill dipende
- quali stati richiede o produce
- se ha codice eseguibile oppure no

Il repository oggi contiene soprattutto il compilatore Python. La parte `mcp/` e solo annunciata come lavoro futuro.

## 2. Struttura reale del repository

### Radice

- `README.md`: overview prodotto, posizionamento, installazione e CLI
- `PHILOSOPHY.md`: motivazione teorica e visione neuro-symbolic
- `CHANGELOG.md`: cronologia modifiche
- `LICENSE`: licenza MIT
- `specs/ontoclaw.shacl.ttl`: regole SHACL che definiscono i vincoli costituzionali dell'ontologia
- `mcp/README.md`: descrive un futuro server MCP in Rust, non ancora implementato
- `assets/logo.png`: asset grafico

### Package principale

La directory importante e `compiler/`. Contiene:

- codice applicativo
- entrypoint CLI
- modelli Pydantic
- serializzazione RDF
- validazione SHACL
- sicurezza
- query SPARQL
- test

## 3. Obiettivo architetturale

Il progetto vuole risolvere un problema specifico: i file `SKILL.md` sono facili da scrivere ma difficili da interrogare in modo affidabile.

Con il solo testo:

- cercare skill per intento richiede scansione completa dei documenti
- capire dipendenze o conflitti richiede parsing implicito del linguaggio naturale
- la risposta di un LLM puo cambiare da una run all'altra

Con OntoClaw:

- il testo viene interpretato una volta
- l'output diventa un grafo semantico
- il grafo puo essere validato, salvato, versionato e interrogato

La pipeline e neuro-symbolic:

- neuro: Claude estrae la struttura dal linguaggio naturale
- symbolic: RDF + OWL 2 rappresentano la conoscenza in modo formale
- constitutional layer: SHACL blocca output invalidi
- retrieval layer: SPARQL risponde a query precise

## 4. Flusso completo end-to-end

Il flusso reale del compilatore e questo.

### 4.1 Scoperta delle skill

La CLI cerca directory che contengono `SKILL.md`.

Codice coinvolto:

- `compiler/cli.py`

Comportamento:

- se passi `ontoclaw compile nome-skill`, compila solo quella directory
- se non passi un nome, esplora ricorsivamente la directory input
- considera skill valida ogni cartella che contiene `SKILL.md`

### 4.2 Generazione identificatore e hash

Codice coinvolto:

- `compiler/extractor.py`

Funzioni:

- `generate_skill_id(directory_name)`: crea uno slug dal nome cartella
- `compute_skill_hash(skill_dir)`: calcola uno SHA-256 di tutti i file della skill

Perche serve:

- `id`: identificatore umano stabile e leggibile
- `hash`: identificatore del contenuto per capire se la skill e cambiata

Dettagli:

- lo slug normalizza spazi e underscore in trattini
- rimuove caratteri non alfanumerici
- tronca a 64 caratteri
- l'hash include sia path relativi sia contenuto dei file

### 4.3 Caching basato su hash

Prima di ricompilare una skill, la CLI controlla se esiste gia un file `skill.ttl` corrispondente e prova a leggere il valore `oc:contentHash`.

Se l'hash coincide:

- la skill viene saltata
- a meno che non si usi `--force`

Questo riduce chiamate inutili al modello.

### 4.4 Security check prima dell'estrazione

Codice coinvolto:

- `compiler/security.py`

Pipeline:

1. normalizzazione del testo
2. rilevamento pattern rischiosi con regex
3. opzionale revisione LLM-as-judge

Tipi di minaccia cercati:

- prompt injection
- command injection
- data exfiltration
- path traversal
- credential exposure

Comportamento:

- se trova pattern e `skip_llm=False`, chiede conferma al modello di sicurezza
- se il giudizio finale non e sicuro, blocca la skill
- se usi `--skip-security`, la review LLM viene saltata, ma pattern trovati bloccano comunque il contenuto

Nota importante:

- la flag `--skip-security` nel codice non significa "salta ogni controllo"
- significa in pratica "non fare la review LLM"
- il controllo regex resta

### 4.5 Estrazione strutturata con Claude

Codice coinvolto:

- `compiler/transformer.py`
- `compiler/schemas.py`

Questa e la parte piu centrale del progetto.

Il modulo `transformer.py` apre una conversazione tool-use con Anthropic.

Tool esposti al modello:

- `list_files`: lista i file della skill
- `read_file`: legge un file relativo alla skill
- `extract_skill`: consegna il risultato strutturato finale

Il prompt di sistema impone una griglia concettuale:

- Knowledge Architecture
- distinzione genus / differentia
- relazioni come `depends_on`, `extends`, `contradicts`
- estrazione di stati `requiresState`, `yieldsState`, `handlesFailure`

Il modello puo leggere `SKILL.md` e file di supporto nella stessa cartella, poi deve produrre un oggetto conforme a `ExtractedSkill`.

### 4.6 Modello dati interno

Codice coinvolto:

- `compiler/schemas.py`

I modelli principali sono:

#### `Requirement`

Campi:

- `type`: uno tra `EnvVar`, `Tool`, `Hardware`, `API`, `Knowledge`
- `value`: valore del requisito
- `optional`: booleano

#### `ExecutionPayload`

Campi:

- `executor`: uno tra `shell`, `python`, `node`, `claude_tool`
- `code`: codice da eseguire
- `timeout`: opzionale

#### `StateTransition`

Campi:

- `requires_state`
- `yields_state`
- `handles_failure`

Vincolo:

- ogni URI di stato deve rispettare il pattern `oc:[A-Z][a-zA-Z0-9]*`

#### `ExtractedSkill`

Campi principali:

- `id`
- `hash`
- `nature`
- `genus`
- `differentia`
- `intents`
- `requirements`
- `depends_on`
- `extends`
- `contradicts`
- `state_transitions`
- `generated_by`
- `execution_payload`
- `provenance`

Campo derivato:

- `skill_type`
  - `executable` se esiste `execution_payload`
  - `declarative` altrimenti

Comportamento utile:

- se il modello restituisce `state_transitions` o `execution_payload` come stringhe JSON, i validator cercano di parsarle automaticamente

### 4.7 Arricchimento dei metadati

Dentro `tool_use_loop()` il risultato del modello viene corretto dal compilatore:

- `id` viene sostituito con quello calcolato localmente
- `hash` viene sostituito con quello calcolato localmente
- `provenance` diventa il path della directory della skill
- `generated_by` viene forzato al nome del modello configurato

Questa scelta e sensata: evita che il modello menta o sbagli su id, hash o provenienza.

### 4.8 Serializzazione RDF/OWL

Codice coinvolto:

- `compiler/serialization.py`

Funzione chiave:

- `serialize_skill(graph, skill)`

Cosa genera:

- una risorsa skill `oc:skill_<hashprefix>`
- tipo RDF `oc:Skill`
- sottotipo `oc:ExecutableSkill` oppure `oc:DeclarativeSkill`
- identificatore `dcterms:identifier`
- `oc:contentHash`
- `oc:nature`
- `skos:broader` per il `genus`
- `oc:differentia`
- uno o piu `oc:resolvesIntent`
- requirement come risorse dedicate
- relazioni `oc:dependsOn`, `oc:extends`, `oc:contradicts`
- stati `oc:requiresState`, `oc:yieldsState`, `oc:handlesFailure`
- `oc:generatedBy`
- eventuale `oc:hasPayload`
- provenance `prov:wasDerivedFrom`

Punto importante:

- le requirement non vengono modellate come blank node, anche se il commento dice cosi
- in realta viene creato un URI deterministico `oc:req_<hash>`

### 4.9 Scrittura modulare su file

Funzione chiave:

- `serialize_skill_to_module(skill, output_path, output_base)`

Comportamento:

- crea un file `skill.ttl` standalone per ogni skill
- importa `ontoclaw-core.ttl` tramite `owl:imports`
- valida il modulo prima di scriverlo

La struttura output voluta e specchiata rispetto a `skills/`:

- `skills/x/y/z/SKILL.md`
- `semantic-skills/x/y/z/skill.ttl`

### 4.10 Ontologia core

Codice coinvolto:

- `compiler/core_ontology.py`

Questo modulo costruisce il TBox dell'ontologia, cioe schema e vocabolario comune.

Classi principali:

- `oc:Skill`
- `oc:ExecutableSkill`
- `oc:DeclarativeSkill`
- `oc:State`
- `oc:Attempt`
- `oc:ExecutionPayload`

Proprieta di stato:

- `oc:requiresState`
- `oc:yieldsState`
- `oc:handlesFailure`
- `oc:hasStatus`

Proprieta di payload:

- `oc:hasPayload`
- `oc:executor`
- `oc:code`
- `oc:timeout`

Proprieta descrittive:

- `oc:generatedBy`
- `oc:contentHash`
- `oc:nature`
- `oc:differentia`
- `oc:resolvesIntent`
- `oc:hasConstraint`
- `oc:hasRequirement`
- `oc:requirementValue`
- `oc:isOptional`

Relazioni tra skill:

- `oc:dependsOn`
- `oc:enables`
- `oc:extends`
- `oc:isExtendedBy`
- `oc:contradicts`

Assiomi OWL interessanti:

- `dependsOn` e `AsymmetricProperty`
- `extends` e `TransitiveProperty`
- `contradicts` e `SymmetricProperty`
- `dependsOn` ha inversa `enables`
- `extends` ha inversa `isExtendedBy`

Stati predefiniti:

- core states: `SystemAuthenticated`, `NetworkAvailable`, `FileExists`, `DirectoryWritable`, `APIKeySet`, `ToolInstalled`, `EnvironmentReady`
- failure states: `PermissionDenied`, `NetworkTimeout`, `FileNotFound`, `InvalidInput`, `OperationFailed`

Nota tecnica importante:

- gli stati predefiniti vengono creati come classi OWL sottoclassi di `oc:State`
- le skill poi puntano a questi URI come oggetti delle proprieta di stato
- il progetto tratta quindi gli stati come entita di schema/concetto piu che come istanze operative

### 4.11 Validazione SHACL

Codice coinvolto:

- `compiler/validator.py`
- `specs/ontoclaw.shacl.ttl`

La validazione e il gate costituzionale del sistema.

Vincoli principali su ogni skill:

- almeno un `oc:resolvesIntent`
- esattamente un `oc:generatedBy`
- `requiresState`, `yieldsState`, `handlesFailure` devono essere IRI e appartenere a `oc:State`

Vincoli sulle skill eseguibili:

- devono avere esattamente un `oc:hasPayload`

Vincoli sulle skill dichiarative:

- non devono avere `oc:hasPayload`

Vincoli sui payload:

- `executor` obbligatorio e in whitelist
- `code` obbligatorio
- `timeout` se presente deve essere intero

Comportamento tecnico utile:

- `validator.py` carica anche l'ontologia core come `ont_graph`
- questo serve per far funzionare bene i controlli `sh:class oc:State`
- senza ontologia core, la validazione degli stati potrebbe dare falsi negativi

### 4.12 Generazione manifest di indice

Codice coinvolto:

- `compiler/storage.py`

Funzione:

- `generate_index_manifest(skill_paths, index_path, output_base)`

Cosa fa:

- crea `index.ttl`
- aggiunge `owl:imports` verso `ontoclaw-core.ttl`
- aggiunge `owl:imports` verso ogni `skill.ttl`

Scopo:

- caricare un solo file di indice e avere accesso all'insieme dei moduli

### 4.13 Pulizia degli orfani

Funzione:

- `clean_orphaned_skills(skills_dir, output_dir, dry_run=False)`

Se in output trova un `skill.ttl` senza la sorgente `SKILL.md` corrispondente:

- lo considera orfano
- lo rimuove

Questo evita che l'ontologia resti sporca dopo cancellazioni di skill dal filesystem.

### 4.14 Query SPARQL

Codice coinvolto:

- `compiler/sparql.py`

Funzione:

- `execute_sparql(ontology_path, query)`

Caratteristiche:

- carica un file Turtle
- blocca query mutative con keyword come `INSERT`, `DELETE`, `DROP`, `CREATE`, `CLEAR`, `LOAD`
- esegue query rdflib
- restituisce righe come lista di dizionari

Output supportato:

- `table`
- `json`
- `turtle` come dump leggibile, non come vero RDF Turtle formale

## 5. CLI: comandi e comportamento

Codice coinvolto:

- `compiler/cli.py`

Il progetto espone uno script console `ontoclaw`.

### `ontoclaw compile`

E il comando principale.

Fa, in ordine:

1. configura logging
2. assicura che esista `ontoclaw-core.ttl`
3. trova le skill da compilare
4. pulisce orfani
5. per ogni skill:
   - genera id e hash
   - tenta skip via hash
   - esegue security check
   - esegue estrazione LLM
6. mostra preview
7. se non e dry-run, serializza i moduli
8. rigenera `index.ttl`

Opzioni importanti:

- `-i/--input`
- `-o/--output`
- `--dry-run`
- `--skip-security`
- `-f/--force`
- `-y/--yes`

### `ontoclaw init-core`

Crea l'ontologia core senza compilare skill.

Serve per inizializzare il TBox.

### `ontoclaw query`

Esegue una query SPARQL contro un file ontologico.

### `ontoclaw list-skills`

Esegue una query predefinita che elenca skill e natura.

### `ontoclaw security-audit`

Rilegge tutte le skill e applica solo la pipeline di sicurezza.

## 6. Configurazione ed environment

Codice coinvolto:

- `compiler/config.py`

Variabili principali:

- `ONTOCLAW_BASE_URI`
- `ONTOCLAW_SKILLS_DIR`
- `ONTOCLAW_OUTPUT_DIR`
- `ANTHROPIC_MODEL`
- `SECURITY_MODEL`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_BASE_URL`

Default importanti:

- base URI: `http://ontoclaw.marea.software/ontology#`
- skills dir: `../../skills/`
- output dir: `../../semantic-skills/`
- modello di estrazione: `claude-opus-4-6`
- modello di sicurezza: `claude-opus-4-6`

Osservazione pratica:

- i path di default sono relativi e pensati per essere usati da dentro la cartella `compiler/`
- quindi l'entrypoint viene eseguito assumendo una certa disposizione del repository

## 7. Dipendenze e ruolo di ciascuna

Da `compiler/pyproject.toml`.

- `click`: CLI
- `pydantic`: validazione strutture dati
- `rdflib`: gestione grafi RDF e query SPARQL
- `anthropic`: accesso API Claude
- `rich`: output terminale
- `owlrl`: inferenza OWL RL
- `pyshacl`: validazione SHACL

Dev dependencies:

- `pytest`
- `pytest-cov`
- `pytest-timeout`
- `ruff`
- `mypy`

## 8. Test suite: cosa copre davvero

La cartella `compiler/tests/` e abbastanza ampia. Copre:

- CLI
- config
- core ontology
- extractor
- eccezioni
- serializzazione
- SPARQL
- storage
- transformer
- validazione
- sicurezza
- integrazione

Ci sono anche test di integrazione che provano la vera estrazione via API Anthropic, ma sono skippati senza `ANTHROPIC_API_KEY`.

In generale la test suite dice che gli autori hanno pensato a:

- correttezza dello schema
- comportamento della CLI
- vincoli SHACL
- tool-use loop
- gestione hash
- reasoning

## 9. Stato reale del progetto: cosa c'e e cosa manca

### Parte veramente implementata

- compilatore Python
- modello dati
- estrazione LLM via Anthropic
- serializzazione RDF/Turtle
- ontologia core
- validazione SHACL
- query SPARQL locali
- test automatici

### Parte solo dichiarata o futura

- server MCP in Rust
- routing runtime basato sugli stati
- integrazione completa MCP con client LLM

Quindi, se vuoi capire il progetto "vero", devi pensare a OntoClaw oggi come:

- un compilatore offline / CLI
- non ancora come piattaforma completa di interrogazione remota via MCP

## 10. Punti forti tecnici

### Separazione chiara dei layer

Il progetto separa bene:

- estrazione
- sicurezza
- modello dati
- serializzazione
- validazione
- query

### Validazione prima della scrittura

Questo e uno dei punti migliori: il sistema non scrive output semanticamente scorretto se SHACL fallisce.

### Hash content-based

Riduce ricompilazioni e costi API.

### Ontologia core esplicita

Non si limita a salvare triple sparse: definisce un TBox consistente e interrogabile.

### Pensiero orientato a modelli piccoli

La filosofia del progetto e coerente: meno contesto testuale, piu retrieval strutturato.

## 11. Limiti, incongruenze e rischi tecnici che ho visto nel codice

Questa e la parte piu utile se vuoi capire il progetto davvero bene.

### 11.1 `compiler/main.py` sembra fragile

Contiene:

- `from cli import cli`

Mentre il package reale usa `compiler.cli`.

Se eseguito in alcuni contesti, questo import puo essere sbagliato o dipendere dal cwd.

### 11.2 Tipi annotati non coerenti in `sparql.py`

`execute_sparql()` annota il return come:

- `list[dict[str, Any]]`

Ma in realta restituisce:

- `rows, vars`

cioe una tupla.

Non rompe l'esecuzione Python, ma la firma e imprecisa.

### 11.3 Commenti non allineati al codice in `serialization.py`

Il commento parla di blank nodes per i requirement, ma vengono creati URI nominati.

Non e grave, ma segnala documentazione interna non perfettamente allineata.

### 11.4 `--skip-security` e ambiguo

Dal nome sembra "salta la sicurezza".

Nel codice significa:

- salta la review LLM
- ma i pattern regex restano bloccanti

La semantica dell'opzione puo confondere.

### 11.5 Gestione stati concettualmente mista

Gli shape SHACL dicono che i riferimenti di stato devono puntare a `oc:State`.
Nel core ontology, pero, gli stati predefiniti sono creati come classi sottoclassi di `oc:State`, non come istanze individuali.

Questo puo comunque funzionare nel modello RDF/OWL adottato, ma concettualmente mescola:

- stati come classi
- stati come nodi runtime referenziati dalle skill

Se il progetto evolvera verso un motore runtime serio, potrebbe servire chiarire meglio se gli stati sono:

- classi
- individui
- o entrambi con un pattern metamodeling esplicito

### 11.6 Alcuni test mostrano tracce di API in evoluzione

Dai test si vedono campi come `constraints` passati al modello, ma non presenti in `ExtractedSkill`.
Questo suggerisce che lo schema ha avuto refactoring e qualche residuo e ancora in giro.

### 11.7 Query sull'indice: dipendenza da import RDF

Il progetto genera `index.ttl` con `owl:imports`, ma `rdflib.Graph.parse()` da solo non "risolve automaticamente tutto" come un reasoner federato completo.

Quindi l'efficacia di query dirette su `index.ttl` dipende dal modo in cui i file importati vengono gestiti nel contesto reale. La narrativa di README e design e piu ambiziosa del comportamento minimo garantito da una semplice parse locale.

### 11.8 Le skill dipendenti sono serializzate come `oc:skill_<dep>`

In `serialize_skill()`, `depends_on`, `extends` e `contradicts` vengono trasformati in URI con pattern `oc:skill_<dep>`.

Ma l'identita vera delle skill e costruita soprattutto dall'hash, non solo dall'id. Quindi questo mapping relazionale va capito bene: se `dep` e un id umano, l'URI risultante potrebbe non coincidere con l'URI hash-based della skill reale.

Questa e la criticita tecnica piu seria che ho notato leggendo il codice:

- skill soggetto: URI basata su hash
- skill nelle relazioni: URI basate su stringa `dep`

Se non esiste una convenzione forte sul contenuto di `depends_on`, si rischiano relazioni che puntano a URI non allineati alle entita serializzate.

## 12. Come leggere mentalmente i moduli

Se vuoi memorizzare il progetto in modo ordinato, pensalo cosi:

- `config.py`: parametri globali e env
- `exceptions.py`: gerarchia errori
- `extractor.py`: id e hash
- `security.py`: filtro difensivo sui contenuti
- `schemas.py`: contratto dati interno
- `transformer.py`: orchestrazione LLM tool-use
- `core_ontology.py`: definizione vocabolario OWL
- `serialization.py`: conversione skill -> triple RDF
- `validator.py`: controllo SHACL
- `storage.py`: path, merge, save, import, cleanup, reasoning
- `sparql.py`: query engine locale
- `cli.py`: facciata operativa

## 13. Come si usa davvero oggi

Uso realistico:

1. prepari directory `skills/.../SKILL.md`
2. installi il package Python
3. esporti `ANTHROPIC_API_KEY`
4. esegui `ontoclaw compile`
5. ottieni:
   - `ontoclaw-core.ttl`
   - moduli `skill.ttl`
   - `index.ttl`
6. interroghi con `ontoclaw query`

Quindi oggi OntoClaw e principalmente:

- un compilatore da markdown a ontologia validata
- con query locali su file

## 14. Sintesi finale

OntoClaw e un progetto concettualmente ambizioso ma con una base concreta gia presente.

La promessa e: trasformare skill testuali di agenti in ontologie formalmente validate.

La parte davvero pronta e:

- CLI Python
- estrazione con Claude
- serializzazione RDF/OWL
- vincoli SHACL
- interrogazione SPARQL

La parte ancora in visione e:

- server MCP Rust
- motore operativo avanzato di routing e reasoning runtime

Se devo definirlo in una frase tecnica precisa:

OntoClaw e un compilatore Python neuro-symbolic che usa Claude per estrarre metadati da skill Markdown, li converte in ontologie OWL 2 validate con SHACL, e li rende interrogabili come knowledge graph RDF.
