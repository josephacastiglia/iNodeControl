"""The stop every farm workflow raises, and the guard for input it sends under its own lease.

InspectionStopped ends a run: nothing more is sent and nothing is replayed. OwnedCaptureRun holds
one phone's input lease for one bounded run and proves, on both sides of every frame, that the
lease, the input generation and the receiver's stream are still the ones it acquired.
"""
import time


class InspectionStopped(Exception):
    pass


class OwnedCaptureRun:
    """In-memory capability. Tokens are never returned as observation evidence."""
    def __init__(self, kernel, run_id, cancelled, monotonic=time.monotonic, *, budget_seconds=90):
        if type(budget_seconds) is not int or not 1 <= budget_seconds <= 120:
            raise ValueError('Owned operation budget must be between 1 and 120 seconds.')
        self.kernel, self.run_id, self.cancelled = kernel, run_id, cancelled
        self.budget_seconds = budget_seconds
        self.monotonic, self.deadline = monotonic, monotonic() + budget_seconds
        self.tokens, self.generation, self.resolved, self.stream = {}, None, None, None

    def check_budget(self):
        if self.cancelled.is_set(): raise InspectionStopped('Inspection cancelled; no action will be replayed.')
        if self.monotonic() >= self.deadline:
            raise InspectionStopped(f'Inspection exceeded its {self.budget_seconds}-second budget.')

    def acquire(self):
        self.check_budget()
        preflight = self.kernel.preflight_phone(self.kernel.phone.board)
        self.resolved = preflight['resolved_id']
        self.stream = self.receiver_context(preflight['receiver'])
        self.tokens = self.kernel.acquire([self.kernel.phone.board], lease_ms=30000)
        state = self.kernel.input_status().get(self.resolved)
        if not self.settled(state): raise InspectionStopped('Acquired input state was not settled.')
        self.generation = state['generation']
        self.check(self.kernel)

    @staticmethod
    def settled(state):
        return (isinstance(state, dict) and type(state.get('generation')) is int and state.get('owned') is True
                and all(state.get(flag) is False for flag in ('active', 'stopped', 'releasing', 'release_failed')))

    @staticmethod
    def receiver_context(receiver):
        return tuple(receiver.get(k) for k in ('deviceid', 'receiver_pid', 'receiver_restarts', 'frame_session'))

    def check(self, kernel):
        self.check_budget()
        if kernel is not self.kernel or not self.tokens: raise InspectionStopped('This capture has no matching owned run.')
        try:
            # Always authenticate the token, not just a status field saying "owned".
            kernel.renew_if_needed(self.tokens, min_remaining_ms=1_000_000)
        except Exception as error:
            raise InspectionStopped('The inspection lease could not be authenticated; input stopped.') from error
        state = kernel.input_status().get(self.resolved)
        if not self.accepts(state): raise InspectionStopped('Inspection ownership changed or input is not settled.')
        receiver = next((r for r in kernel.kernel_status().get('receivers', []) if r.get('deviceid') == self.resolved), {})
        if receiver.get('live') is not True or self.receiver_context(receiver) != self.stream:
            raise InspectionStopped('Receiver or stream changed during inspection.')
        self.check_budget()

    def accepts(self, *states):
        return bool(states) and all(self.settled(s) and s['generation'] == self.generation for s in states)

    def evidence(self):
        return dict(runId=self.run_id, generation=self.generation, authenticatedBeforeAndAfter=True,
                    source='owned_capture_guard', continuousPhoneActivityKnown=False)

    def release(self):
        if self.tokens:
            # Cleanup is deliberately independent of cancellation/deadline checks.
            self.kernel.release(self.tokens)
            self.tokens = {}
