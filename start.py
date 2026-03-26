import subprocess
import sys
import os
import time
import socket
import logging

# Basic logging for the orchestrator
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("ORCHESTRATOR")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def check_redis():
    """Check if Redis is running on default port 6379."""
    try:
        with socket.create_connection(("localhost", 6379), timeout=1):
            return True
    except:
        return False

def start_redis_docker():
    """Attempt to start Redis via Docker if not running."""
    logger.info("Redis not detected. Attempting to start via Docker...")
    try:
        subprocess.run(["docker", "run", "-d", "--name", "nexus-redis-local", "-p", "6379:6379", "redis:7-alpine"], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        return check_redis()
    except:
        return False

def cleanup_zombies():
    """Kill any orphaned python/celery processes associated with this project."""
    logger.info("Cleaning up existing processes...")
    if os.name == 'nt':
        # On Windows, we use wmic to be selective and terminate processes that are part of the project.
        try:
            # Kill processes that have 'celery' or 'run_backend' in the command line
            # This is safer than killing all python.exe processes.
            subprocess.run(['wmic', 'process', 'where', "commandline like '%celery%' or commandline like '%run_backend%'", 'call', 'terminate'], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2) # Give it a moment to clear Redis connections
        except Exception as e:
            logger.warning(f"Cleanup routine warning: {e}")
    return True

def main():
    print("\n" + "="*50)
    print(" 🛡️  NEXUS - Global News Intelligence Orchestrator")
    print(" " + "="*50 + "\n")

    cleanup_zombies()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "backend")
    frontend_dir = os.path.join(base_dir, "frontend")
    
    python_exe = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    npx_exe = "npx.cmd" if os.name == 'nt' else "npx"

    if not os.path.exists(python_exe):
        python_exe = "python"
        logger.warning("Virtual environment not found, using global python.")

    # Load .env variables
    env = os.environ.copy()
    env_file = os.path.join(backend_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env[k.strip()] = v.strip()

    # 1. Check Dependencies
    if not check_redis():
        if not start_redis_docker():
            logger.error("Redis is required but not running. Please start Redis or Docker Desktop.")
            sys.exit(1)
    logger.info("✅ Redis Connection Verified.")

    # 2. Port Cleanup
    for port in [8000, 5173]:
        if is_port_in_use(port):
            logger.warning(f"Port {port} is already in use. Attempting to proceed anyway...")

    processes = []
    logs = []

    def start_service(name, cmd, cwd, log_file):
        logger.info(f"Starting {name}...")
        f = open(os.path.join(base_dir, log_file), "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, shell=(os.name == 'nt' and not cmd[0].endswith('.exe'))
        )
        processes.append((name, proc, f))
        return proc

    try:
        # Start API
        start_service("Backend API", [python_exe, "run_backend.py"], backend_dir, "api.log")
        
        # Start Worker (-P gevent for Windows stability and high I/O throughput)
        start_service("Celery Worker", [python_exe, "-m", "celery", "-A", "celery_app", "worker", "--loglevel=info", "-P", "gevent", "--concurrency=" + os.getenv("CELERY_WORKER_CONCURRENCY", "16")], backend_dir, "worker.log")
        
        # Start Beat (Scheduler)
        start_service("Celery Beat", [python_exe, "-m", "celery", "-A", "celery_app", "beat", "--loglevel=info"], backend_dir, "beat.log")
        
        # Start Frontend
        start_service("Frontend (Vite)", [npx_exe, "vite", "--port", "5173", "--host"], frontend_dir, "frontend.log")

        print("\n" + "🚀 All services initialized!".center(50))
        print("-" * 50)
        print(f" ➜ Dashboard:  http://localhost:5173")
        print(f" ➜ API Docs:   http://localhost:8000/docs")
        print("-" * 50)
        print(" Logs available in root directory: api.log, worker.log, beat.log, frontend.log")
        print(" Press Ctrl+C to shutdown all services safely.\n")

        while True:
            time.sleep(5)
            for name, proc, _ in processes:
                if proc.poll() is not None:
                    logger.error(f"Critical service '{name}' has stopped (Exit code: {proc.returncode}).")
                    raise KeyboardInterrupt

    except KeyboardInterrupt:
        logger.info("Shutting down services...")
    finally:
        for name, proc, f in processes:
            logger.info(f"Stopping {name}...")
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
            f.close()
        logger.info("Full system shutdown complete.")

if __name__ == "__main__":
    main()
