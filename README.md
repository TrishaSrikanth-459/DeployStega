DeployStega --- Deterministic Covert Routing over Benign GitHub Activity

======================================================================

DeployStega is a **research framework** for studying the **detectability of covert routing** over **benign-looking GitHub interactions**.

It is **not a messaging system**, **does not guarantee delivery**, and **does not provide acknowledgments or retransmission**. Its purpose is to enable **verifiable rendezvous** under **explicit, auditable assumptions**, suitable for controlled experiments.

DeployStega cleanly separates:

*   **Routing determinism**

*   **Behavioral feasibility constraints**

*   **Benign interaction noise modeling**

into independent, inspectable components.

What DeployStega Is (and Is Not)

--------------------------------

### ✔ What It Is

*   A **deterministic dead-drop resolver**

*   A framework for **detectability and plausibility analysis**

*   Snapshot-based and **identifier-preserving**

*   Explicit about **permissions, timing, and behavioral assumptions**

*   Designed to integrate **empirical benign interaction traces**

### ✘ What It Is Not

*   ❌ A chat system

*   ❌ A reliable transport

*   ❌ A delivery-guaranteeing protocol

*   ❌ A real-time communication system

*   ❌ A production covert channel

Core Concept

------------

At each logical **epoch**, both sender and receiver independently and deterministically resolve:

*   an **artifact class**

*   a **schema-valid identifier**

*   **exactly one concrete GitHub GUI URL**

*   **exactly one role-specific action**

No runtime coordination, signaling, or API access occurs.

If the sender mutates the artifact as instructed, the receiver may later observe it and attempt decoding. Failure to decode is treated as **benign background activity**, not an error.

Prerequisites

-------------

*   Python **3.10+**

*   A GitHub account

*   A GitHub **Personal Access Token**

    *   For private repositories: token must have access

    *   **Sender MUST be a collaborator** with write permissions

### Set your token

bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   export GITHUB_TOKEN=YOUR_TOKEN_HERE   `

Repository Preconditions (Hard Assumptions)

-------------------------------------------

The GitHub repository used in an experiment MUST satisfy:

*   Sender is a collaborator

*   Sender has write permissions

*   Routing artifacts already exist (issues, PRs, commits, etc.)

*   Repository identifiers remain stable for the experiment duration

These are experimental assumptions, not enforced invariants.

If an identifier-changing operation occurs (rename, transfer, history rewrite), the experiment is considered invalidated.

Step-by-Step Usage

------------------

### 1\. Clone the Repository

bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   git clone https://github.com//DeployStega.git  cd DeployStega   `

### 2\. Create the Experiment Manifest

Create or edit:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   experiments/experiment_manifest.json   `

This file defines all fixed experiment parameters.

#### Required Fields

*   experiment\_id

*   snapshot (path to snapshot JSON)

*   participants.sender.id

*   participants.receiver.id

*   epoch.origin\_unix

*   epoch.duration\_seconds

*   epoch.window\_size

#### Example

json

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   {    "experiment_id": "deploystega-test-001",    "snapshot": "experiments/snapshot.json",    "participants": {      "sender": { "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },      "receiver": { "id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }    },    "epoch": {      "origin_unix": 1735689600,      "duration_seconds": 180,      "window_size": 20    }  }   `

### 3\. Bootstrap Participant IDs (Once)

Generate fresh opaque identifiers:

bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   python -m scripts.bootstrap_participants   `

Properties of these IDs:

*   128-bit random hex

*   Non-semantic

*   Not cryptographic keys

*   Used only for deterministic routing synchronization

⚠️ **Do not regenerate IDs mid-experiment** --- doing so breaks sender/receiver alignment.

### 4\. Distribute IDs (Out-of-Band)

*   Sender ID → sender

*   Receiver ID → receiver

No further identity exchange occurs.

### 5\. Build the Repository Snapshot (Once)

Enumerate and freeze real, addressable GitHub artifacts:

bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   python -m scripts.build_snapshot   `

This step:

*   Uses the GitHub REST API

*   Emits only schema-valid identifiers

*   Rejects placeholder values (e.g., "unknown")

*   Enumerates routing artifacts only

*   Writes the snapshot to the path specified in the manifest

⚠️ **After this step, DeployStega performs NO GitHub API calls.**

### 6\. (Optional) Prepare Benign Trace Model Template

Before collecting real benign traces, generate a template:

bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`python -m scripts.generate_benign_trace_template \    --owner  \    --repo`

This produces:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   experiments/benign_trace_model.json   `

The template can later be populated with empirical probabilities derived from real benign browsing traces.

### 7\. Run the Interactive Dead-Drop Resolver

Each participant runs independently:

bash

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   python -m scripts.interactive_dead_drop   `

The console will:

*   Warn about collaborator/write-access requirements

*   Load experiment context and snapshot

*   Ask for role (sender or receiver)

*   Verify your role-specific ID

*   Resolve the current logical epoch

Runtime Behavior

----------------

### Sender Workflow

1\.  Resolve the current epoch

2\.  Open the resolved GitHub URL

3\.  Perform exactly the instructed mutation

4\.  Exit

**No retries. No acknowledgments. No confirmation of reception.**

### Receiver Workflow

1\.  Resolve the current epoch

2\.  Optionally inspect epochs in \[T - W, T\]

3\.  Open resolved URLs

4\.  Attempt steganographic decoding

5\.  Apply decode-or-discard semantics:

    *   Decode fails → treat artifact as benign

    *   Decode succeeds → accept message

Epoch Model

-----------

*   Epochs are logical indices, not synchronized events

*   Epoch origin (T₀) is fixed out-of-band

*   Sender resolves exactly one epoch

*   Receiver may inspect a bounded window \[T - W, T\]

*   Clock drift is tolerated via window size

Feasibility Region

------------------

Routing is constrained by a FeasibilityRegion abstraction that:

*   Encodes which (epoch, artifact\_class, role, URL) tuples are allowed

*   Is deterministic and side-effect free

*   Is populated from benign interaction traces

*   Applies equally to routing and benign interactions

A permissive AllowAllFeasibility exists for inspection and debugging only.

Key Properties

--------------

*   Deterministic resolution

*   No runtime coordination

*   Snapshot-bound identifiers

*   Identifier-preserving actions only

*   Explicit behavioral assumptions

*   Best-effort covert routing

Research Scope

--------------

DeployStega is intended for:

*   Detectability analysis

*   Behavioral plausibility studies

*   Controlled covert-routing experiments

*   Empirical comparison against benign traces

It is **not** intended for:

*   Production deployment

*   Reliable communication

*   Interactive messaging

*   Real-time signaling

License and Ethics

------------------

DeployStega is a research-only framework.

Users are responsible for ensuring that all experiments:

*   comply with GitHub's Terms of Service,

*   respect ethical research guidelines, and

*   are conducted on repositories they are authorized to use.
## License

Research use only.  
See `LICENSE` for details.
