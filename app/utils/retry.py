"""重试装饰器模块"""

import functools
from typing import Callable, Type, Tuple

from app.utils.logger import logger


def retry(
    max_retries: int = 3,
    delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    backoff: float = 2.0,
):
    """重试装饰器

    Args:
        max_retries: 最大重试次数，默认 3
        delay: 初始延迟时间（秒），默认 1
        exceptions: 需要重试的异常类型，默认所有 Exception
        backoff: 退避倍数，默认 2（指数退避）

    Example:
        @retry(max_retries=3, delay=1.0)
        def my_function():
            # 可能失败的代码
            pass
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_error = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e

                    if attempt < max_retries - 1:
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} attempts: {e}"
                        )

            raise last_error

        return wrapper

    return decorator