# Behavioral Priors Extraction

This script extracts empirical behavioral priors from GitHub Archive data using the DeployStega feature pipeline. The output is a `behavioral_priors.json` file that will be used for downstream training and evaluation 

## Repository Assumptions
- This script must be run from the root of the DeployStega repository.
- It relies on the existing feature extractors under:
  `features/behavioral/`

## Requirements
- Python 3.9+
- Hugging Face `datasets` library
- Internet access (to stream GitHub Archive data from Hugging Face)

## How to Run

You can run directly on any environment suitable for you.

OR

From the repository root:

```bash
python genbehavioural_json.py


