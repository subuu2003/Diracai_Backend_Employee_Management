from django.contrib import admin
from .models import SiteConfig, HeroVideo


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("company_name", "hero_heading", "hero_highlight", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HeroVideo)
class HeroVideoAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "duration", "is_selected", "order", "uploaded_at")
    list_editable = ("title", "duration", "is_selected", "order")
    list_filter = ("is_selected",)
    ordering = ("order", "uploaded_at")
    readonly_fields = ("uploaded_at",)
