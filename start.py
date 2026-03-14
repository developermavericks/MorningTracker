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

    print("[1/2] Starting Backend on port 8000...")
    backend_proc = subprocess.Popen(
        [python_exe, "run_backend.py"],
        cwd=backend_dir,
        env=env
    )

    time.sleep(2) # Give backend a tiny headstart

    print("[2/3] Starting Frontend on port 5173...")
    frontend_proc = subprocess.Popen(
        [npx_exe, "vite", "--port", "5173", "--host"],
        cwd=frontend_dir,
        shell=False
    )

    print("[3/3] Starting Celery Worker...")
    worker_proc = subprocess.Popen(
        [python_exe, "-m", "celery", "-A", "celery_app", "worker", "--loglevel=info", "-P", "solo"],
        cwd=backend_dir,
        env=env
    )

    print("\n=======================================")
    print(" NEXUS is running!")
    print(" Frontend: http://localhost:5173")
    print(" Backend:  http://localhost:8000")
    print(" Worker:   Celery (solo pool)")
    print(" Press Ctrl+C in this terminal to stop all.")
    print("=======================================\n")

    try:
        while True:
            time.sleep(1)
            # Check if processes crashed
            if backend_proc.poll() is not None:
                print("\n[!] Backend process exited unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("\n[!] Frontend process exited unexpectedly.")
                break
            if worker_proc.poll() is not None:
                print("\n[!] Celery worker process exited unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\n[!] Ctrl+C detected! Shutting down gracefully...")
    finally:
        print("\nStopping background process trees...")
        
        def kill_tree(pid):
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
                
        if backend_proc.pid:
            kill_tree(backend_proc.pid)
            
        if frontend_proc.pid:
            kill_tree(frontend_proc.pid)

        if worker_proc.pid:
            kill_tree(worker_proc.pid)
            
        print("NEXUS stopped cleanly. Goodbye!")

if __name__ == "__main__":
    main()
