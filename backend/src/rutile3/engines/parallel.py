"""Process-local solver state for independent CPU calculations."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import multiprocessing as mp
import os
from threading import Thread
from time import sleep


def worker_count(requested=0):
    available = max(1, (os.cpu_count() or 1) - 1)
    return min(requested or 8, available, 16)


def _watch_parent():
    # JobManager terminates the coordinator on cancel/server shutdown. Spawned
    # workers must exit too, including while a native solver call is in progress.
    parent = mp.parent_process()
    while parent is not None and parent.is_alive():
        sleep(.25)
    os._exit(0)


def _initialize(raw, settings):
    global _db, _components, _phases, _models, _records, _settings
    Thread(target=_watch_parent, daemon=True).start()
    from pycalphad import Model, variables as v
    from pycalphad.codegen.phase_record_factory import PhaseRecordFactory
    from rutile3.engines.tdb import available_phases, parse_tdb, solver_models
    _db = parse_tdb(raw)
    _settings = settings
    _phases, _components = available_phases(_db, settings["components"])
    _models, _ = solver_models(_db, _components, _phases)
    _phases = sorted(_models)
    _records = PhaseRecordFactory(_db, _components, [v.N, v.P, v.T], _models)


def equilibrium_row(task):
    from pycalphad import equilibrium, variables as v
    temperature, xs = task
    try:
        eq = equilibrium(_db, _components, _phases,
                         {v.N: 1, v.P: _settings["pressure"], v.T: float(temperature),
                          v.X(_settings["components"][1]): xs},
                         model=_models, phase_records=_records, calc_opts={"pdens": 1000})
        return eq, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def hull_batch(temperatures):
    from rutile3.engines.boundaries import solve_hull_batch
    return solve_hull_batch(_db, _components, _phases, _settings, temperatures, _models, _records)


@contextmanager
def solver_pool(raw, settings):
    count = settings.get("cpu_workers", 1)
    if count <= 1:
        yield None
        return
    # Spawn avoids inheriting solver/native-library state and works on Windows.
    with ProcessPoolExecutor(max_workers=count, mp_context=mp.get_context("spawn"),
                             initializer=_initialize, initargs=(raw, settings)) as pool:
        yield pool
