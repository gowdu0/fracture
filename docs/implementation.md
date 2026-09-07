# Implementation gates

1. Establish repository and run `tests/test_semantics.py` against pinned dependencies.
2. Demonstrate approval replay and the separate-node correction.
3. Establish durable effect evidence, response loss, and abrupt worker termination.
4. Expand baseline boundaries into isolated, bounded recovery cases.
5. Complete assertions, replay, pytest helpers, and CLI.
6. Attempt independent integration; document its status separately.
7. Verify clean installation, document actual results, and inspect remote CI.

Three SQLite stores separate application effects, workflow checkpoints, and
controller evidence. Recovery belongs to the scenario. Case validity is separate
from assertion correctness. The implementation is sequential and offline.
