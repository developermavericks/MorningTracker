import subprocess
import sys
import os
import time

def main():
    print("\n=======================================")
    print(" NEXUS - Global News Intelligence")
    print(" Starting application...")
    print("=======================================\n")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "backend")
    frontend_dir = os.path.join(base_dir, "frontend")
    
    python_exe = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    npx_exe = "npx.cmd" if os.name == 'nt' else "npx"

    # Make sure python venv exists
    if not os.path.exists(python_exe):
        python_exe = "python" # fallback to global if venv is missing
        print("Warning: Virtual environment python not found, falling back to global python")

    # Load .env
    env_file = os.path.join(backend_dir, ".env")
    env = os.environ.copy()
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    print("\n[0/3] Cleaning up old task queues...")
    try:
        subprocess.run(
            [python_exe, "-m", "celery", "-A", "celery_app", "purge", "-f"],
            cwd=backend_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("      ➜ Queues cleared.")
    except Exception as e:
        print(f"      ➜ Warning: Could not purge queues: {e}")

    print("[1/3] Starting Backend (port 8000)...")
    backend_log = open(os.path.join(backend_dir, "api.log"), "a", encoding="utf-8")
    backend_proc = subprocess.Popen(
        [python_exe, "run_backend.py"],
        cwd=backend_dir,
        env=env,
        stdout=backend_log,
        stderr=subprocess.STDOUT
    )

    print("[2/3] Starting Frontend (port 5173)...")
    frontend_log = open(os.path.join(base_dir, "frontend.log"), "a", encoding="utf-8")
    frontend_proc = subprocess.Popen(
        [npx_exe, "vite", "--port", "5173", "--host"],
        cwd=frontend_dir,
        stdout=frontend_log,
        stderr=subprocess.STDOUT,
        shell=False
    )

    print("[3/3] Starting Celery Worker (gevent)...")
    worker_env = env.copy()
    worker_env["CELERY_WORKER_GEVENT"] = "1"
    worker_log = open(os.path.join(backend_dir, "worker.log"), "a", encoding="utf-8")
    
    worker_proc = subprocess.Popen(
        [python_exe, "-m", "celery", "-A", "celery_app", "worker", "--loglevel=info", "--pool=gevent", "--concurrency=50", "-Q", "orchestrator,scraper_nodes,celery"],
        cwd=backend_dir,
        env=worker_env,
        stdout=worker_log,
        stderr=subprocess.STDOUT
    )

    print("\n" + "="*40)
    print(" NEXUS is now running!")
    print("="*40)
    print(" ➜ API:      http://localhost:8000")
    print(" ➜ Frontend: http://localhost:5173")
    print(" ➜ Logs:     backend/api.log, worker.log")
    print("\n Press Ctrl+C to stop all services.")
    print("="*40 + "\n")

    try:
        while True:
            time.sleep(2)
            if backend_proc.poll() is not None:
                print("\n[!] Backend process exited.")
                break
            if frontend_proc.poll() is not None:
                print("\n[!] Frontend process exited.")
                break
            if worker_proc.poll() is not None:
                print("\n[!] Celery worker process exited.")
                break
    except KeyboardInterrupt:
        print("\n[!] Stopping services...")
    finally:
        def kill_tree(pid):
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except: pass

        for p in [backend_proc, frontend_proc, worker_proc]:
            if p.pid: kill_tree(p.pid)
            
        backend_log.close()
        frontend_log.close()
        worker_log.close()
        print("Goodbye!")

if __name__ == "__main__":
    main()
