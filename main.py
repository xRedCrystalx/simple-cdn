"""
Service entry point.

When run directly, this will start the service and serve until it is stopped.
"""

import logging, sys, asyncio, dotenv
sys.dont_write_bytecode = True
dotenv.load_dotenv()

from uvicorn import Server, Config
from fastapi import FastAPI

from utils.models import StatusResponse
from utils.general import ENV

logger = logging.getLogger("cdn.main")


app = FastAPI(
    title=ENV.BRAND_NAME,
    redoc_url=None, docs_url="/api/docs", openapi_url="/api/openapi.json",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1
    },
    responses={
        422: {"model": StatusResponse, "description": "The request did not match the expected shape."},
        500: {"model": StatusResponse, "description": "The request could not be completed."}
    }
)


async def startup() -> Server:
    """Configure and serve web service."""

    from utils import logger as logging_setup, database, errors, paths
    from utils.general import UPLOAD_LOCATION_MAP

    logging_setup.setup()
    logger.info(f"Starting simple-cdn on {ENV.HOST}:{ENV.PORT} (debug={ENV.DEBUG}).")

    await database.db_manager.initialize_pools()

    for path in UPLOAD_LOCATION_MAP.values():
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Upload directory ready: '{path}'.")

    await paths.reload_managed_tree()
    await errors.register_exception_handlers(app)

    from api import admin, files
    app.include_router(admin.router)
    app.include_router(files.router)

    # Order matters here: the index router owns `/{path:path}` and matching is first-win,
    # so every route that should answer for itself has to be registered before it.
    from pages import admin, upload, index, special
    app.include_router(admin.router)
    app.include_router(upload.router)
    app.include_router(special.router)
    app.include_router(index.router)

    logger.info(f"Registered {len(app.routes)} routes, handing over to uvicorn.")

    server = Server(
        Config(app, host=ENV.HOST, port=ENV.PORT,
            log_level="info" if not ENV.DEBUG else "debug",
            server_header=False,
            log_config=None,
            timeout_graceful_shutdown=10,
        )
    )

    await server.serve()


async def shutdown() -> None:
    """Release everything startup acquired."""

    from utils import database
    await database.db_manager.MAIN_POOL.close()

    logger.info("Shutdown complete.")



if __name__ == "__main__":

    with asyncio.Runner() as runner:
        try:
            runner.run(startup())
 
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Interrupted, shutting down.")
 
        except Exception as e:
            logger.critical(f"The service failed: {e}", exc_info=e)
 
        finally:
            try:
                runner.run(shutdown())
 
            except KeyboardInterrupt:
                # A second Ctrl+C during cleanup. Respect it, but say what it cost.
                logger.warning("Shutdown interrupted; some resources were not released cleanly.")
 
