# urlshortener/tasks.py
from celery import shared_task
from django.core.cache import cache
from urlshortener.models import ShortLink, ClickLog
from django.db import models, transaction
import json
import redis
import os
REDIS_CLICK_KEY = "shortlink_click_count"
redis_url = os.getenv('REDIS_CACHE_URL', 'redis://localhost:6379/0')
redis_client = redis.Redis.from_url(redis_url)

@shared_task(name='urlshortener_count_log_click')
def count_log_click():
    redis_click_key = os.getenv("REDIS_CLICK_KEY", "click_count")

    try:
        click_data = redis_client.hgetall(redis_click_key)
        if not click_data:
            return False

        with transaction.atomic():
            for compressed_url, count in click_data.items():
                original_url = ShortLink.decompress_url(compressed_url.decode())
                if not original_url:
                    continue
                ShortLink.objects.filter(original_url=original_url).update(
                    click_count=models.F('click_count') + int(count)
                )
            redis_client.delete(redis_click_key)
            return True

    except redis.RedisError as e:
        print(f"Redis error: {e}")
        return False
    except Exception as e:
        print(f"Error updating click count: {e}")
        return False



@shared_task(name='urlshortener_log_click')
def log_click(original_url, request_data_json):
    """
    Log a click for a given original URL and update click count in Redis.
    """
    request_data = json.loads(request_data_json)

    # Extract key features
    filtered_data = {
        "ip_address": request_data.get("REMOTE_ADDR"),
        "referrer": request_data.get("HTTP_REFERER"),
        "user_agent": request_data.get("HTTP_USER_AGENT")
    }

    ClickLog.objects.create(
        original_url=original_url,
        ip_address=filtered_data.get("ip_address", ""),
        referrer=filtered_data.get("referrer", ""),
        user_agent=filtered_data.get("user_agent", "")[:255],
        request_data=request_data
    )
    compressed_url = ShortLink.compress_url(original_url)

    try:
        redis_client.hincrby(REDIS_CLICK_KEY, compressed_url, 1)
    except redis.RedisError as e:
        print(f"Redis error: {e}")
        return False

    return True

@shared_task(name='urlshortener_cache_popular_urls')
def cache_popular_urls():
    popular_links = ShortLink.objects.filter(click_count__gte=30).values_list('short_code', 'original_url')
    for short_code, original_url in popular_links:
        cache.set(f'short_link_{short_code}', original_url, timeout=3600*24)

