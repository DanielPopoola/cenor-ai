from observation.service import ObservationService


async def run_observation_task(
    session_id: str, observation_service: ObservationService
):
    await observation_service.run_observation(session_id)
