import asyncio
import logging
import signal

from agent0 import __version__
from agent0.api import create_app
from agent0.config import load_config
from agent0.daemon import Daemon
from agent0.logbuffer import LogBuffer

__all__ = ['main']

log = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:

    '''
    Compute logging configuration.

    Args:
        level (str): Logging level name

    Returns:
        None
    '''

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


async def _run() -> None:

    '''
    Compute main async entry point: startup, server, poll loop, shutdown.

    Returns:
        None
    '''

    config = load_config()
    _setup_logging(config.log_level)

    log_buffer = LogBuffer()
    logging.getLogger().addHandler(log_buffer)

    log.info('Agent0 v%s starting', __version__)
    log.info('Config: %s', config.log_redacted())

    daemon = Daemon(config)

    await daemon.start()

    app = create_app(daemon, config, log_buffer)

    import uvicorn
    server_config = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=config.port,
        log_level=config.log_level.lower(),
    )
    server = uvicorn.Server(server_config)
    server.install_signal_handlers = False

    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        log.info('Signal received, initiating shutdown')
        shutdown_event.set()
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    async def _serve() -> None:
        await server.serve()

    async def _poll() -> None:
        poll_task = asyncio.create_task(daemon.poll_loop())
        await shutdown_event.wait()
        await daemon.shutdown()
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

    await asyncio.gather(_serve(), _poll())


def main() -> None:

    '''
    Compute Agent0 startup sequence.

    Returns:
        None
    '''

    asyncio.run(_run())
