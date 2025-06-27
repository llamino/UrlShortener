# urlshortener/models.py

import uuid
from urllib.parse import urlparse, urlunparse
import json
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
import hmac
import hashlib
from django.conf import settings
import base64
from urllib.parse import unquote
import zlib
from django.core.cache import cache

class Campaign(models.Model):
    """
    Represents a marketing campaign. Each campaign can have multiple short links.
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=100, unique=True)
    advertiser = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    extra = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.name

class Blogger(models.Model):
    """
    Represents a blogger who can be associated with short links.
    """
    user_name = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    instagram_id = models.CharField(max_length=100, unique=True)
    extra = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.user_name


class ShortLink(models.Model):
    """
    Represents a shortened URL and its metadata.
    Each short link is associated with a campaign and optionally a blogger.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('blocked', 'Blocked'),
        ('inactive', 'Inactive'),
    ]
    blogger = models.ForeignKey(Blogger, on_delete=models.SET_NULL, null=True, blank=True, related_name='short_links')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    original_url = models.TextField()
    short_code = models.TextField(null=True, blank=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL,null=True, related_name="short_links")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="short_links")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    click_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    extra = models.JSONField(null=True, blank=True)

    ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


    @staticmethod
    def is_valid_url(url: str) -> bool:
        """
        Validates a URL using Django's URLValidator.
        Returns True if valid, False otherwise.
        """
        if not url:
            return False
        validator = URLValidator()
        try:
            decoded_url = unquote(url)  # Decode percent-encoded URL
            validator(decoded_url)
            return True
        except ValidationError:
            return False


    @staticmethod
    def convert_request_data_to_json(request):
        """
        Extracts all available data from request and returns a JSON-serializable dictionary.
        """
        request_data = {
            key: value for key, value in request.META.items() if isinstance(value, (str, int, float, list, dict))
        }
        request_data["method"] = request.method
        request_data["path"] = request.path
        request_data["query_params"] = request.GET.dict()
        request_data["post_data"] = request.POST.dict()
        return json.dumps(request_data)

    @staticmethod
    def compress_url(url):
        """
        Compresses a URL for shorter storage and easier caching.
        """
        compressed = zlib.compress(url.encode())
        return base64.urlsafe_b64encode(compressed).decode()


    @staticmethod
    def decompress_url(compressed_url):
        """
        Decompresses a previously compressed URL.
        """
        compressed = base64.urlsafe_b64decode(compressed_url.encode())
        return zlib.decompress(compressed).decode()

    @staticmethod
    def generate_short_code(original_url: str) -> str:
        """
        Generates a short code for a given original URL using HMAC and base64 encoding.
        """
        encoded_url = base64.urlsafe_b64encode(original_url.encode()).decode().rstrip('=')
        signature = hmac.new(settings.SECRET_KEY.encode(), msg=encoded_url.encode(),digestmod=hashlib.sha256).hexdigest()[:4]
        return f"{encoded_url}{signature}"


    @staticmethod
    def decode_short_code(short_code: str) -> str:
        """
        Decodes a short code back to the original URL, verifying its signature.
        Raises ValueError if invalid.
        """
        if len(short_code) <= 4:
            raise ValueError("Short code is invalid")

        encoded_url = short_code[:-4]
        signature = short_code[-4:]
        expected_signature = hmac.new(settings.SECRET_KEY.encode(), msg=encoded_url.encode(), digestmod=hashlib.sha256).hexdigest()[:4]

        if signature != expected_signature:
            raise ValueError("Signature of short code is invalid")

        try:
            padding_needed = 4 - (len(encoded_url) % 4)
            encoded_url += "=" * padding_needed
            original_url = base64.urlsafe_b64decode(encoded_url).decode()
            return original_url
        except Exception:
            raise ValueError("Failed to decode the short code")

    @staticmethod
    def canonicalize_url(url: str) -> str:
        """
        Removes query parameters and fragments from a URL to get its canonical form.
        """
        parsed = urlparse(url)
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean)

    def __str__(self):
        return f"{self.short_code} - {self.campaign.name} - {self.original_url}"

    def save(self, *args, **kwargs):
        """
        Saves the ShortLink instance, generating a short code if not present.
        """
        if not self.short_code:
            self.short_code = self.generate_short_code(self.original_url)
        super().save(*args, **kwargs)




class ClickLog(models.Model):
    """
    Stores click logs for each short link, including IP, referrer, and user agent.
    """
    original_url = models.TextField() # This field relates to original_url in ShortLink table.
    ip_address = models.CharField(max_length=100, null=True, blank=True)
    referrer = models.CharField(max_length=100, null=True, blank=True, default=None)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    request_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    extra = models.JSONField(null=True, blank=True)
    def __str__(self):
        return f"Click on {self.original_url} at {self.created_at}"

class BlockedIp(models.Model):
    """
    Stores blocked IP addresses and their restrictions for accessing short links.
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    ip_address = models.CharField(max_length=32, db_index=True, unique=True)
    is_blocked_for_all_url = models.BooleanField(default=False)
    is_unblocked_for_every_url = models.BooleanField(default=True)
    blocked_links = models.JSONField(blank=True, default=list)  # Stores list of blocked original_urls
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Blocked IP: {self.ip_address}"

    @staticmethod
    def is_blocked_ip(ip, original_url):
        """
        Checks if an IP is blocked for all URLs or a specific original URL, using cache for performance.
        Returns True if blocked, False otherwise.
        """
        cache_key_all = f'blocked_ip_all_{ip}'
        if cache.get(cache_key_all):
            return True

        cache_key_link = f'blocked_ip_link_{ip}_{original_url}'
        if cache.get(cache_key_link):
            return True

        blocked_ip = BlockedIp.objects.filter(ip_address=ip, is_active=True).exists()
        if not blocked_ip:
            return False

        if blocked_ip["is_blocked_for_all_url"]:
            cache.set(cache_key_all, True, timeout=900)  # 15 minute
            return True

        if original_url in blocked_ip["blocked_links"]:
            cache.set(cache_key_link, True, timeout=900)  # 15 minute
            return True

        return False

