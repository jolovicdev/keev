import asyncio
import time
import statistics
import aiohttp
import multiprocessing
import random
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any

# 3rd-party imports
# Make sure you have installed them via pip:
# pip install uvicorn fastapi flask pydantic keev

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field
from keev import Application, Router, JSONResponse, RequestContext
from keev import HTTPException as KeevHTTPException
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.CRITICAL)
for name in ["uvicorn", "uvicorn.error", "keev", "fastapi", "asyncio"]:
    logging.getLogger(name).setLevel(logging.CRITICAL)

# ------------------------------------------------------------------
# 1. CONFIGURATION
# ------------------------------------------------------------------

@dataclass
class BenchmarkConfig:
    run_duration: int = 15              # Duration (in seconds) for each concurrency level test
    concurrency_levels: List[int] = field(default_factory=lambda: [10, 50])
    warmup_requests: int = 5
    keev_port: int = 9001
    fastapi_port: int = 9002
    flask_port: int = 9003

# ------------------------------------------------------------------
# 2. MODELS & PAYLOAD GENERATION
# ------------------------------------------------------------------

class TestItem(BaseModel):
    """
    Pydantic model for testing POST requests.
    """
    id: int = Field(default_factory=lambda: int(time.time() * 1000) % 10000)
    name: str
    price: float
    quantity: int = Field(default=1, ge=0)
    in_stock: bool = True
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

def generate_test_item() -> dict:
    """Generate a random item payload."""
    return {
        "name": f"Item_{random.randint(100, 999)}",
        "price": round(random.uniform(1, 1000), 2),
        "quantity": random.randint(1, 10),
        "in_stock": random.choice([True, False]),
        "tags": [f"tag_{i}" for i in range(random.randint(1, 3))],
        "metadata": {f"key_{i}": f"value_{i}" for i in range(random.randint(1, 3))}
    }

# ------------------------------------------------------------------
# 3. FRAMEWORK SERVERS
# ------------------------------------------------------------------

# ---------------------- Keev ---------------------- #
keev_app = Application(debug=False)
keev_router = Router()

@keev_router.get("/benchmark")
async def keev_get(ctx: RequestContext):
    return JSONResponse({"framework": "Keev", "timestamp": time.time()})

@keev_router.post("/benchmark")
async def keev_post(ctx: RequestContext, item: TestItem):
    return JSONResponse(item.model_dump())

keev_app.router = keev_router


# --------------------- FastAPI -------------------- #
fastapi_app = FastAPI(debug=False)

@fastapi_app.get("/benchmark")
async def fastapi_get():
    return {"framework": "FastAPI", "timestamp": time.time()}

@fastapi_app.post("/benchmark")
async def fastapi_post(item: TestItem):
    return item


# ---------------------- Flask ---------------------- #
flask_app = Flask(__name__)

@flask_app.route("/benchmark", methods=["GET"])
def flask_get():
    return jsonify({"framework": "Flask", "timestamp": time.time()})

@flask_app.route("/benchmark", methods=["POST"])
def flask_post():
    data = request.json
    return jsonify(data)

# ------------------------------------------------------------------
# 4. SERVER WRAPPERS (Process-based)
# ------------------------------------------------------------------

class ServerProcess:
    """
    Manages a server in a separate process for each framework,
    so that they can run concurrently and be benchmarked.
    """
    def __init__(self, name: str, app, port: int, use_uvicorn: bool = True):
        self.name = name
        self.app = app
        self.port = port
        self.process = None
        self.use_uvicorn = use_uvicorn

    def start(self):
        # For Keev and FastAPI, we can just run uvicorn. 
        # For Flask, we can do app.run(...) or also uvicorn if you wrap it with a WSGI->ASGI translator.
        if self.name == "Flask":
            # We'll just do the standard Flask run here (WSGI)
            # NOTE: If you prefer, you could do gunicorn or waitress here for concurrency.
            self.process = multiprocessing.Process(
                target=self.app.run,
                kwargs={
                    "host": "127.0.0.1",
                    "port": self.port,
                    "debug": False,
                }
            )
        else:
            # For Keev and FastAPI
            self.process = multiprocessing.Process(
                target=uvicorn.run,
                args=(self.app,),
                kwargs={
                    "host": "127.0.0.1",
                    "port": self.port,
                    "log_level": "critical",
                    "workers": 1,
                }
            )
        self.process.start()
        time.sleep(1)  # give server time to start

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.join()

# ------------------------------------------------------------------
# 5. BENCHMARK RUNNER & METRICS
# ------------------------------------------------------------------

@dataclass
class BenchmarkMetrics:
    times: List[float] = field(default_factory=list)
    errors: int = 0
    status_codes: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def success_rate(self) -> float:
        total = len(self.times) + self.errors
        return (len(self.times) / total) * 100 if total else 0.0

    @property
    def avg_time(self) -> float:
        return statistics.mean(self.times) * 1000 if self.times else 0.0  # ms

    @property
    def median_time(self) -> float:
        return statistics.median(self.times) * 1000 if self.times else 0.0

    @property
    def min_time(self) -> float:
        return min(self.times) * 1000 if self.times else 0.0

    @property
    def max_time(self) -> float:
        return max(self.times) * 1000 if self.times else 0.0

    @property
    def rps(self) -> float:
        total_time = self.end_time - self.start_time
        return len(self.times) / total_time if total_time > 0 else 0.0

    @property
    def std_dev(self) -> float:
        return statistics.stdev(self.times) * 1000 if len(self.times) > 1 else 0.0

