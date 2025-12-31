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

## Set your token
```bash
export GITHUB_TOKEN=YOUR_TOKEN_HERE
```

---

## Step-by-Step Usage

### 1. Clone the Repository
```bash
git clone https://github.com//DeployStega.git
cd DeployStega
```

### 2. Prepare the Experiment Manifest

Create or edit:
```bash
experiments/experiment_manifest.json
```

Required fields:

- `experiment_id`
- `snapshot` (path to snapshot JSON)
- `participants.sender.id`
- `participants.receiver.id`
- `epoch.origin_time_utc`
- `epoch.duration_seconds`
- `epoch.inspection_window`

#### Sample `experiment_manifest.json`
```json
{
  "experiment_id": "deploystega-test-001",

  "snapshot": "experiments/snapshot.json",

  "participants": {
    "sender": {
      "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "receiver": {
      "id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
  },

  "epoch": {
    "origin_unix": 1735689600,
    "duration_seconds": 180,
    "window_size": 20
  }
}
```

### 3. Bootstrap Participant IDs (Once)

Generate fresh opaque session identifiers:
```bash
python -m scripts.bootstrap_experiment
```

This will populate:

- `participants.sender.id`
- `participants.receiver.id`

### 4. Distribute

- Sender ID → sender
- Receiver ID → receiver

### 5. Build the Repository Snapshot (Once)

Enumerate real, addressable GitHub artifacts and freeze them into a snapshot:
```bash
python -m scripts.build_snapshot
```

This step:

- Uses the GitHub REST API
- Emits only schema-valid, concrete identifiers
- Rejects placeholders (e.g., "unknown")
- Writes the snapshot to the path specified in the manifest

⚠️ **No enumeration or API calls occur after this step.**

### 6. Run the Dead-Drop Resolver (Runtime)

Each participant independently runs:
```bash
python -m scripts.interactive_dead_drop
```

Inside the console:

- Confirm collaborator/write-access requirement
- Select role (sender or receiver)
- Enter your role-specific ID
- Enter an epoch index (integer)

The resolver outputs:

- Artifact class
- Identifier tuple
- Exactly one role-appropriate GitHub URL
- Exactly one action sequence

#### Sender Workflow

1. Run the resolver as sender
2. Open the resolved URL
3. Perform the instructed mutation (edit, create, comment, etc.)
4. Exit — no signaling, acknowledgments, or retries

#### Receiver Workflow

1. Run the resolver as receiver
2. Open the resolved URL
3. Attempt steganographic decoding
4. Apply decode-or-discard:
   - Decode fails → treat artifact as benign
   - Decode succeeds → accept message
5. Optionally inspect previous epochs within the experiment's window

---

## Key Properties

- Deterministic resolution
- No runtime coordination
- No live network queries
- No invalid or placeholder URLs
- Snapshot-valid, schema-conformant identifiers only
- Verifiable rendezvous, not guaranteed delivery

---

## Epoch Model

- Epochs are logical indices, not synchronized events
- Epoch definition is agreed out-of-band
- Receiver may inspect epochs within a bounded window `[T − W, T]`
- Clock drift is tolerated via window size

---

## Research Scope

DeployStega is intended for:

- Detectability analysis
- Behavioral plausibility evaluation
- Controlled covert-routing experiments

It is **not** intended for:

- Production deployment
- Guaranteed message delivery
- Real-time communication

---

## License

Research use only.  
See `LICENSE` for details.
