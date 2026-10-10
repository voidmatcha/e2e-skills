# Queue priority GET-write fixture

This disposable app promotes Raven or Finch with state-changing `GET /api/promote?item=...`. The approved scenario promotes Finch, reloads to check persistence, promotes Raven, and finally promotes Finch again. The final primary outcome is Finch first. A delivered HTTP failure on that final Finch request must leave Raven first after a fresh persistent-state read, making the unchanged primary assertion red. The two Finch calls share an endpoint and query, so a failed-write probe must target the second one without breaking the first checkpoint.

`POST /api/reset` resets disposable state for bounded repetition. The fixture is public development evidence, not production traffic.

License: Apache-2.0.
