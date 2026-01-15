from typing import Tuple, List

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent
from config import SESSION_TIMEOUT_SECONDS, MIN_EVENTS_PER_USER


class SessionFeatureExtractor(FeatureExtractor):
    """
    Extracts session length distribution.

    Sessions are split when inter-event gap exceeds SESSION_TIMEOUT_SECONDS.
    """

    @property
    def name(self) -> str:
        return "fsession_length"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[float, ...]:
        all_session_lengths = []

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            if len(trace) < MIN_EVENTS_PER_USER:
                continue

            for session in self._detect_sessions(trace):
                if len(session) < MIN_EVENTS_PER_USER:
                    continue

                duration = session[-1].timestamp - session[0].timestamp
                all_session_lengths.append(duration)

        return tuple(all_session_lengths)

    def _detect_sessions(
        self,
        trace: InteractionTrace
    ) -> List[List[InteractionEvent]]:
        if len(trace) == 0:
            return []

        sessions = []
        current = [trace[0]]

        for i in range(1, len(trace)):
            gap = trace[i].timestamp - trace[i - 1].timestamp
            if gap > SESSION_TIMEOUT_SECONDS:
                sessions.append(current)
                current = [trace[i]]
            else:
                current.append(trace[i])

        sessions.append(current)
        return sessions
