from django.contrib import admin
from urlshortener.models import Campaign, Blogger, ShortLink, ClickLog

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'advertiser', 'is_active')
    search_fields = ('id', 'name', 'advertiser')
    list_filter = ('is_active',)
    readonly_fields = ('uuid', 'id')

    def get_queryset(self, request):
        query_set = super().get_queryset(request)
        return query_set.select_related('advertiser')

@admin.register(ShortLink)
class ShortLinkAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'original_url', 'campaign', 'blogger', 'status', 'click_count', 'created_at')
    search_fields = ('short_code', 'original_url', 'campaign__name', 'blogger__user_name')
    list_filter = ('status', 'is_active', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    readonly_fields = ('uuid', 'short_code', 'created_at', 'updated_at', 'click_count')
    actions = ['make_active', 'make_inactive', 'make_blocked']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('campaign', 'blogger', 'created_by')

    def make_active(self, request, queryset):
        queryset.update(status='active')
    make_active.short_description = "Mark selected links as Active"

    def make_inactive(self, request, queryset):
        queryset.update(status='inactive')
    make_inactive.short_description = "Mark selected links as Inactive"

    def make_blocked(self, request, queryset):
        queryset.update(status='blocked')
    make_blocked.short_description = "Mark selected links as Blocked"


@admin.register(Blogger)
class BloggerAdmin(admin.ModelAdmin):
    list_display = ('user_name', 'name', 'instagram_id')
    search_fields = ('user_name', 'name', 'instagram_id')
    ordering = ('user_name',)
    readonly_fields = ('user_name',)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('short_links')


@admin.register(ClickLog)
class ClickLogAdmin(admin.ModelAdmin):
    list_display = ('original_url', 'ip_address', 'referrer', 'user_agent', 'created_at')
    search_fields = ('original_url', 'ip_address', 'referrer', 'user_agent')
    list_filter = ('created_at',)
    ordering = ('-created_at',)
    readonly_fields = ('original_url', 'ip_address', 'referrer', 'user_agent', 'request_data', 'created_at')

