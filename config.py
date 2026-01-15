# Feature Extraction Configuration

SESSION_TIMEOUT_SECONDS: int = 1800
MIN_EVENTS_PER_USER: int = 5
MIN_TIMING_DELTA_SECONDS: float = 1.0
MAX_TIMING_DELTA_SECONDS: float = 86400.0

# Data Source Configuration

DATA_YEAR: int = 2025
DATA_MONTH: int = 9
DATA_START_DAY: int = 1
DATA_END_DAY: int = 30

# Output Configuration

OUTPUT_JSON_PATH: str = "behavioral_priors.json"
OUTPUT_FIGURES_DIR: str = "figures"