def format_metrics(metrics: BenchmarkMetrics) -> Dict[str, Any]:
    return {
        "requests": len(metrics.times),
        "errors": metrics.errors,
        "avg_ms": round(metrics.avg_time, 2),
        "median_ms": round(metrics.median_time, 2),
        "min_ms": round(metrics.min_time, 2),
        "max_ms": round(metrics.max_time, 2),
        "std_dev_ms": round(metrics.std_dev, 2),
        "rps": round(metrics.rps, 2),
        "success_rate_%": round(metrics.success_rate, 2),
        "status_codes": dict(metrics.status_codes)
    }

class BenchmarkRunner:
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        # We'll test two scenarios: GET and POST with random item
        self.scenarios = [
            {"name": "GET /benchmark", "method": "GET", "path": "/benchmark", "data": None},
            {"name": "POST /benchmark", "method": "POST", "path": "/benchmark", "data": generate_test_item()}
        ]

    async def run_for_framework(self, name: str, port: int) -> Dict[str, Dict]:
        """
        Runs the benchmark for all concurrency levels in config and returns a summary of results.
        """
        base_url = f"http://127.0.0.1:{port}"
        results = {}

        # Single HTTP session can be used for concurrency
        connector = aiohttp.TCPConnector(limit=1000)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Warmup
            await self._warmup(session, base_url)

            # For each concurrency level
            for c_level in self.config.concurrency_levels:
                scenario_results = {}
                for scenario in self.scenarios:
                    scenario_key = f"{scenario['name']} | concurrency={c_level}"
                    metrics = await self._run_scenario(
                        session, 
                        base_url, 
                        scenario, 
                        concurrency=c_level, 
                        duration=self.config.run_duration
                    )
                    scenario_results[scenario_key] = format_metrics(metrics)
                results[f"Concurrency_{c_level}"] = scenario_results
        return results

    async def _warmup(self, session: aiohttp.ClientSession, base_url: str):
        """Send a few warmup requests before the real test."""
        tasks = []
        for _ in range(self.config.warmup_requests):
            tasks.append(session.get(f"{base_url}/benchmark"))
            tasks.append(session.post(f"{base_url}/benchmark", json=generate_test_item()))
        # We don't care about the results, just discard
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_scenario(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        scenario: Dict[str, Any],
        concurrency: int,
        duration: int
    ) -> BenchmarkMetrics:
        metrics = BenchmarkMetrics()
        metrics.start_time = time.time()
        url = f"{base_url}{scenario['path']}"

        async def worker():
            while (time.time() - metrics.start_time) < duration:
                await self._make_request(session, url, scenario, metrics)

        # Spawn concurrency tasks
        tasks = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*tasks, return_exceptions=True)
        metrics.end_time = time.time()
        return metrics

    async def _make_request(self, session: aiohttp.ClientSession, url: str, scenario: Dict[str, Any], metrics: BenchmarkMetrics):
        start = time.perf_counter()
        try:
            async with session.request(
                method=scenario["method"],
                url=url,
                json=scenario["data"],
                headers={"Content-Type": "application/json"}
            ) as response:
                # Attempt to read the response (to ensure framework has to process it)
                await response.text()
                duration = time.perf_counter() - start
                metrics.times.append(duration)
                metrics.status_codes[response.status] += 1
        except Exception:
            metrics.errors += 1

# ------------------------------------------------------------------
# 6. MAIN LOGIC
# ------------------------------------------------------------------

def save_results_to_file(all_results: Dict[str, Any]):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"benchmark_results_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {filename}\n")

async def main():
    config = BenchmarkConfig()

    # Create server processes
    keev_server = ServerProcess("Keev", keev_app, port=config.keev_port)
    fastapi_server = ServerProcess("FastAPI", fastapi_app, port=config.fastapi_port)
    flask_server = ServerProcess("Flask", flask_app, port=config.flask_port, use_uvicorn=False)

    servers = [keev_server, fastapi_server, flask_server]

    # Start servers
    for srv in servers:
        srv.start()

    runner = BenchmarkRunner(config)
    all_results = {}

    # Run benchmark for each
    try:
        # Keev
        all_results["Keev"] = await runner.run_for_framework("Keev", config.keev_port)

        # FastAPI
        all_results["FastAPI"] = await runner.run_for_framework("FastAPI", config.fastapi_port)

        # Flask
        all_results["Flask"] = await runner.run_for_framework("Flask", config.flask_port)

    finally:
        # Stop the servers
        for srv in servers:
            srv.stop()

    # Print summary and save
    for framework, results_by_concurrency in all_results.items():
        print(f"\n=== {framework} ===")
        for concurrency_level, scenario_res in results_by_concurrency.items():
            print(f"\n  {concurrency_level}:")
            for scenario_key, metrics_dict in scenario_res.items():
                print(f"    {scenario_key}: {metrics_dict}")

    save_results_to_file(all_results)

if __name__ == "__main__":
    asyncio.run(main())
