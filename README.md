# DeployStega – Deterministic Dead-Drop Resolver

DeployStega is a **research framework** for evaluating the detectability of covert routing over benign GitHub activity.  
It is **not a messaging system** and **does not guarantee delivery**.  
It provides *verifiable rendezvous* under strict, explicit assumptions.

---

## Prerequisites

- Python **3.10+**
- A GitHub account
- A GitHub **personal access token**
  - For **private repositories**, the token must have access
  - The **sender must be a collaborator** with write permissions

---

## Set Your Token
```bash
export GITHUB_TOKEN=YOUR_TOKEN_HERE
```
## Step-by-Step Usage
### 1. Clone the Repository
```bash
git clone https://github.com/TrishaSrikanth-459/DeployStega.git
cd DeployStega
```
### 2. Create and Activate a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```
### 3. Build the Experiment Snapshot (Required, Once)
Install python's requests package in your virtual environment:
```bash
pip install requests
```

All experiment initialization is performed by:
```bash
python3 -m scripts.build_snapshot
```
This step fully initializes the experiment and must be completed before any sender or receiver runtime execution.


During this step, the user is prompted to provide:

- GitHub repository owner
- GitHub repository name
- Epoch origin UNIX time
- Epoch end UNIX time

### 4. Timing Constraints (Enforced)
- epoch.origin_unix must be at least 5 minutes after snapshot build time
- epoch.end_unix must be at least 5 minutes after epoch.origin_unix

Invalid inputs will abort snapshot creation.

#### What build_snapshot.py does:
This single step:
- Generates a unique experiment ID
- Generates opaque sender and receiver IDs
- Enumerates all real, addressable GitHub artifacts
- Freezes them into a routing-only snapshot
- Writes both:
  - experiments/snapshot.json
  - experiments/experiment_manifest.json

Example Output
```text
Experiment ID : deploystega-1768098266
Snapshot      : experiments/snapshot.json
Manifest      : experiments/experiment_manifest.json
```
Participant IDs (share privately):
```text
Sender ID   : <opaque 128-bit hex>
Receiver ID : <opaque 128-bit hex>
Do not modify the snapshot or manifest after this step.
All runtime scripts operate in read-only mode.
```
### 5. Distribute Participant IDs (Out-of-Band)
- Sender ID → sender
- Receiver ID → receiver

These identifiers:
- Are not cryptographic keys
- Are used only as deterministic PRNG inputs
- Must remain fixed for the experiment

### 6. Run the Dead-Drop Resolver (Runtime)
Each participant independently runs:
```bash
python3 -m scripts.interactive_dead_drop
```
## Console Flow:
- Automatic wait until epoch origin (with countdown warning)
- Select role (sender or receiver)
- Enter role-specific ID
- Resolver executes automatically per epoch

The resolver outputs:
- Artifact class
- Identifier tuple
- Exactly one role-appropriate GitHub URL
- Exactly one action sequence

## Sender Workflow
1. Wait for epoch start
2. Open the resolved URL
3. Perform the instructed mutation (edit, comment, etc.)
4. Do not signal or retry

## Receiver Workflow
1. Wait for epoch start
2. Open the resolved URL
3. Attempt steganographic decoding
4. Apply decode-or-discard:
  - Decode fails → treat artifact as benign
  - Decode succeeds → accept message
5. Inspect prior epochs within the inspection window if needed

## Epoch Model
- Epochs are logical indices, not events
- Epoch counting is fixed relative to epoch.origin_unix
- Running scripts does not reset epoch state
- Resolver outputs are valid only within:
```text
[epoch.origin_unix, epoch.end_unix)
- A safety countdown is displayed prior to epoch start
- Execution terminates automatically at epoch end
```
## Key Properties
- Deterministic resolution
- No runtime coordination
- No live network queries
- No invalid or placeholder URLs
- Snapshot-valid identifiers only
- Verifiable rendezvous, not guaranteed delivery

## Research Scope
DeployStega is intended for:
- Detectability analysis
- Behavioral plausibility evaluation
- Controlled covert-routing experiments
It is not intended for:
- Production deployment
- Guaranteed message delivery
- Real-time communication
- Endpoint security evaluation

## License
Research use only.
See LICENSE for details.
