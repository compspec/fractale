import functools
import time


def save_result(func):
    """
    Save the final result, with total elapsed time
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # This is the original function
        start = time.perf_counter()
        context = func(self, *args, **kwargs)
        # Get the result and pass to the callback!
        end = time.perf_counter()
        elapsed_time = end - start
        final_result = context.get("result")
        # Cut out early if missing result (e.g., failure)
        if not self.save_incremental or not final_result:
            return context
        # This can be called more than once if nested
        self.metadata["result"] = {
            "item": final_result,
            "total_seconds": elapsed_time,
            "start_time": start,
            "end_time": end,
            "type": self.result_type,
        }
        return context

    return wrapper


def timed(func):
    """
    Timed decorator that adds timed executions for different functions
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):

        # This is the original function
        start = time.perf_counter()
        result = func(self, *args, **kwargs)
        end = time.perf_counter()
        elapsed_time = end - start
        name = f"{func.__name__}_seconds"
        if name not in self.metadata["times"]:
            self.metadata["times"][name] = []
        self.metadata["times"][name].append(elapsed_time)
        return result

    return wrapper
