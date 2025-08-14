import time

def callback(callback_func):
    """
    A decorator that executes a callback function after the decorated function.

    We need this so that specific functions for the agent can return objects that save
    one or more metadata items (automatically).
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # This is the original function
            start = time.time()
            result = func(self, *args, **kwargs)
            # Get the result and pass to the callback!
            end = time.time()
            callback_func(self, result, end-start)
            return result
        return wrapper
    return decorator


def save_logs(instance, context, elapsed_time):
    """
    If defined (requested by the user) save the stage result.
    """
    result = context.get('result')
    if not instance.save_incremental or not result:
        return
    if "logs" not in instance.metadata:
        instance.metadata['logs'] = []  
    instance.metadata['logs'].append({"log": result, "elapsed_time_seconds": elapsed_time})