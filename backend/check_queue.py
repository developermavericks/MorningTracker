import redis
import json

try:
    r = redis.from_url('redis://localhost:6379/0')
    q_len = r.llen('celery')
    print(f"Queue 'celery' length: {q_len}")
    
    if q_len > 0:
        tasks = r.lrange('celery', 0, 5)
        for i, task in enumerate(tasks):
            try:
                task_data = json.loads(task)
                headers = task_data.get('headers', {})
                task_name = headers.get('task')
                print(f"  [{i}] Task: {task_name}")
            except:
                print(f"  [{i}] Raw: {task[:100]}...")
except Exception as e:
    print(f"Error connecting to Redis: {e}")
