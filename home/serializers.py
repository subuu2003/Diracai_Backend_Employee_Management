from rest_framework import serializers
from .models import SiteConfig


class SiteConfigSerializer(serializers.ModelSerializer):
    hero_video_url = serializers.SerializerMethodField()

    class Meta:
        model = SiteConfig
        fields = [
            "id",
            "company_name",
            "hero_heading",
            "hero_highlight",
            "hero_subheading",
            "hero_video",       # write-only upload field
            "hero_video_url",   # read-only full CDN URL
            "updated_at",
        ]
        extra_kwargs = {
            "hero_video": {"write_only": True, "required": False},
        }

    def get_hero_video_url(self, obj):
        """Return the full DigitalOcean Spaces / CDN URL for the video."""
        if not obj.hero_video:
            return None
        request = self.context.get("request")
        # django-storages with S3Boto3 returns an absolute URL from .url
        try:
            url = obj.hero_video.url
            # If it's already absolute (starts with http), return as-is
            if url.startswith("http"):
                return url
            # Otherwise build from request
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None


# ─── Hero Video Serializer ────────────────────────────────────────────────────
from .models import HeroVideo

class HeroVideoSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HeroVideo
        fields = [
            'id', 'media_type', 'title', 'duration', 'is_selected', 'order',
            'video',        # write-only upload
            'video_url',    # read-only CDN URL
            'image',        # write-only upload
            'image_url',    # read-only CDN URL
            'uploaded_at',
        ]
        extra_kwargs = {
            'video': {'write_only': True, 'required': False},
            'image': {'write_only': True, 'required': False},
        }

    def _get_url(self, field, request):
        if not field:
            return None
        try:
            url = field.url
            if url.startswith('http'):
                return url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

    def get_video_url(self, obj):
        return self._get_url(obj.video, self.context.get('request'))

    def get_image_url(self, obj):
        return self._get_url(obj.image, self.context.get('request'))
