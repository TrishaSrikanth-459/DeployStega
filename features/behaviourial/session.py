"""
Session length feature extractor for behavioral analysis.
"""

from typing import Tuple, List

from features.extractor import FeatureExtractor
from dataset.benign_dataset import BenignDataset
from dataset.neighboring_dataset import NeighboringDataset
from dataset.interaction_trace import InteractionTrace
from dataset.interaction_event import InteractionEvent
from config import SESSION_TIMEOUT_SECONDS, MIN_EVENTS_PER_USER


class SessionFeatureExtractor(FeatureExtractor):
    """
    Extracts session length distribution for behavioral analysis.
    
    Segments user activity into sessions using timeout threshold. Sessions
    are separated when inter-event gap exceeds SESSION_TIMEOUT_SECONDS.
    
    Aggregates session lengths across all users without preserving per-collaborator
    identity. The adversary cannot determine which users are performing stega
    operations, regardless of per-user session count differences.
    """

    @property
    def name(self) -> str:
        return "fsession_length"

    def extract(
        self,
        dataset: BenignDataset | NeighboringDataset
    ) -> Tuple[float, ...]:
        """
        Extract session length distribution from dataset.
        
        Segments traces into sessions using timeout, computes session durations,
        and returns aggregated distribution across all users.
        
        Args:
            dataset: Dataset containing user activity traces
            
        Returns:
            Tuple of session lengths (seconds) aggregated across all users
        """
        all_session_lengths = []

        for user_idx in range(len(dataset)):
            trace = dataset.get_trace(user_idx)

            if len(trace) < MIN_EVENTS_PER_USER:
                continue

            sessions = self._detect_sessions(trace)

            for session_events in sessions:
                if len(session_events) < MIN_EVENTS_PER_USER:
                    continue

                session_length = (
                    session_events[-1].timestamp - session_events[0].timestamp
                )
                all_session_lengths.append(session_length)

        return tuple(all_session_lengths)

    def _detect_sessions(
        self,
        trace: InteractionTrace
    ) -> List[List[InteractionEvent]]:
        """
        Segment trace into sessions using timeout threshold.
        
        New session starts when gap exceeds SESSION_TIMEOUT_SECONDS.
        
        Returns:
            List of sessions (each session is a list of events)
        """
        if len(trace) == 0:
            return []

        sessions = []
        current_session = [trace[0]]

        for i in range(1, len(trace)):
            gap = trace[i].timestamp - trace[i - 1].timestamp

            if gap > SESSION_TIMEOUT_SECONDS:
                sessions.append(current_session)
                current_session = [trace[i]]
            else:
                current_session.append(trace[i])

        sessions.append(current_session)

        return sessions
