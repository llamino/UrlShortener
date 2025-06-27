# urlshortener/views.py
from django.shortcuts import redirect, get_object_or_404
from django.core.cache import cache
import redis
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from urlshortener.models import ShortLink, Campaign, ClickLog, BlockedIp
from urlshortener.tasks import log_click
from rest_framework.throttling import SimpleRateThrottle
from django.conf import settings
import os
import json


class CustomRedirectThrottle(SimpleRateThrottle):
    """
    Custom rate throttle for redirect requests.
    Limits the number of redirects per IP to prevent abuse.
    """
    scope = 'custom_redirect'
    rate = '10/minute'  # Limit to 10 requests per minute

    def get_cache_key(self, request, view):
        """
        Returns a unique cache key for the request based on the client IP.
        """
        return self.get_ident(request)


class AddLinkApi(APIView):
    """
    API endpoint to add links from a JSON file to the database.
    Reads links from json/links.json and creates ShortLink objects for valid URLs.
    """
    def get(self, request):
        """
        Reads links from a JSON file and adds them to the database under the 'Digikala' campaign.
        """
        file_path = os.path.join('json', 'links.json')
        print(file_path)
        with open(file_path, 'r', encoding='utf-8') as file:
            links = json.load(file)['links']

        campaign, created = Campaign.objects.get_or_create(name="Digikala")

        for link in links:
            if ShortLink.is_valid_url(link):
                short_link, created = ShortLink.objects.get_or_create(original_url=link, campaign=campaign)
                if created:
                    print(f"Created ShortLink for {link}")
                else:
                    print(f"ShortLink for {link} already exists")
            else:
                print(f"Invalid URL: {link}")


class RedirectView(APIView):
    """
    API endpoint to redirect a short code to its original URL.
    Uses cache and checks for blocked IPs before redirecting.
    """
    throttle_classes = [CustomRedirectThrottle]

    def get(self, request, short_code):
        """
        Redirects to the original URL for the given short code.
        Caches the result and logs the click asynchronously.
        """
        # Check if the URL is cached
        ip = request.META.get('REMOTE_ADDR')
        cached_url = cache.get(f'short_link_{short_code}')
        request_data_json = ShortLink.convert_request_data_to_json(request)

        if cached_url:
            if BlockedIp.is_blocked_ip(ip, cached_url):
                return Response({"status": "blocked"}, status=403)
            log_click.delay(cached_url, request_data_json)
            return redirect(cached_url, permanent=True)

        try:
            original_url = ShortLink.decode_short_code(short_code)
            if BlockedIp.is_blocked_ip(ip, original_url):
                return Response({"status": "blocked"}, status=403)
            cache.set(f'short_link_{short_code}', original_url, timeout=1200)  # Cache for 20 min
            log_click.delay(original_url, request_data_json)
            return redirect(original_url, permanent=True)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ShortenURLAPI(APIView):
    """
    API endpoint to shorten a given URL for a specific campaign.
    Returns a short code for the original URL.
    """
    # permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Shortens a URL and associates it with a campaign.
        Returns the short code or an error message.
        """
        original_url = request.data.get('url')
        campaign_id = request.data.get('campaign_id')
        is_valid_url = ShortLink.is_valid_url(original_url)
        if not original_url:
            return Response({"error": "URL is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not is_valid_url:
            return Response({'is_valid_url': False}, status=status.HTTP_400_BAD_REQUEST)
        if not campaign_id:
            return Response({"error": "Campaign ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Canonicalize the URL
        canonical_url = ShortLink.canonicalize_url(original_url)

        # Get the campaign object
        campaign = Campaign.objects.filter(id=campaign_id).first()
        if not campaign:
            return Response({"error": "Invalid campaign ID"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the URL already exists
        existing_link = ShortLink.objects.filter(original_url=canonical_url, campaign=campaign).first()
        if existing_link:
            return Response({"short_url": f"{settings.DOMAINS['local']}/{existing_link.short_code}"},
                            status=status.HTTP_200_OK)

        # Create a new short link
        short_link = ShortLink.objects.create(
            original_url=canonical_url,
            campaign=campaign,
            # created_by=request.user
        )
        # Generate the short code
        generated_code = ShortLink.generate_short_code(original_url)
        while ShortLink.objects.filter(short_code=generated_code).exists():
            generated_code = ShortLink.generate_short_code(original_url)

        short_link.short_code = generated_code
        short_link.save()

        return Response({"short_url": generated_code}, status=status.HTTP_201_CREATED)


class ClickReportAPI(APIView):
    """
    API endpoint to report click statistics for a given short code.
    Only accessible by the creator or staff users.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, short_code):
        """
        Returns click statistics and logs for the given short code.
        """
        short_link = get_object_or_404(ShortLink, short_code=short_code)
        if short_link.created_by != request.user and not request.user.is_staff:
            return Response({"error": "permission denied"}, status=status.HTTP_403_FORBIDDEN)

        click_logs = ClickLog.objects.filter(original_url=short_link.original_url).only('ip_address', 'referrer',
                                                                                        'timestamp', 'user_agent',
                                                                                        'request_data')
        data = {
            "total_clicks": short_link.click_count,
            "clicks": [
                {
                    "ip_address": log.ip_address,
                    "referrer": log.referrer,
                    "created_at": log.created_at,
                    "user_agent": log.user_agent,
                    "request_data": log.request_data,
                }
                for log in click_logs
            ]
        }
        return Response(data, status=status.HTTP_200_OK)
